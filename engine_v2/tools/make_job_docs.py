"""취업지원패키지 추가서류 합성기 — 결제영수증·응시서류·면접확인서 (가상 값만).

  python -m engine_v2.tools.make_job_docs                 # → engine_v2/data/synthetic/job_docs/ (커밋 안 됨)
  python -m engine_v2.tools.make_job_docs --n 3 --seed 7 --conditions text,clean,scan,photo,lowres

만드는 것: 서류 모양(layout)마다 n건 × 화질 조건(condition)마다 파일 1개와
  - 파일마다 정답 `<파일 이름>.gt.json` (make_gt와 같은 키 → extract_check --gt 로 바로 비교)
  - 전체 목록 `manifest.json` (job_docs_bench 가 읽음: 서류 종류·기대 판별·일부러 넣은 결함)
화질 조건
  text    글자층 PDF (OCR 없이 읽힘 — 판독 논리 확인용)
  clean   200dpi 이미지 PDF
  scan    흑백·약한 흐림·1° 안팎 기울기·JPEG 압축, 200dpi 이미지 PDF
  photo   책상 위 휴대폰 사진 흉내(배경·3° 안팎 기울기·색조·잡음), JPG
  lowres  100dpi 이미지 PDF
면접확인서는 저장소의 사업계획서 서식(demo/fixtures/templates/job_interview_confirmation.pdf)에 값을 채운다.
글꼴은 저장소의 Noto Sans KR 부분집합(OFL, 데모 서식과 같은 파일)이라 운영체제와 상관없이 같게 그려진다.
(PyMuPDF 내장 'korea' 글꼴은 숫자·영문을 전각 폭으로 기록해 금액 끝자리가 페이지 밖으로 잘린다.)
판독기를 만든 사람이 만든 합성이라 쉬운 시험이다. 준실셋(인쇄 후 촬영)과 함께 본다.
"""
from __future__ import annotations

import argparse
import io
import json
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter

from ..extractors.job_common import brn_check_digit

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "engine_v2" / "data" / "synthetic" / "job_docs"
INTERVIEW_TEMPLATE = ROOT / "demo" / "fixtures" / "templates" / "job_interview_confirmation.pdf"
INTERVIEW_COORDS = ROOT / "demo" / "fixtures" / "form_coords" / "job_interview_confirmation.json"
FONT_FILE = ROOT / "demo" / "frontend" / "src" / "assets" / "fonts" / "NotoSansKR" / "NotoSansKR-subset.ttf"
FONT = "notokr"
CONDITIONS = ("text", "clean", "scan", "photo", "lowres")

SURNAMES = "김이박최정강조윤장임"
GIVEN = "가나다라마바사아자하온별솔빛결찬린윤준서"
STORES = {
    "suit": ("한빛정장대여", "새솔양복점", "미래정장", "바른예복"),
    "photo": ("다온사진관", "온누리포토", "푸른스튜디오"),
}
COMPANIES = ("한빛테크(주)", "새솔물산", "푸른에너지 주식회사", "다온디자인", "미래로지스(주)")
INDUSTRIES = ("정보통신업/소프트웨어 개발", "도소매/사무용품", "제조업/전자부품", "서비스/광고 디자인")
JOBS = ("사무 행정", "영업", "웹 개발", "생산 관리", "디자인")
PLACES = ("본사 3층 회의실", "2층 면접실", "전주지점 회의실")
EXAMS = (("정보처리기능사", 19400), ("컴퓨터활용능력 2급", 19000), ("워드프로세서", 19500),
         ("한국사능력검정 심화", 27000), ("전산회계 2급", 25000))
AGENCIES = ("전북가상검정원", "가상자격평가원")

_font: pymupdf.Font | None = None


def _text(page: pymupdf.Page, x: float, y: float, text: str, size: float = 10, align: str = "left",
          color: tuple[float, float, float] = (0, 0, 0)) -> None:
    global _font
    if align != "left":
        _font = _font or pymupdf.Font(fontfile=str(FONT_FILE))
        width = _font.text_length(text, fontsize=size)
        x = x - width if align == "right" else x - width / 2
    page.insert_text((x, y), text, fontname=FONT, fontfile=str(FONT_FILE), fontsize=size, color=color)


# ---------------------------------------------------------------------------
# 가상 값
# ---------------------------------------------------------------------------

def _name(rng: random.Random) -> str:
    return rng.choice(SURNAMES) + rng.choice(GIVEN) + rng.choice(GIVEN)


