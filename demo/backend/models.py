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
    """업로드 서류. P2에서 채운다."""

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(index=True, foreign_key="application.id")
    slot_key: str
    doc_type: Optional[str] = None
    file_path: str
    file_format: str
    declared_issue_date: Optional[date] = None
    ocr_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    #: PASS | FAIL | NEEDS_REVIEW
    stage1_status: Optional[str] = None
    findings_json: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    uploaded_at: datetime = Field(default_factory=datetime.now)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
