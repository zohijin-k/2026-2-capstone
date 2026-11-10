"""전북AI PaddleOCR-VL 클라이언트.

기존 OcrWord 인터페이스와 달리 이 백엔드는 bbox를 제공한다고 가정하지 않는다.
결과는 쪽별 텍스트 줄과 HTML 표 구조로 보존하며, 기존 서류 추출기에는 연결하지 않는다.
"""

from __future__ import annotations

import base64
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


class JBAIOCRError(RuntimeError):
    """외부 OCR 요청 오류. 키·응답 전문은 메시지에 포함하지 않는다."""


class JBAIConfigurationError(JBAIOCRError):
    pass


class JBAIAuthenticationError(JBAIOCRError):
    pass


class JBAIRateLimitError(JBAIOCRError):
    pass


class JBAIRequestError(JBAIOCRError):
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


@dataclass(frozen=True)
class JBAIDocumentResult:
    pages: list[JBAIPageResult]
    elapsed_sec: float


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


def run_jbai_ocr(png: bytes, size: tuple[int, int], *, task: str = TASK_OCR,
                 page: int = 0, source_path: str | Path | None = None,
                 is_demo_upload: bool = False,
                 sleep: Callable[[float], None] = time.sleep) -> JBAIPageResult:
    """합성/승인 문서의 한 PNG 쪽을 요청한다. task는 OCR: 또는 Table Recognition:."""
    ensure_external_allowed(source_path, is_demo_upload=is_demo_upload)
    if task not in {TASK_OCR, TASK_TABLE}:
        raise ValueError("task는 'OCR:' 또는 'Table Recognition:'이어야 합니다.")
    if len(png) > MAX_IMAGE_BYTES:
        raise JBAIImageTooLarge("전북AI OCR 이미지가 32MB 제한을 넘었습니다.")
    key = os.environ.get("JBAI_API_KEY", "").strip()
    if not key:
        raise JBAIConfigurationError("JBAI_API_KEY가 설정되지 않았습니다.")
    base_url = os.environ.get("JBAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    url = base_url + "/ocr/chat/completions"
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
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
                status, response_bytes, headers = _http_post(request, REQUEST_TIMEOUT_SEC)
        except Exception as error:  # noqa: BLE001
            raise JBAIRequestError(f"전북AI OCR 요청 실패 ({type(error).__name__}).") from None
        if status == 401:
            raise JBAIAuthenticationError(
                "전북AI OCR 인증에 실패했습니다. JBAI_API_KEY가 틀렸거나 만료되었는지 확인하세요."
            )
        if status == 429:
            if attempt == MAX_ATTEMPTS:
                raise JBAIRateLimitError(
                    f"전북AI OCR이 재시도 {MAX_ATTEMPTS - 1}회 뒤에도 요청을 제한했습니다."
                )
            sleep(_retry_after(headers, attempt))
            continue
        if status < 200 or status >= 300:
            raise JBAIRequestError(f"전북AI OCR 요청이 HTTP {status}로 실패했습니다.")
        try:
            body = json.loads(response_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise JBAIResponseError("전북AI OCR 응답이 JSON이 아닙니다.") from None
        content = _response_content(body)
        return JBAIPageResult(
            page=page, text_lines=_text_lines(content), tables=parse_html_tables(content),
            elapsed_sec=time.monotonic() - started,
        )
    raise JBAIRateLimitError("전북AI OCR 요청이 재시도 한도를 넘었습니다.")


def render_pdf_pages_200dpi(file_path: str | Path) -> list[tuple[int, bytes, tuple[int, int]]]:
    """PDF를 쪽 순서대로 200dpi PNG로 렌더한다."""
    import pymupdf

    scale = 200 / 72
    rendered = []
    with pymupdf.open(file_path) as document:
        if document.needs_pass:
            raise JBAIRequestError("암호화된 PDF는 전북AI OCR 입력으로 사용할 수 없습니다.")
        for index, page in enumerate(document):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            if pix.n != 3:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            rendered.append((index, pix.tobytes("png"), (pix.width, pix.height)))
    return rendered


def run_jbai_pdf(file_path: str | Path, *, task: str = TASK_OCR,
                 is_demo_upload: bool = False) -> JBAIDocumentResult:
    """가드 검사 후 PDF를 페이지 단위로 순서대로 요청한다."""
    ensure_external_allowed(file_path, is_demo_upload=is_demo_upload)
    started = time.monotonic()
    rendered = render_pdf_pages_200dpi(file_path)
    results = [
        run_jbai_ocr(png, size, task=task, page=index, source_path=file_path,
                     is_demo_upload=is_demo_upload)
        for index, png, size in rendered
    ]
    return JBAIDocumentResult(pages=results, elapsed_sec=time.monotonic() - started)
