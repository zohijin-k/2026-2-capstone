"""개인정보 파일 위치. 실행 위치와 상관없이 항상 engine_v2/data/private/ 를 가리킨다.

이 폴더는 engine_v2/.gitignore 와 루트 .gitignore 가 둘 다 막는다 — 절대 커밋되지 않는다.
"""

from pathlib import Path

PRIVATE_DIR = Path(__file__).resolve().parent / "data" / "private"