def _birth(rng: random.Random) -> date:
    return date(rng.randint(1988, 2006), rng.randint(1, 12), rng.randint(1, 28))


def _brn(rng: random.Random) -> str:
    head = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(8)]
    digits = "".join(map(str, head + [brn_check_digit(head)]))
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def _day(rng: random.Random, start: date = date(2026, 1, 5), end: date = date(2026, 10, 20)) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _dot(value: date) -> str:
    return f"{value.year}. {value.month:02d}. {value.day:02d}."


# ---------------------------------------------------------------------------
# 서류 모양. 반환: (PDF, 정답(make_gt 키), 기대 판별 종류, 일부러 넣은 결함 = 실패해야 할 검증)
# ---------------------------------------------------------------------------

def receipt_card(rng: random.Random, *, title: str = "[신용승인]", exam_items: int = 0):
    store = rng.choice(STORES["suit"])
    brn = _brn(rng)
    paid = _day(rng)
    hh, mm, ss = rng.randint(9, 20), rng.randint(0, 59), rng.randint(0, 59)
    when = rng.choice((
        f"{paid:%Y-%m-%d} {hh:02d}:{mm:02d}:{ss:02d}", f"{paid:%Y/%m/%d} {hh:02d}:{mm:02d}",
        f"{paid:%y/%m/%d} {hh:02d}:{mm:02d}", f"{paid:%Y.%m.%d} {hh:02d}:{mm:02d}",
    ))
    if exam_items:
        items = [(f"{exam} 필기", fee) for exam, fee in rng.sample(EXAMS, exam_items)]
    else:
        items = [("면접 정장 대여", rng.randrange(30000, 90001, 1000))]
    total = sum(amount for _, amount in items)
    supply = round(total / 1.1)
    doc = pymupdf.open()
    page = doc.new_page(width=227, height=340 + 16 * len(items))
    y = 28.0
    _text(page, 113, y, title, 13, "center")
    _text(page, 113, y + 17, "카드 매출전표", 10, "center")
    y += 41
    for label, value in (("가맹점명", store), ("사업자번호", brn), ("거래일시", when), ("카드종류", "가상카드"),
                         ("카드번호", "9410-12**-****-3456"), ("할부", "일시불"),
                         ("승인번호", str(rng.randint(10**7, 10**8 - 1)))):
        _text(page, 14, y, label, 9)
        _text(page, 78, y, value, 9)
        y += 15
    _text(page, 14, y, "-" * 44, 8)
    y += 14
    for name, amount in items:
        _text(page, 14, y, name, 9)
        _text(page, 213, y, f"{amount:,}", 9, "right")
        y += 16
    _text(page, 14, y, "-" * 44, 8)
    y += 14
    for label, value in (("공급가액", supply), ("부가세", total - supply)):
        _text(page, 14, y, label, 9)
        _text(page, 213, y, f"{value:,}", 9, "right")
        y += 15
    _text(page, 14, y + 4, "합계금액", 10)
    _text(page, 213, y + 4, f"{total:,}원", 11, "right")
    _text(page, 14, y + 30, "서명", 9)
    gt = {"amount": str(total), "payment_date": paid.isoformat(), "store": store, "brn": brn,
          "payment_method": "카드"}
    defects = (["not_cancelled"] if "취소" in title else []) + (["single_item"] if exam_items > 1 else [])
    return doc, gt, "receipt", defects


def receipt_simple(rng: random.Random):
    kind = rng.choice(("suit", "photo"))
    store = rng.choice(STORES[kind])
    brn = _brn(rng)
    paid = _day(rng)
    item = "면접 정장 대여" if kind == "suit" else "증명사진 촬영"
    amount = rng.randrange(30000, 90001, 1000) if kind == "suit" else rng.randrange(15000, 35001, 1000)
    doc = pymupdf.open()
    page = doc.new_page(width=420, height=595)
    _text(page, 210, 60, "영 수 증", 22, "center")
    _text(page, 40, 110, f"상호: {store}", 11)
    _text(page, 225, 110, f"사업자등록번호: {brn}", 10)
    _text(page, 40, 132, f"일자: {paid.year}년 {paid.month}월 {paid.day}일", 11)
    for x, head in ((40, "품목"), (210, "수량"), (260, "단가"), (330, "금액")):
        _text(page, x, 172, head, 10)
    _text(page, 40, 194, item, 10)
    _text(page, 214, 194, "1", 10)
    _text(page, 260, 194, f"{amount:,}", 10)
    _text(page, 330, 194, f"{amount:,}", 10)
    _text(page, 200, 244, rng.choice(("합계", "합 계", "합계 금액", "총 금액")), 12)
    _text(page, 290, 244, rng.choice((f"₩{amount:,}", f"{amount:,}원")), 12)
    _text(page, 210, 292, "위 금액을 정히 영수합니다.", 11, "center")
    gt = {"amount": str(amount), "payment_date": paid.isoformat(), "store": store, "brn": brn}
    return doc, gt, "receipt", []


