"""전북AI PaddleOCR-VL 클라이언트.

기존 OcrWord 인터페이스와 달리 이 백엔드는 bbox를 제공한다고 가정하지 않는다.
결과는 쪽별 텍스트 줄과 HTML 표 구조로 보존한다. 서류 판독은 `extractors/jbai_text.py`가 맡는다.

전송 이미지는 JPEG만 쓴다(전북AI OCR은 JPG만 받는다). PDF는 쪽마다 200dpi RGB로 렌더링하고,
사진은 RGB로 바꿔 품질 95 JPEG로 다시 인코딩한다.

응답 본문에는 주민등록번호 13자리가 그대로 온다. 받은 즉시 `mask_rrn`으로 뒷자리(성별 자리 뒤
6자리)를 지우고, 지운 텍스트만 결과(`text_lines`·`tables`·`raw_content`)에 남긴다.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from ..paths import PRIVATE_DIR

MODEL = "PaddlePaddle/PaddleOCR-VL"
DEFAULT_BASE_URL = "https://ai.jb.go.kr/open-api/v1"
REQUEST_TIMEOUT_SEC = 600
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_ATTEMPTS = 4  # 첫 요청 + 최대 3회 재시도
TASK_OCR = "OCR:"
TASK_TABLE = "Table Recognition:"
RENDER_DPI = 200
JPEG_QUALITY = 95
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class JBAIOCRError(RuntimeError):
    """외부 OCR 요청 오류. 키·응답 전문은 메시지에 포함하지 않는다.

    `status`는 로그·대체 사유에 남길 HTTP 상태 코드(모르면 None)다.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class JBAIConfigurationError(JBAIOCRError):
    pass


class JBAIAuthenticationError(JBAIOCRError):
    pass


class JBAIRateLimitError(JBAIOCRError):
    pass


class JBAIRequestError(JBAIOCRError):
    pass


class JBAITimeoutError(JBAIRequestError):
    pass


class JBAIResponseError(JBAIOCRError):
    pass


class JBAIRealDocumentBlocked(JBAIOCRError):
    pass


class JBAIImageTooLarge(JBAIOCRError):
    pass


@dataclass(frozen=True)
class JBAITableCell:
    text: str
    rowspan: int = 1
    colspan: int = 1
    header: bool = False


@dataclass(frozen=True)
class JBAITable:
    rows: list[list[JBAITableCell]] = field(default_factory=list)


@dataclass(frozen=True)
class JBAIPageResult:
    page: int
    text_lines: list[str]
    tables: list[JBAITable]
    elapsed_sec: float
    raw_content: str = ""
    table_content: str = ""
    ocr_elapsed_sec: float = 0.0
    table_elapsed_sec: float = 0.0
    image_size: tuple[int, int] = (0, 0)
    jpeg_bytes: int = 0


@dataclass(frozen=True)
class JBAIDocumentResult:
    pages: list[JBAIPageResult]
    elapsed_sec: float

    @property
    def request_count(self) -> int:
        return sum((bool(page.ocr_elapsed_sec) + bool(page.table_elapsed_sec)) or 1 for page in self.pages)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[JBAITableCell]] = []
        self._row: list[JBAITableCell] | None = None
        self._cell: dict[str, object] | None = None

    @staticmethod
    def _span(attrs: list[tuple[str, str | None]], name: str) -> int:
        raw = next((value for key, value in attrs if key.lower() == name), None)
        try:
            return max(1, min(100, int(raw or "1")))
        except (TypeError, ValueError):
            return 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = {
                "text": [], "rowspan": self._span(attrs, "rowspan"),
                "colspan": self._span(attrs, "colspan"), "header": tag == "th",
            }
        elif tag == "br" and self._cell is not None:
            self._cell["text"].append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(JBAITableCell(
                text=re.sub(r"\s+", " ", "".join(self._cell["text"])).strip(),
                rowspan=int(self._cell["rowspan"]), colspan=int(self._cell["colspan"]),
                header=bool(self._cell["header"]),
            ))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def parse_html_tables(content: str) -> list[JBAITable]:
    """HTML table의 각 셀 텍스트와 병합 범위를 보존한다."""
    tables: list[JBAITable] = []
    for match in re.finditer(r"<table\b[^>]*>.*?</table\s*>", content, flags=re.I | re.S):
        parser = _TableParser()
        parser.feed(match.group(0))
        parser.close()
        if parser.rows:
            tables.append(JBAITable(rows=parser.rows))
    return tables


