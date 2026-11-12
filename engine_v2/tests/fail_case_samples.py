"""Authored fictitious values with layout_shape5 word bands; never load source files."""
from datetime import date
import pymupdf
from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.pipeline.preprocess import PageImage, PageSource
from engine_v2.tests.nhis_form_samples import coordinate_page, insurance_portal_cells
from engine_v2.tests.p2_payment_samples import payment
from engine_v2.tests.p2_form_samples import page as form_page

NAME = "가짜이름"
BIRTH = date(1990, 1, 1)


def shaped_page(cells, size=(595, 842), index=0, text=True):
    words = [OcrWord(t, c, (x0, y0, x1, y1)) for x0, y0, x1, y1, t, c in cells]
    p = PageImage(index, PageSource.TEXT_LAYER if text else PageSource.UPLOAD,
                  (595, 842), pixel_size=size, dpi=300 if text else None)
    return p, OcrResult("text_layer" if text else "own", words)


def daily(*, months=("2025-10", "2025-12", "2026-02"), copies=True):
    result = []
    for insurance in (("산재", "고용") if copies else ("산재",)):
        cells = [(190, 50, 300, 71, f"[√]{insurance}보험", 1),
                 (112, 75, 485, 96, "일용근로·노무제공내역서(근로자/노무제공자)", 1),
                 (55,105,93,117,"발급번호",1),(111,105,222,117,"0000-0000-000000000",1),
                 (234,105,280,117,"발급일자",1),(292,105,380,117,"2026년03월03일",1),
                 (60,134,90,146,"신청인",1),(122,134,143,146,"성명",1),
                 (224,134,270,146,NAME,1),(331,134,380,146,"생년월일",1),
                 (432,134,520,146,"1990년01월01일",1),
                 (55,168,100,180,"조회기간",1),(264,158,334,170,"2025년09월~",1),
                 (337,158,407,170,"2026년03월",1),
                 (49,215,67,227,"번호",1),(90,206,108,218,"근로",1),(90,215,108,227,"년월",1),
                 (145,210,205,222,"사업장명",1),(255,206,273,218,"근로",1),
                 (255,215,273,227,"일자",1),(307,206,325,218,"근로",1),
                 (307,215,325,227,"일수",1),(364,210,410,222,"임금총액",1),
                 (442,210,488,222,"보수총액",1),(512,206,546,218,"근로자",1),
                 (517,215,542,227,"구분",1)]
        for i, month in enumerate(months):
            y = 246 + i * 29
            cells += [(55,y,61,y+12,str(i+1),1),(79,y,119,y+12,month.replace("-","/"),1),
                      (128,y,195,y+12,"가짜사업장",1),(241,y-7,288,y+5,"1,2,3,",1),
                      (244,y+3,284,y+15,"4,5",1),(323,y,329,y+12,"5",1),(331,y,340,y+12,"일",1),
                      (358,y,405,y+12,"500,000",1),(408,y,417,y+12,"원",1),
                      (436,y,483,y+12,"500,000",1),(486,y,495,y+12,"원",1),
                      (512,y,546,y+12,"근로자",1)]
        cells.append((220,600,400,612,"이하 여백",1))
        result.append(shaped_page(cells,index=len(result)))
        # The second page of each insurance copy contains confirmation only.
        result.append(shaped_page([(220,162,380,174,"위와 같이 내역을 확인합니다.",1),
                                  (255,191,360,203,"2026년03월03일",1),
                                  (226,237,390,255,"근로복지공단이사장",1)],index=len(result)))
    return result


def mixed_portal():
    cells = [(x,y,"2026.01.01" if t == "2020.01.01" else t) for x,y,t in insurance_portal_cells()]
    p,r = coordinate_page(cells)
    return [(p,r)] + [shaped_page([(200,600,900,660,"가짜 첨부문서",.99)],
                                 size=(2480,3508),index=i,text=False) for i in (1,2)]


def missing_address_dates(*, header=True):
    # Both date headers exist, but body cells are empty (case 5).
    cells = [(130,87,399,132,"주민등록표",.96),(180,133,218,161,"초",1),
             (309,124,399,165,"본)",.97),(563,164,730,188,"2026년03월03일",.99),
             (773,43,802,64,"1/1",1),(85,232,177,258,"성명(한자)",.94),
             (218,231,310,259,NAME,1),(529,232,628,257,"주민등록번호",1),
             (670,235,810,254,"900101-1******",.99)]
    if header:
        cells += [(68,428,108,453,"번호",1),(236,429,399,452,"주소",1),
                  (530,417,620,443,"발  생일",.84),(607,417,745,443,"신 고 일",.95),
                  (783,419,901,440,"세대주및관계",1)]
    for i in range(3):
        y=467+i*46
        cells += [(80,y+12,96,y+31,str(i+1),1),(124,y,386,y+20,"전북특별자치도 가짜시 가짜로 0",.99),
                  (707,y+20,747,y+44,"전입",.97)]
    return [shaped_page(cells,size=(970,1282),text=False)]


def tiny_unknown():
    from .fail_case_tiny_geometry import TINY_WORDS
    return [shaped_page(TINY_WORDS,size=(586,709),text=False)]


def missing_payment_months():
    cells,size=payment()
    # Keep all actual positive amounts inside the printed query range. The
    # annual template still prints twelve month labels with outside zeros.
    authored = []
    for x0,y0,x1,y1,text,c in cells:
        if text in {"보수외", "월별"}:
            continue
        if "2025년 10월" in text:
            text = "2024년 01월 ~ 2024년 09월 납부내역"
        if 962 <= y0 <= 1660 and x0 > 300:
            row = round((y0 - 962) / 59) + 1
            if row in (10,11,12):
                text = "0"
            elif row in (1,2,3) and text == "0":
                text = str({1:100000,2:20000,3:30000}[row] // (10 if 550 < x0 < 700 or 1350 < x0 < 1500 else 1))
        authored.append((x0,y0,x1,y1,text,c))
    cells = authored
    return [form_page(cells,size=size)]


def encrypted_pdf(path):
    with pymupdf.open() as doc:
        doc.new_page().insert_text((30,30), "FAKE ENCRYPTED DOCUMENT")
        doc.save(path,encryption=pymupdf.PDF_ENCRYPT_AES_256,user_pw="FAKE-password",owner_pw="FAKE-owner")
    return path