def receipt_online(rng: random.Random):
    store = rng.choice(STORES["suit"] + STORES["photo"])
    brn = _brn(rng)
    paid = _day(rng)
    amount = rng.randrange(15000, 90001, 500)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _text(page, 60, 80, "결제가 완료되었습니다", 18)
    y = 130.0
    for label, value in (("주문번호", f"{paid:%Y%m%d}{rng.randint(10**6, 10**7 - 1)}"),
                         ("결제일시", f"{paid:%Y.%m.%d} {rng.randint(9, 22):02d}:{rng.randint(0, 59):02d}"),
                         ("상품명", rng.choice(("면접 정장 대여(1일)", "증명사진 촬영 패키지"))),
                         ("결제수단", "신용카드(일시불)")):
        _text(page, 60, y, label, 11)
        _text(page, 200, y, value, 11)
        y += 30
    _text(page, 60, y, "결제금액", 11)          # 값은 라벨 아래 줄 (결제 화면 배치)
    _text(page, 60, y + 22, f"{amount:,}원", 15)
    y += 62
    for label, value in (("판매자", store), ("사업자등록번호", brn)):
        _text(page, 60, y, label, 11)
        _text(page, 200, y, value, 11)
        y += 30
    gt = {"amount": str(amount), "payment_date": paid.isoformat(), "store": store, "brn": brn,
          "payment_method": "카드"}
    return doc, gt, "receipt", []


def receipt_transfer(rng: random.Random):
    studio = rng.choice(STORES["photo"])
    paid = _day(rng)
    amount = rng.randrange(15000, 35001, 1000)
    doc = pymupdf.open()
    page = doc.new_page(width=420, height=595)
    _text(page, 210, 60, "이체확인증", 20, "center")
    y = 110.0
    for label, value in (("이체일시", f"{paid:%Y-%m-%d} {rng.randint(9, 22):02d}:{rng.randint(0, 59):02d}"),
                         ("출금계좌", "가상은행 123-***-456789"), ("받는분", studio), ("입금은행", "가상은행"),
                         ("입금계좌", "987-***-654321"), ("이체금액", f"{amount:,}원"), ("수수료", "0원")):
        _text(page, 50, y, label, 11)
        _text(page, 160, y, value, 11)
        y += 26
    _text(page, 210, y + 30, "위와 같이 이체되었음을 확인합니다.", 11, "center")
    gt = {"amount": str(amount), "payment_date": paid.isoformat(), "payee": studio,
          "payment_method": "계좌이체"}
    return doc, gt, "receipt", []


def registration_only(rng: random.Random):
    exam, fee = rng.choice(EXAMS)
    when = _day(rng)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _text(page, 297, 80, "원서접수확인서", 20, "center")
    y = 140.0
    for label, value in (("수험번호", str(rng.randint(10**7, 10**8 - 1))), ("성명", _name(rng)), ("종목명", exam),
                         ("시험일자", _dot(when + timedelta(days=20))), ("접수일시", f"{when:%Y-%m-%d} 10:12"),
                         ("응시수수료", f"{fee:,}원"), ("접수상태", "접수완료")):
        _text(page, 70, y, label, 12)
        _text(page, 200, y, value, 12)
        y += 32
    return doc, {}, "unknown", ["document_type"]


