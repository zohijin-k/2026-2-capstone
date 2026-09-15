"""원본 파일 인라인 스트리밍 (R4.1).

이 파일의 금칙은 하나다 — **다운로드 경로를 만들지 않는다.**

담당자가 심사 1건을 처리하는 동안 파일 다운로드는 0회여야 한다. 원본이 로컬
디스크로 내려가는 순간 보관·파기 책임이 개인 PC로 옮겨가고, "브라우저 안에서
끝낸다"는 이 데모의 논점 자체가 사라진다.

그래서 `Content-Disposition`은 **항상 `inline`**이다. 그 외의 값을 쓰는 분기는 이
모듈 어디에도 없고, 추가해서도 안 된다. 프론트에도 파일 저장 링크나 blob 저장이
없다 — 뷰어(pdf.js / img 태그)가 이 URL을 직접 읽는다.

검증 스크립트(`tests/run_p4_scenarios.py`)가 `demo/` 소스 전체를 훑어 파일 저장을
유발하는 토큰이 하나도 없는지 정적으로도 확인한다.
"""

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..models import Document, get_session
from .common import STORAGE

router = APIRouter(prefix="/api/files", tags=["files"])

#: 확장자 → MIME. 브라우저가 인라인으로 렌더할 수 있는 형식만 둔다.
#: 알 수 없는 형식을 application/octet-stream으로 내보내면 브라우저가 곧바로
#: 파일 저장을 시작한다 — 그래서 목록에 없는 형식은 아예 거절한다.
INLINE_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}

#: 반드시 이 값이어야 한다. 검증 스크립트가 응답 헤더로 직접 확인한다.
DISPOSITION = "inline"


def _resolve(file_path: str) -> Path:
    """DB의 상대 경로 → 실제 파일. 저장소 밖으로 나가는 경로는 막는다."""
    root = STORAGE.resolve()
    target = (STORAGE.parent / file_path).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(400, "허용되지 않은 파일 경로입니다.")
    if not target.is_file():
        raise HTTPException(404, "원본 파일을 찾을 수 없습니다.")
    return target


@router.get("/{document_id}")
def stream_document(document_id: int) -> FileResponse:
    """업로드 원본을 브라우저 안에서 그대로 연다.

    `review_payload.documents[].file_ref`가 가리키는 주소가 이것이다
    (`engine_adapter.inject_file_refs`).
    """
    with get_session() as s:
        row = s.get(Document, document_id)
        if row is None:
            raise HTTPException(404, "서류를 찾을 수 없습니다.")
        file_path = row.file_path
        file_format = (row.file_format or "").lower()

    media_type = INLINE_MEDIA_TYPES.get(file_format)
    if media_type is None:
        raise HTTPException(
            415, f"브라우저에서 바로 볼 수 없는 형식입니다: {file_format or '알 수 없음'}"
        )

    target = _resolve(file_path)
    # 한글 파일명이 그대로 들어간다. RFC 5987 표기를 함께 실어 브라우저가 깨진
    # 이름으로 저장 대화상자를 띄우는 일을 막는다.
    name = quote(target.name)
    return FileResponse(
        target,
        media_type=media_type,
        headers={
            "Content-Disposition": f"{DISPOSITION}; filename*=UTF-8''{name}",
            # 시연 중 캐시된 예전 파일이 보이면 판독 결과와 원본이 어긋나 보인다.
            "Cache-Control": "no-store",
        },
    )
