"""Tier2 — PDF 텍스트 레이어 판독 (PyMuPDF).

정부24·건강보험공단이 발급하는 PDF는 스캔 이미지가 아니라 **텍스트 PDF**다.
그래서 상용 OCR API 없이도 문서종류·발급일·가구원수·건보료·전입일을 실제로 읽어낼
수 있고, 좌표(bbox)까지 같이 뽑을 수 있다. 이 계층이 "데모가 진짜로 서류를 읽는다"를
증명하는 자리다.

암호 여부(`needs_pass`)도 여기서 즉시 잡힌다 — 공고문이 직접 지목한 미비 사유다.

이미지(jpg/png)는 텍스트 레이어가 없으므로 여기서는 화면 캡처 휴리스틱과 화질
추정만 하고 판독은 Tier3에 넘긴다.
"""

import re
from datetime import date
from pathlib import Path

from ..rules.doc_types import DocType
from .base import BBox, OcrResult, unreadable

NAME = "pdftext"

#: 문서종류 분류 키워드. 앞에 오는 항목부터 검사하므로 **더 구체적인 것을 위에** 둔다.
#: 예: "주민등록표 초본"이 "주민등록표"보다 먼저 와야 초본/등본이 갈린다.
DOC_TYPE_KEYWORDS: list[tuple[DocType, tuple[str, ...]]] = [
    (DocType.RESIDENT_ABSTRACT, ("주민등록표초본", "주민등록초본")),
    (DocType.RESIDENT_CERTIFICATE, ("주민등록표등본", "주민등록등본")),
    (DocType.NHIS_ACQUISITION_LOSS, ("자격득실확인서",)),
    (DocType.NHIS_QUALIFICATION, ("자격확인서", "건강보험자격확인")),
    (DocType.NHIS_PAYMENT, ("보험료납부확인서", "건강보험료납부확인")),
    (DocType.INSURANCE_4, ("4대보험가입내역", "사대보험가입내역", "가입내역확인서")),
    (DocType.DAILY_WORK_RECORD, ("일용근로내역",)),
    (DocType.BIZ_REG_PROOF, ("사업자등록증명",)),
    (DocType.BIZ_REG_CERT, ("사업자등록증",)),
    (DocType.FARM_BIZ_CERT, ("농업경영체",)),
    (DocType.FISHERY_BIZ_CERT, ("어업경영체",)),
    (DocType.LABOR_CONTRACT, ("근로계약서",)),
    (DocType.ADMIN_INFO_CONSENT, ("행정정보공동이용",)),
    (DocType.INTERVIEW_CONFIRMATION, ("면접확인서",)),
    (DocType.EXAM_CONFIRMATION, ("응시확인서",)),
    (DocType.EXAM_TRANSCRIPT, ("성적표",)),
    (DocType.PAYMENT_RECEIPT, ("영수증",)),
]