_OTSL_TOKEN = re.compile(r"<(fcel|ecel|lcel|ucel|xcel|nl)>", re.I)


@dataclass
class _OTSLAnchor:
    text: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


def parse_otsl_tables(content: str) -> list[JBAITable]:
    """OTSL 구조 토큰을 셀 격자로 바꾸고 가로·세로 병합을 복원한다."""
    matches = list(_OTSL_TOKEN.finditer(content))
    if not matches:
        return []

    anchors: list[_OTSLAnchor] = []
    occupancy: dict[tuple[int, int], _OTSLAnchor] = {}
    previous: dict[tuple[int, int], _OTSLAnchor] = {}
    row = col = max_row = 0
    for index, match in enumerate(matches):
        token = match.group(1).lower()
        if token == "nl":
            max_row = max(max_row, row)
            row += 1
            col = 0
            previous, occupancy = occupancy, {}
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        value = re.sub(r"\s+", " ", content[match.end():end]).strip()
        if token in {"fcel", "ecel"}:
            anchor = _OTSLAnchor(value if token == "fcel" else "", row, col)
            anchors.append(anchor)
            occupancy[(row, col)] = anchor
        elif token == "lcel":
            anchor = occupancy.get((row, col - 1))
            if anchor is None:
                anchor = _OTSLAnchor("", row, col)
                anchors.append(anchor)
            anchor.colspan += 1
            if value:
                anchor.text = (anchor.text + " " + value).strip()
            occupancy[(row, col)] = anchor
        elif token == "ucel":
            anchor = previous.get((row - 1, col))
            if anchor is None:
                anchor = _OTSLAnchor("", row, col)
                anchors.append(anchor)
            elif anchor.row + anchor.rowspan == row:
                anchor.rowspan += 1
            occupancy[(row, col)] = anchor
        else:  # xcel — 같은 상단 셀의 가로·세로 연장
            anchor = previous.get((row - 1, col)) or occupancy.get((row, col - 1))
            if anchor is None:
                anchor = _OTSLAnchor("", row, col)
                anchors.append(anchor)
            if anchor.row + anchor.rowspan == row:
                anchor.rowspan += 1
            if anchor.col + anchor.colspan == col:
                anchor.colspan += 1
            if value:
                anchor.text = (anchor.text + " " + value).strip()
            occupancy[(row, col)] = anchor
        col += 1

    max_row = max(max_row, row)
    rows: list[list[JBAITableCell]] = [[] for _ in range(max_row + 1)]
    for anchor in sorted(anchors, key=lambda cell: (cell.row, cell.col)):
        rows[anchor.row].append(JBAITableCell(
            text=anchor.text, rowspan=anchor.rowspan, colspan=anchor.colspan,
            header=anchor.row < 2,
        ))
    rows = [cells for cells in rows if cells]
    return [JBAITable(rows=rows)] if rows else []


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._in_table = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._in_table += 1
        elif not self._in_table and tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "table" and self._in_table:
            self._in_table -= 1
        elif not self._in_table and tag in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._in_table:
            self.parts.append(data)


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                fragments.append(item["text"])
        return "\n".join(fragments)
    raise JBAIResponseError("전북AI OCR 응답의 message.content 형식을 해석할 수 없습니다.")


