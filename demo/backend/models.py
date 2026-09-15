"""데모 DB 스키마 (SQLite + SQLModel).

서식 입력값은 JSON 컬럼 하나에 통째로 넣는다. 데모 단계에서 서식 필드가 계속
바뀌는데 그때마다 마이그레이션을 하는 건 낭비다. 심사·집계에 실제로 쓰이는
값만 P3에서 별도 컬럼으로 승격한다.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine

DB_PATH = Path(__file__).resolve().parents[1] / "demo.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    #: 엔진 `Applicant.applicant_id` 와 같은 키. 담당자가 원본과 매칭하는 유일 키.
    application_no: str = Field(index=True, unique=True)
    program_code: str = Field(index=True)
    #: draft | submitted | reviewing | decided
    status: str = Field(default="draft", index=True)
    #: 서식1 입력값 전체
    form1_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    #: 서식2 자가진단 답변 {문항번호: "예"|"아니오"}
    self_check_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    #: 서식5 입력값(서명 이미지는 consent 테이블에 별도 저장)
    form5_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    #: 서류 체크리스트를 조립하는 입력 (근로유형·사업장 수·자필서명 여부)
    doc_context_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None


class Consent(SQLModel, table=True):
    """동의 이력.

    수기 서명 없이도 '누가 언제 무엇에 동의했는지'를 남기는 것이 이 테이블의
    존재 이유다. 서식3·4는 체크만, 서식5는 서명 이미지까지 함께 남긴다.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(index=True, foreign_key="application.id")
    #: privacy | unique_id | third_party | admin_info
    consent_type: str
    agreed: bool
    #: 서식5 전자서명 PNG 경로 (storage/ 하위). 자필 업로드면 그 파일 경로.
    signature_path: Optional[str] = None
    #: electronic | handwritten
    signature_kind: Optional[str] = None
    agreed_at: datetime = Field(default_factory=datetime.now)
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


class Document(SQLModel, table=True):
    """업로드 서류 한 건.

    같은 `doc_type`이 여러 슬롯에 올 수 있어(복수 사업장 근로확인서류) 슬롯 키를
    따로 둔다. 병합 PDF를 페이지 단위로 쪼갠 경우 `page_index`와
    `source_file_path`로 원본을 되짚는다.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(index=True, foreign_key="application.id")
    #: 체크리스트 슬롯 식별자. 아직 배정되지 않은 병합 페이지는 "unassigned".
    slot_key: str
    #: OCR이 판별한 실제 서류 종류
    doc_type: Optional[str] = None
    #: 이 슬롯이 요구하는 서류 종류 (오분류 판정의 기준값)
    expected_doc_type: Optional[str] = None
    file_path: str
    file_format: str
    declared_issue_date: Optional[date] = None
    ocr_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    #: PASS | FAIL | NEEDS_REVIEW
    stage1_status: Optional[str] = None
    findings_json: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    #: 병합 PDF에서 쪼갠 경우 원본에서의 페이지 번호(0-based)
    page_index: Optional[int] = None
    #: 병합 PDF 원본 경로
    source_file_path: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.now)


class Review(SQLModel, table=True):
    """제출 1건의 심사 결과.

    담당자 화면(`09-16-demo-officer`)이 읽는 유일한 테이블이다. 엔진이 만든
    `review_payload`와 데모가 채점한 `ScoreSheet`를 같이 들고 있어야, 담당자가
    "판정 사유"와 "점수 근거"를 한 화면에서 원본과 대조할 수 있다.

    ⚠️ 점수는 신청자에게 노출하지 않는다 (공고문: "평가결과는 공개하지 않음").
    마이페이지 응답(`/status`)은 이 테이블의 점수 컬럼을 절대 싣지 않는다.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(index=True, foreign_key="application.id")
    #: PASS | FAIL | NEEDS_REVIEW (엔진 최종 판정)
    final_status: str = Field(index=True)
    stage1_status: Optional[str] = None
    stage2_status: Optional[str] = None
    #: `rules/scoring.ScoreSheet.as_dict()` — 항목별 basis·source_doc·bbox 포함
    score_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    total_score: Optional[int] = Field(default=None, index=True)
    #: 동점자 정렬 키 (시행지침 우선순위 ①~④)
    tiebreak_json: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    #: 엔진 `run_pipeline` 결과의 심사 요청 패키지 (+ file_ref 주입본)
    review_payload_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    #: 담당자 판단 — 여기부터는 officer 태스크가 채운다.
    officer_role: Optional[str] = None
    officer_decision: Optional[str] = None
    officer_memo: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)


#: 병합 PDF 페이지 중 어느 슬롯에도 배정되지 않은 것.
UNASSIGNED_SLOT = "unassigned"

#: 신청 상태. 마이페이지 진행 표시의 단일 소스다.
STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_REVIEWING = "reviewing"
STATUS_DECIDED = "decided"


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """데모용 초경량 마이그레이션.

    SQLModel의 `create_all`은 이미 있는 테이블에 컬럼을 추가해 주지 않는다. 데모
    DB를 지웠다 다시 만들면 P1에서 작성한 신청 건이 날아가므로, 빠진 컬럼만
    ALTER로 붙인다. 정식 마이그레이션 도구는 데모 범위 밖이다.
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table.name})"))
            }
            if not existing:
                continue
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type}"
                conn.execute(text(ddl))
        conn.commit()


def get_session() -> Session:
    return Session(engine)