#: "2026년 3월 5일" / "2026. 3. 5." / "2026-03-05" / "2026/03/05"
_DATE_RE = re.compile(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?")
#: 발급일 라벨 뒤에 오는 날짜만 따로 잡는다.
_ISSUE_LABEL_RE = re.compile(
    r"(?:발급일자?|발행일자?|발급년월일|교부일자)\s*[:：]?\s*"
    r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?"
)
_TRANSFER_RE = re.compile(
    r"(?:최종전입일|전입일자?|신고일)\s*[:：]?\s*"
    r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?"
)
#: "가구원수 4명" / "세대원수: 4"
_HOUSEHOLD_RE = re.compile(r"(?:가구원\s*수|세대원\s*수|세대원수)\s*[:：]?\s*(\d{1,2})")
#: 건강보험료 고지금액. 세 자리 콤마 표기를 그대로 잡는다.
_PREMIUM_RE = re.compile(
    r"(?:고지금액|보험료|월보험료|합계금액)\s*[:：]?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})"
)
#: 초본의 과거 주소이력 블록.
_ADDRESS_HISTORY_HINTS = ("주소변동", "변동사유", "세대주및관계", "번지")

#: 흔한 모니터 해상도. 화면 캡처 휴리스틱에 쓴다.
SCREEN_RESOLUTIONS = [
    (1280, 720), (1366, 768), (1440, 900), (1536, 864), (1600, 900),
    (1680, 1050), (1920, 1080), (1920, 1200), (2560, 1440), (2560, 1600),
    (2880, 1800), (3440, 1440), (3840, 2160),
]


def _squeeze(text: str) -> str:
    """공백을 모두 지운 비교용 문자열. PDF 텍스트는 글자 사이에 공백이 섞인다."""
    return re.sub(r"\s+", "", text)


def classify(text: str) -> DocType | None:
    """본문 텍스트로 문서 종류를 판별한다."""
    flat = _squeeze(text)
    for doc_type, keywords in DOC_TYPE_KEYWORDS:
        if any(k in flat for k in keywords):
            return doc_type
    return None


def _to_date(groups: tuple[str, str, str]) -> date | None:
    try:
        return date(int(groups[0]), int(groups[1]), int(groups[2]))
    except ValueError:
        return None


def extract_issue_date(text: str) -> date | None:
    """발급일. 라벨이 붙은 날짜를 우선하고, 없으면 문서에서 가장 늦은 날짜를 쓴다."""
    labeled = _ISSUE_LABEL_RE.search(_squeeze(text))
    if labeled:
        return _to_date(labeled.groups())  # type: ignore[arg-type]
    candidates = [d for g in _DATE_RE.findall(text) if (d := _to_date(g))]
    # 발급일은 보통 문서에 찍힌 날짜 중 가장 나중이다.
    return max(candidates) if candidates else None


def extract_transfer_in(text: str) -> date | None:
    """초본의 최종 전입일. 라벨이 없으면 주소 변동 이력의 마지막 날짜를 쓴다."""
    labeled = _TRANSFER_RE.search(_squeeze(text))
    if labeled:
        return _to_date(labeled.groups())  # type: ignore[arg-type]
    return None


def extract_household_size(text: str) -> str | None:
    m = _HOUSEHOLD_RE.search(_squeeze(text))
    return m.group(1) if m else None


def extract_premium(text: str) -> str | None:
    """건강보험료 고지금액. 실납부액이 아니라 고지금액이 심사 기준이다."""
    m = _PREMIUM_RE.search(_squeeze(text))
    return m.group(1).replace(",", "") if m else None


def has_address_history(text: str) -> bool:
    """초본에 과거 주소이력이 들어 있는가. 공고문이 지목한 미비 사유 ②."""
    flat = _squeeze(text)
    if "주소변동내역" in flat and ("없음" in flat or "미포함" in flat):
        return False
    return sum(1 for h in _ADDRESS_HISTORY_HINTS if h in flat) >= 1


def _locate(page, needle: str, page_index: int) -> BBox | None:
    """페이지에서 문자열 위치를 찾아 bbox로. 못 찾으면 None."""
    try:
        rects = page.search_for(needle)
    except Exception:  # noqa: BLE001 - 좌표를 못 구해도 판독은 계속돼야 한다
        return None
    if not rects:
        return None
    r = rects[0]
    return BBox(page_index, float(r.x0), float(r.y0), float(r.x1), float(r.y1))


def _confidence(text: str, doc_type: DocType | None, issue_date: date | None) -> float:
    """텍스트 레이어 판독의 신뢰도 추정.

    상용 OCR처럼 문자 단위 확률이 없으므로, **읽어낸 신호의 개수**로 근사한다.
    엔진 임계값(0.85)과 직접 비교되는 값이라 계산 근거를 눈에 보이게 둔다.
    길이만으로 매기면 짧지만 정확한 서류가 부당하게 담당자 큐로 밀려난다.
    """
    if doc_type is None:
        return 0.55  # 종류를 모르면 담당자 확인 대상
    length = len(_squeeze(text))
    score = 0.6
    score += 0.2  # 문서종류 판별 성공
    if issue_date is not None:
        score += 0.1
    if length >= 150:
        score += 0.05
    if length >= 400:
        score += 0.05
    return round(min(score, 1.0), 2)


def read_page_text(text: str, page, page_index: int) -> OcrResult:
    """페이지 텍스트 하나를 판독 결과로 만든다. 병합 PDF 분리에서도 이걸 쓴다."""
    doc_type = classify(text)
    issue_date = extract_issue_date(text)

    fields: dict[str, str] = {}
    bboxes: dict[str, BBox] = {}

    if issue_date:
        fields["발급일"] = issue_date.isoformat()
        box = _locate(page, f"{issue_date.year}", page_index) if page else None
        if box:
            bboxes["발급일"] = box

    transfer_in = extract_transfer_in(text)
    if transfer_in:
        fields["전입일"] = transfer_in.isoformat()

    size = extract_household_size(text)
    if size:
        fields["가구원수"] = size
        box = _locate(page, size, page_index) if page else None
        if box:
            bboxes["가구원수"] = box

    premium = extract_premium(text)
    if premium:
        fields["건강보험료"] = premium
        box = _locate(page, f"{int(premium):,}", page_index) if page else None
        if box:
            bboxes["건강보험료"] = box

    if doc_type is DocType.RESIDENT_ABSTRACT:
        fields["주소변동내역"] = "포함" if has_address_history(text) else "미포함"

    # 서명란 감지: 텍스트 PDF에서는 "(서명 또는 인)" 문구 옆 서명 이미지 유무를
    # 판별할 수 없다. 서명이 필요한 서류(서식5)에서만 의미가 있으므로 None으로 둔다.
    return OcrResult(
        detected_doc_type=doc_type,
        confidence=_confidence(text, doc_type, issue_date),
        image_quality=1.0,  # 텍스트 PDF는 화질 개념이 없다
        issue_date=issue_date,
        fields=fields,
        bboxes=bboxes,
        tier=NAME,
    )


def _read_pdf(path: Path) -> OcrResult | None:
    import fitz  # PyMuPDF. 지연 import — 이미지 파일만 다룰 때는 필요 없다.

    try:
        doc = fitz.open(path)
    except Exception as e:  # noqa: BLE001
        return unreadable(f"파일을 열 수 없습니다: {e}", tier=NAME)

    with doc:
        if doc.needs_pass:
            # 공고문 미비 사유 ① 파일 암호 미해제.
            return unreadable("PDF에 암호가 걸려 있어 열 수 없습니다.", tier=NAME)

        page_count = doc.page_count
        if page_count == 0:
            return unreadable("페이지가 없는 PDF입니다.", tier=NAME)

        page = doc[0]
        text = page.get_text()
        if not _squeeze(text):
            # 텍스트 레이어가 없다 = 스캔 이미지 PDF. Tier3 몫.
            return None

        result = read_page_text(text, page, 0)
        result.page_count = page_count
        return result


def _read_image(path: Path) -> OcrResult | None:
    """이미지는 판독하지 않고, 화면 캡처 여부와 화질만 본다.

    화면 캡처는 **확정 판정을 하지 않는다.** 오탐이면 신청자가 억울해지는 항목이라
    담당자 확인 대상(NEEDS_REVIEW)으로만 보낸다.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(path) as im:
            width, height = im.size
            exif = im.getexif()
    except Exception as e:  # noqa: BLE001
        return unreadable(f"이미지를 열 수 없습니다: {e}", tier=NAME)

    # EXIF 0x010F Make / 0x0110 Model — 카메라로 찍었으면 보통 채워져 있다.
    has_camera = bool(exif.get(0x010F) or exif.get(0x0110))
    near_screen = any(
        abs(width - w) <= 8 and abs(height - h) <= 8 for w, h in SCREEN_RESOLUTIONS
    )
    screen_capture = near_screen and not has_camera

    # 화질은 해상도로 근사한다. A4를 200dpi로 스캔하면 짧은 변이 1600px 안팎이다.
    short_side = min(width, height)
    if short_side >= 1400:
        quality = 0.9
    elif short_side >= 1000:
        quality = 0.75
    elif short_side >= 700:
        quality = 0.55
    else:
        quality = 0.35

    return OcrResult(
        detected_doc_type=None,
        confidence=0.0,  # 판독하지 못했다 → 엔진이 NEEDS_REVIEW로 넘긴다
        image_quality=quality,
        is_screen_capture=screen_capture,
        fields={
            "해상도": f"{width}x{height}",
            "촬영정보": "있음" if has_camera else "없음",
        },
        tier=NAME,
    )


class PdfTextOcr:
    """PDF는 텍스트 레이어로 읽고, 이미지는 화면 캡처 판별만 한다."""

    name = NAME

    def read(self, file_path: str, expected: DocType | None) -> OcrResult | None:
        del expected  # Tier2는 기대값을 보지 않고 있는 그대로 읽는다
        path = Path(file_path)
        if not path.exists():
            return unreadable("파일이 존재하지 않습니다.", tier=NAME)
        if path.suffix.lower() == ".pdf":
            return _read_pdf(path)
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            return _read_image(path)
        return None


def split_pdf_pages(file_path: str, out_dir: Path, stem: str) -> list[tuple[int, Path, OcrResult]]:
    """병합 PDF를 페이지 단위로 쪼개고 각 페이지를 판독한다 (R3.5).

    공고문은 "1개의 파일로 압축하여 올려야 함"을 요구한다. 신청자가 기존 방식대로
    합쳐 올린 경우에도 슬롯별로 자동 배정되게 하려면 페이지 단위로 나눠야 한다.

    반환: [(페이지 번호, 쪼갠 파일 경로, 판독 결과), ...]
    """
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[int, Path, OcrResult]] = []

    with fitz.open(file_path) as doc:
        if doc.needs_pass:
            return results
        for i in range(doc.page_count):
            page = doc[i]
            result = read_page_text(page.get_text(), page, i)
            result.page_count = 1

            single = fitz.open()
            single.insert_pdf(doc, from_page=i, to_page=i)
            target = out_dir / f"{stem}_p{i + 1}.pdf"
            single.save(target)
            single.close()

            results.append((i, target, result))

    return results