def _response_content(body: object) -> str:
    if not isinstance(body, dict):
        raise JBAIResponseError("전북AI OCR 응답이 JSON 객체가 아닙니다.")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise JBAIResponseError("전북AI OCR 응답에 choices 항목이 없습니다.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise JBAIResponseError("전북AI OCR 응답에 message 항목이 없습니다.")
    return _content_text(message.get("content"))


#: 주민등록번호(외국인등록번호 포함). 앞 6자리 + 구분자 + 성별 자리 + 나머지 6자리.
#: OCR이 뒷자리 숫자 사이에 공백을 끼워 읽는 경우도 잡는다.
_RRN_SEPARATED = re.compile(r"(?<!\d)(\d{6})([ \t]*[-‐‑‒–—―~][ \t]*)(\d)((?:[ \t]?\d){6})(?!\d)")
#: 구분자 없이 13자리가 붙어 온 경우.
_RRN_COMPACT = re.compile(r"(?<!\d)(\d{6})(\d)(\d{6})(?!\d)")


def mask_rrn(text: str) -> str:
    """주민등록번호 뒷자리 중 성별 자리 뒤 6자리를 `*`로 지운다.

    생년월일·성별 자리는 남긴다 — 초본·건강보험 추출기가 출생 연도(1900/2000년대)를
    성별 자리로 가르기 때문이다(`resident_abstract.RRN`, `nhis_common.RRN_RE`).
    """
    text = _RRN_SEPARATED.sub(lambda m: f"{m.group(1)}-{m.group(3)}******", text)
    return _RRN_COMPACT.sub(lambda m: f"{m.group(1)}{m.group(2)}******", text)


def _text_lines(content: str) -> list[str]:
    without_tables = re.sub(r"<table\b[^>]*>.*?</table\s*>", "\n", content, flags=re.I | re.S)
    if "<" in without_tables and ">" in without_tables:
        parser = _PlainTextParser()
        parser.feed(without_tables)
        text = "".join(parser.parts)
    else:
        text = without_tables
    lines = []
    for line in text.replace("```html", "").replace("```", "").splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


class _TokenBucket:
    """최대 30회 순간 요청, 분당 평균 최대 60회(초당 1 토큰 재충전)."""

    def __init__(self, capacity: int = 30, refill_per_sec: float = 1.0,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = float(capacity)
        self.clock = clock
        self.sleep = sleep
        self.updated = clock()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = self.clock()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_sec)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                delay = (1 - self.tokens) / self.refill_per_sec
            self.sleep(delay)


_RATE_LIMITER = _TokenBucket()
_CONCURRENCY = threading.BoundedSemaphore(4)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_private_path(path: str | Path | None) -> bool:
    if path is None:
        return False
    try:
        Path(path).resolve().relative_to(Path(PRIVATE_DIR).resolve())
        return True
    except (OSError, ValueError):
        return False


def ensure_external_allowed(source_path: str | Path | None = None,
                            *, is_demo_upload: bool = False) -> None:
    if _truthy(os.environ.get("JBAI_ALLOW_REAL_DOCS")):
        return
    if is_demo_upload:
        raise JBAIRealDocumentBlocked(
            "JBAI_ALLOW_REAL_DOCS=false이므로 데모 업로드는 전북AI로 보내지 않습니다. 기존 OCR 경로를 사용하세요."
        )
    if _is_private_path(source_path):
        raise JBAIRealDocumentBlocked(
            "JBAI_ALLOW_REAL_DOCS=false이므로 data/private 경로 파일은 전북AI로 보내지 않습니다."
        )


def _retry_after(headers: object, attempt: int) -> float:
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    if raw:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            try:
                when = parsedate_to_datetime(str(raw))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return float(2 ** (attempt - 1))


def _http_post(request: urllib.request.Request, timeout: int):
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        # 오류 응답 본문은 로그·예외에 붙이지 않는다.
        return error.code, b"", error.headers


def _is_timeout(error: BaseException) -> bool:
    if isinstance(error, TimeoutError):
        return True
    reason = getattr(error, "reason", None)
    return isinstance(reason, TimeoutError) or "timed out" in str(reason or "").lower()


def run_jbai_ocr(image: bytes, size: tuple[int, int], *, task: str = TASK_OCR,
                 page: int = 0, source_path: str | Path | None = None,
                 is_demo_upload: bool = False,
                 sleep: Callable[[float], None] = time.sleep,
                 timeout: float = REQUEST_TIMEOUT_SEC) -> JBAIPageResult:
    """합성/승인 문서의 한 JPEG 쪽을 요청한다. task는 OCR: 또는 Table Recognition:.

    `image`는 JPEG 바이트다(`render_pdf_pages_200dpi`·`image_file_to_jpeg`로 만든다).
    32MB 제한은 실제로 보내는 이 바이트로 검사한다.
    """
    ensure_external_allowed(source_path, is_demo_upload=is_demo_upload)
    if task not in {TASK_OCR, TASK_TABLE}:
        raise ValueError("task는 'OCR:' 또는 'Table Recognition:'이어야 합니다.")
    if len(image) > MAX_IMAGE_BYTES:
        raise JBAIImageTooLarge("전북AI OCR 이미지가 32MB 제한을 넘었습니다.")
    key = os.environ.get("JBAI_API_KEY", "").strip()
    if not key:
        raise JBAIConfigurationError("JBAI_API_KEY가 설정되지 않았습니다.")
    # --env-file로 빈 값(JBAI_BASE_URL=)이 들어와도 기본 주소를 쓴다.
    base_url = (os.environ.get("JBAI_BASE_URL", "").strip() or DEFAULT_BASE_URL).rstrip("/")
    url = base_url + "/ocr/chat/completions"
    data_url = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": task},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _RATE_LIMITER.acquire()
        try:
            with _CONCURRENCY:
                status, response_bytes, headers = _http_post(request, timeout)
        except Exception as error:  # noqa: BLE001
            if _is_timeout(error):
                raise JBAITimeoutError("전북AI OCR 응답 시간이 초과되었습니다.") from None
            raise JBAIRequestError(f"전북AI OCR 요청 실패 ({type(error).__name__}).") from None
        if status == 401:
            raise JBAIAuthenticationError(
                "전북AI OCR 인증에 실패했습니다. JBAI_API_KEY가 틀렸거나 만료되었는지 확인하세요.",
                status=401,
            )
        if status == 429:
            if attempt == MAX_ATTEMPTS:
                raise JBAIRateLimitError(
                    f"전북AI OCR이 재시도 {MAX_ATTEMPTS - 1}회 뒤에도 요청을 제한했습니다.",
                    status=429,
                )
            sleep(_retry_after(headers, attempt))
            continue
        if status < 200 or status >= 300:
            raise JBAIRequestError(f"전북AI OCR 요청이 HTTP {status}로 실패했습니다.", status=status)
        try:
            body = json.loads(response_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise JBAIResponseError("전북AI OCR 응답이 JSON이 아닙니다.", status=status) from None
        # 원문(주민번호 13자리 포함)은 여기서 바로 가린다. 아래로는 가린 텍스트만 흐른다.
        content = mask_rrn(_response_content(body))
        del body, response_bytes
        return JBAIPageResult(
            page=page, text_lines=_text_lines(content),
            tables=parse_html_tables(content) or parse_otsl_tables(content),
            elapsed_sec=time.monotonic() - started, raw_content=content,
            ocr_elapsed_sec=(time.monotonic() - started) if task == TASK_OCR else 0.0,
            table_elapsed_sec=(time.monotonic() - started) if task == TASK_TABLE else 0.0,
            image_size=size, jpeg_bytes=len(image),
        )
    raise JBAIRateLimitError("전북AI OCR 요청이 재시도 한도를 넘었습니다.", status=429)


def _encode_jpeg(image) -> bytes:
    """PIL 이미지를 알파 없는 RGB JPEG(품질 95)로 인코딩한다. 투명 영역은 흰 바탕으로 채운다."""
    from PIL import Image

    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, (255, 255, 255))
        flattened.paste(rgba, mask=rgba.getchannel("A"))
        image = flattened
    elif image.mode != "RGB":
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def render_pdf_pages_200dpi(file_path: str | Path) -> list[tuple[int, bytes, tuple[int, int]]]:
    """PDF를 쪽 순서대로 200dpi RGB(알파 없음)로 렌더링해 JPEG(품질 95)로 만든다."""
    import pymupdf
    from PIL import Image

    scale = RENDER_DPI / 72
    rendered = []
    with pymupdf.open(file_path) as document:
        if document.needs_pass:
            raise JBAIRequestError("암호화된 PDF는 전북AI OCR 입력으로 사용할 수 없습니다.")
        for index, page in enumerate(document):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                  colorspace=pymupdf.csRGB, alpha=False)
            if pix.alpha:
                pix = pymupdf.Pixmap(pix, 0)  # 알파 채널 제거
            if pix.n != 3:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            rendered.append((index, _encode_jpeg(image), (pix.width, pix.height)))
    return rendered