def exam_admission(rng: random.Random):
    name, birth = _name(rng), _birth(rng)
    exam, _ = rng.choice(EXAMS)
    taken = _day(rng)
    issued = taken + timedelta(days=rng.randint(1, 30))
    taken_text = rng.choice((f"{_dot(taken)}", f"{taken.year}년 {taken.month}월 {taken.day}일", f"{taken:%Y-%m-%d}"))
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _text(page, 297, 90, "응 시 확 인 서", 22, "center")
    _text(page, 70, 160, "성    명", 12)
    _text(page, 160, 160, name, 12)
    _text(page, 320, 160, "생년월일", 12)
    _text(page, 400, 160, _dot(birth), 12)
    y = 196.0
    for label, value in (("수험번호", str(rng.randint(10**7, 10**8 - 1))), ("종 목 명", exam),
                         ("시험일자", taken_text), ("시험장소", "전주 가상고등학교")):
        _text(page, 70, y, label, 12)
        _text(page, 160, y, value, 12)
        y += 36
    _text(page, 297, y + 40, "위 사람은 위 시험에 응시하였음을 확인합니다.", 13, "center")
    _text(page, 297, y + 90, f"발급일자: {_dot(issued)}", 12, "center")
    _text(page, 297, y + 140, f"{rng.choice(AGENCIES)}장", 15, "center")
    gt = {"name": name, "birth_date": birth.isoformat(), "exam_name": exam, "exam_date": taken.isoformat(),
          "issue_date": issued.isoformat()}
    return doc, gt, "exam_admission", []


def exam_score(rng: random.Random):
    name, birth = _name(rng), _birth(rng)
    exam, _ = rng.choice(EXAMS)
    taken = _day(rng)
    printed = taken + timedelta(days=rng.randint(10, 40))
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _text(page, 297, 90, "성 적 통 지 서", 22, "center")
    y = 160.0
    for label, value in (("성명", name), ("생년월일", f"{birth:%Y-%m-%d}"), ("종목", exam),
                         ("시험일", f"{taken:%Y-%m-%d}"), ("점수", f"{rng.randint(40, 98)}점"),
                         ("출력일", f"{printed:%Y-%m-%d}")):
        _text(page, 80, y, label, 12)
        _text(page, 190, y, value, 12)
        y += 36
    gt = {"name": name, "birth_date": birth.isoformat(), "exam_name": exam, "exam_date": taken.isoformat(),
          "issue_date": printed.isoformat()}
    return doc, gt, "exam_score", []


def admission_ticket(rng: random.Random):
    exam, _ = rng.choice(EXAMS)
    taken = _day(rng)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _text(page, 297, 90, "수 험 표", 24, "center")
    y = 160.0
    for label, value in (("성명", _name(rng)), ("수험번호", str(rng.randint(10**7, 10**8 - 1))), ("종목명", exam),
                         ("시험일시", f"{_dot(taken)} 09:00")):
        _text(page, 80, y, label, 12)
        _text(page, 190, y, value, 12)
        y += 36
    return doc, {}, "unknown", ["document_type"]


def _interview_values(rng: random.Random) -> dict:
    when = _day(rng)
    start = rng.randint(9, 16) * 60 + rng.choice((0, 30))
    end = start + rng.choice((20, 30, 40, 60))
    return {
        "name": _name(rng), "birth": _birth(rng), "company": rng.choice(COMPANIES),
        "industry": rng.choice(INDUSTRIES), "job": rng.choice(JOBS), "place": rng.choice(PLACES),
        "when": when, "time": f"{start // 60:02d}:{start % 60:02d}~{end // 60:02d}:{end % 60:02d}",
        "confirm": when + timedelta(days=rng.choice((0, 0, 1, 2))),
    }


def _interview_gt(v: dict) -> dict:
    return {"name": v["name"], "birth_date": v["birth"].isoformat(), "company": v["company"],
            "industry": v["industry"], "interview_date": v["when"].isoformat(), "interview_time": v["time"],
            "place": v["place"], "job": v["job"], "confirm_date": v["confirm"].isoformat()}


