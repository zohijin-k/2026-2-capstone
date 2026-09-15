"""데모 사이트 백엔드 엔트리.

기동 (저장소 루트에서):
    uvicorn demo.backend.main:app --reload --port 8000

`demo.backend`는 패키지로 동작한다. 루트에서 띄워야 engine_adapter가 저장소
루트를 sys.path에 올려 `engine/`을 import 할 수 있다.
"""

from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import applications, documents, files, forms, officer, review, subsidy
from .engine_adapter import apply_runtime_overrides
from .models import init_db
from .rules.programs import PROGRAMS, get_program
from .rules.self_check import item_numbers
from .rules.subsidy import catalog


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 엔진 config를 공고문 실제값으로 덮어쓴다. 엔진 파일은 건드리지 않는다.
    apply_runtime_overrides()
    init_db()
    yield


app = FastAPI(
    title="전북청년 두배적금·취업지원패키지 신청서류 자동 검토 시스템 (데모)",
    version="0.1.0",
    lifespan=lifespan,
)

# 데모는 vite dev 서버(5173)에서 호출한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(applications.router)
app.include_router(documents.router)
# 취업지원패키지 지원 항목 선택 + 실비 계산(P5). 사업이 두 개가 되는 지점이다.
app.include_router(subsidy.router)
app.include_router(review.router)
# 작성 서식 PDF 내보내기(P7, 선택). 여기도 inline 으로만 나간다.
app.include_router(forms.router)
# 담당자 심사 화면(P4). 원본은 files 라우터가 inline으로만 흘린다 — 다운로드 경로는 없다.
app.include_router(officer.router)
app.include_router(files.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/programs")
def list_programs() -> list[dict]:
    """사업 목록 + 신청기간 + 정원.

    랜딩 화면의 사업 선택과, 사업별 분기(연령 기준·서류 인정일·보완 정책)의
    단일 소스다.
    """
    return [_serialize(code) for code in PROGRAMS]


@app.get("/api/programs/{code}")
def get_program_detail(code: str) -> dict:
    return _serialize(code)


def _serialize(code: str) -> dict:
    program = get_program(code)
    data = asdict(program)
    data["allows_supplement"] = program.allows_supplement
    data["is_first_come"] = program.is_first_come
    data["quota_total"] = program.quota_total
    #: 화면이 몇 문항을 물어야 하는지. 두배적금 8문항 / 취업패키지 2문항.
    data["self_check_items"] = item_numbers(code)
    #: 지원 항목 목록. 금액·횟수·추가서류가 전부 여기서 나간다.
    data["subsidy_catalog"] = catalog() if program.has_subsidy_items else None
    return data