def image_file_to_jpeg(file_path: str | Path) -> tuple[bytes, tuple[int, int]]:
    """사진 업로드(png·jpg 등)를 전송용 RGB JPEG(품질 95)로 바꾼다.

    휴대폰 사진의 EXIF 회전을 반영하고, 다시 인코딩하므로 촬영 위치 같은 메타데이터는 빠진다.
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(file_path) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
    except Exception as error:  # noqa: BLE001
        raise JBAIRequestError(f"이미지를 열 수 없습니다 ({type(error).__name__}).") from None
    return _encode_jpeg(image), image.size


def run_jbai_pdf(file_path: str | Path, *, task: str = TASK_OCR,
                 is_demo_upload: bool = False) -> JBAIDocumentResult:
    """가드 검사 후 PDF를 페이지 단위로 순서대로 요청한다."""
    ensure_external_allowed(file_path, is_demo_upload=is_demo_upload)
    started = time.monotonic()
    rendered = render_pdf_pages_200dpi(file_path)
    results = [
        run_jbai_ocr(image, size, task=task, page=index, source_path=file_path,
                     is_demo_upload=is_demo_upload)
        for index, image, size in rendered
    ]
    return JBAIDocumentResult(pages=results, elapsed_sec=time.monotonic() - started)


def run_jbai_image_pair(image: bytes, size: tuple[int, int], *, page: int = 0,
                        source_path: str | Path | None = None,
                        is_demo_upload: bool = False,
                        sleep: Callable[[float], None] = time.sleep,
                        timeout: float = REQUEST_TIMEOUT_SEC) -> JBAIPageResult:
    """JPEG 한 쪽에 OCR과 표 인식을 각각 호출해 텍스트·표를 함께 보존한다."""
    text_result = run_jbai_ocr(image, size, task=TASK_OCR, page=page,
                               source_path=source_path, is_demo_upload=is_demo_upload,
                               sleep=sleep, timeout=timeout)
    table_result = run_jbai_ocr(image, size, task=TASK_TABLE, page=page,
                                source_path=source_path, is_demo_upload=is_demo_upload,
                                sleep=sleep, timeout=timeout)
    return JBAIPageResult(
        page=page, text_lines=text_result.text_lines, tables=table_result.tables,
        elapsed_sec=text_result.elapsed_sec + table_result.elapsed_sec,
        raw_content=text_result.raw_content, table_content=table_result.raw_content,
        ocr_elapsed_sec=text_result.elapsed_sec, table_elapsed_sec=table_result.elapsed_sec,
        image_size=size, jpeg_bytes=len(image),
    )


def run_jbai_pdf_pair(file_path: str | Path, *, is_demo_upload: bool = False,
                      sleep: Callable[[float], None] = time.sleep,
                      timeout: float = REQUEST_TIMEOUT_SEC) -> JBAIDocumentResult:
    """PDF를 쪽마다 200dpi JPEG로 렌더링해 OCR·표 인식을 모두 실행한다."""
    path = Path(file_path)
    ensure_external_allowed(path, is_demo_upload=is_demo_upload)
    started = time.monotonic()
    pages = [
        run_jbai_image_pair(image, size, page=index, source_path=path,
                            is_demo_upload=is_demo_upload, sleep=sleep, timeout=timeout)
        for index, image, size in render_pdf_pages_200dpi(path)
    ]
    return JBAIDocumentResult(pages=pages, elapsed_sec=time.monotonic() - started)


def run_jbai_file_pair(file_path: str | Path, *, is_demo_upload: bool = False,
                       sleep: Callable[[float], None] = time.sleep,
                       timeout: float = REQUEST_TIMEOUT_SEC) -> JBAIDocumentResult:
    """PDF는 쪽마다, 사진은 한 쪽으로 JPEG를 만들어 OCR·표 인식을 모두 실행한다."""
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return run_jbai_pdf_pair(path, is_demo_upload=is_demo_upload, sleep=sleep, timeout=timeout)
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        raise JBAIRequestError("전북AI OCR은 PDF와 사진 파일만 보낼 수 있습니다.")
    ensure_external_allowed(path, is_demo_upload=is_demo_upload)
    started = time.monotonic()
    image, size = image_file_to_jpeg(path)
    page = run_jbai_image_pair(image, size, page=0, source_path=path,
                               is_demo_upload=is_demo_upload, sleep=sleep, timeout=timeout)
    return JBAIDocumentResult(pages=[page], elapsed_sec=time.monotonic() - started)