def interview_official(rng: random.Random):
    """사업계획서 서식 위에 값을 채운다. 신청자 칸은 데모 서식 좌표를, 기업 칸은 인쇄된 라벨 위치를 쓴다."""
    v = _interview_values(rng)
    coords = json.loads(INTERVIEW_COORDS.read_text(encoding="utf-8"))["fields"]
    doc = pymupdf.open(INTERVIEW_TEMPLATE)
    page = doc[0]
    # 인쇄된 '2026. 00. 00. 00:00~00:00'은 글자층에서도 지운 뒤 값을 쓴다
    for rect in page.search_for("2026. 00. 00. 00:00~00:00"):
        page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()
    for key, value in (("name", v["name"]), ("birth", _dot(v["birth"])),
                       ("address", "전북특별자치도 전주시 가상로 12"), ("mobile", "010-0000-0000"),
                       ("email", "test@example.com")):
        _text(page, coords[key]["x"], coords[key]["y"], value, coords[key].get("size", 10))

    def baseline(anchor: str, index: int = 0) -> float:
        return page.search_for(anchor)[index].y1 - 2.4

    left, right = coords["name"]["x"], coords["birth"]["x"]
    _text(page, left, baseline("회사명"), v["company"])
    _text(page, left, baseline("소재지"), "전북특별자치도 전주시 덕진구 가상로 34")
    _text(page, left, baseline("업태/업종"), v["industry"])
    _text(page, left, baseline("담당자"), "박담당")
    _text(page, right, baseline("연락처", 1), "063-000-0000")
    _text(page, left, baseline("면접일시"), f"{_dot(v['when'])} {v['time']}")
    _text(page, left, baseline("면접장소"), v["place"])
    _text(page, left, baseline("응시직군"), v["job"])
    year = page.search_for("2026년")[0]
    _text(page, year.x1 + 12, year.y1 - 2.6, str(v["confirm"].month), 12)
    _text(page, year.x1 + 61, year.y1 - 2.6, str(v["confirm"].day), 12)
    company_label = page.search_for("회사명 :")[0]
    _text(page, company_label.x1 + 6, company_label.y1 - 2.6, v["company"], 12)
    manager_label = page.search_for("담당자 :")[0]
    _text(page, manager_label.x1 + 6, manager_label.y1 - 2.6, "박담당", 12)
    stamp = page.search_for("(서명/인)")[0]
    page.draw_circle(((stamp.x0 + stamp.x1) / 2, (stamp.y0 + stamp.y1) / 2), 13, color=(0.85, 0.1, 0.1), width=1.4)
    return doc, _interview_gt(v), "interview_confirm", []


def interview_company(rng: random.Random):
    """기업 자체 양식."""
    v = _interview_values(rng)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _text(page, 297, 90, "면 접 확 인 서", 22, "center")
    y = 160.0
    for text in (f"성명: {v['name']}", f"생년월일: {v['birth']:%Y.%m.%d}", f"기업명: {v['company']}",
                 f"업종: {v['industry']}", f"면접일자: {v['when'].year}년 {v['when'].month}월 {v['when'].day}일",
                 f"면접시간: {v['time']}", f"면접장소: {v['place']}", f"지원분야: {v['job']}"):
        _text(page, 80, y, text, 12)
        y += 32
    _text(page, 297, y + 30, "위 사람이 당사 채용 면접에 참석하였음을 확인합니다.", 13, "center")
    confirm = v["confirm"]
    _text(page, 297, y + 80, f"{confirm.year}년 {confirm.month}월 {confirm.day}일", 13, "center")
    _text(page, 297, y + 130, f"{v['company']} 대표 (인)", 14, "center")
    return doc, _interview_gt(v), "interview_confirm", []


LAYOUTS = {
    "receipt_card": ("receipt", receipt_card),
    "receipt_simple": ("receipt", receipt_simple),
    "receipt_online": ("receipt", receipt_online),
    "receipt_transfer": ("receipt", receipt_transfer),
    "receipt_card_cancel": ("receipt", lambda rng: receipt_card(rng, title="[승인취소]")),
    "receipt_card_bulk": ("receipt", lambda rng: receipt_card(rng, exam_items=2)),
    "receipt_registration_only": ("receipt", registration_only),
    "exam_admission": ("exam_admission", exam_admission),
    "exam_score": ("exam_score", exam_score),
    "exam_admission_ticket": ("exam_admission", admission_ticket),
    "interview_official": ("interview_confirm", interview_official),
    "interview_company": ("interview_confirm", interview_company),
}


# ---------------------------------------------------------------------------
# 화질 조건
# ---------------------------------------------------------------------------

def _render(doc: pymupdf.Document, dpi: int) -> list[tuple[Image.Image, pymupdf.Rect]]:
    out = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        out.append((Image.frombytes("RGB", (pix.width, pix.height), pix.samples), page.rect))
    return out


def _image_pdf(images: list[tuple[Image.Image, pymupdf.Rect]], path: Path, fmt: str = "PNG") -> None:
    out = pymupdf.open()
    for image, rect in images:
        buffer = io.BytesIO()
        image.save(buffer, format=fmt, quality=90)
        page = out.new_page(width=rect.width, height=rect.height)
        page.insert_image(page.rect, stream=buffer.getvalue())
    out.save(path, garbage=3, deflate=True)  # deflate 없이 저장하면 PNG가 무압축(장당 10MB 넘음)으로 들어간다


def _scan(image: Image.Image, rng: random.Random) -> Image.Image:
    gray = image.convert("L").filter(ImageFilter.GaussianBlur(0.7))
    gray = gray.rotate(rng.uniform(-1.2, 1.2), resample=Image.Resampling.BICUBIC, fillcolor=255)
    gray = ImageEnhance.Contrast(gray).enhance(1.15)
    buffer = io.BytesIO()
    gray.save(buffer, format="JPEG", quality=60)
    return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")


def _photo(image: Image.Image, rng: random.Random) -> Image.Image:
    tilted = image.rotate(rng.uniform(-3, 3), resample=Image.Resampling.BICUBIC, expand=True,
                          fillcolor=(236, 233, 226))
    desk = Image.new("RGB", (int(tilted.width * 1.25), int(tilted.height * 1.18)), (118, 96, 78))
    desk.paste(tilted, ((desk.width - tilted.width) // 2, (desk.height - tilted.height) // 2))
    desk = Image.blend(desk, Image.new("RGB", desk.size, (255, 226, 190)), 0.10)
    desk = Image.blend(desk, Image.effect_noise(desk.size, 22).convert("RGB"), 0.05)
    desk = desk.filter(ImageFilter.GaussianBlur(0.8))
    scale = 2000 / max(desk.size)
    return desk.resize((round(desk.width * scale), round(desk.height * scale)), Image.Resampling.LANCZOS)


def _save(doc: pymupdf.Document, condition: str, stem: str, out: Path, rng: random.Random) -> str:
    if condition == "text":
        name = f"{stem}.pdf"
        doc.subset_fonts()
        doc.save(out / name, garbage=3, deflate=True)
    elif condition == "clean":
        name = f"{stem}.pdf"
        _image_pdf(_render(doc, 200), out / name)
    elif condition == "scan":
        name = f"{stem}.pdf"
        _image_pdf([(_scan(image, rng), rect) for image, rect in _render(doc, 200)], out / name, "JPEG")
    elif condition == "lowres":
        name = f"{stem}.pdf"
        _image_pdf(_render(doc, 100), out / name)
    elif condition == "photo":
        name = f"{stem}.jpg"
        image, _ = _render(doc, 200)[0]
        _photo(image, rng).save(out / name, format="JPEG", quality=82)
    else:
        raise ValueError(f"알 수 없는 조건: {condition}")
    return name


def generate(out: Path, n: int = 2, seed: int = 7, conditions: tuple[str, ...] = CONDITIONS) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    files = []
    for layout, (doc_name, make) in LAYOUTS.items():
        for index in range(1, n + 1):
            source, gt, expect_type, defects = make(rng)
            pdf_bytes = source.tobytes()
            for condition in conditions:
                doc = pymupdf.open("pdf", pdf_bytes)  # 조건마다 같은 원본에서 시작
                name = _save(doc, condition, f"{layout}_{index:02d}__{condition}", out, rng)
                gt_name = f"{Path(name).stem}.gt.json"
                (out / gt_name).write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
                files.append({"file": name, "gt_file": gt_name, "doc": doc_name, "layout": layout,
                              "condition": condition, "expect_type": expect_type, "expect_failed": defects,
                              "gt": gt})
    manifest = {"generator": "engine_v2.tools.make_job_docs", "seed": seed, "n": n,
                "conditions": list(conditions), "files": files}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--n", type=int, default=2, help="서류 모양마다 만들 건수")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    args = ap.parse_args()
    conditions = tuple(item for item in args.conditions.split(",") if item)
    unknown = set(conditions) - set(CONDITIONS)
    if unknown:
        raise SystemExit(f"알 수 없는 조건: {sorted(unknown)} (가능: {', '.join(CONDITIONS)})")
    manifest = generate(args.out, args.n, args.seed, conditions)
    counts = Counter(entry["layout"] for entry in manifest["files"])
    print(f"합성 서류 {len(manifest['files'])}개 → {args.out}")
    for layout, count in counts.items():
        print(f"  {layout}: {count}")
    print("다음: python -m engine_v2.tools.job_docs_bench  (OCR 엔진이 있으면 --engine rapidocr 등)")


if __name__ == "__main__":
    main()
