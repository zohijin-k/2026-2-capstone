"""시나리오 테스트 공통 준비."""

from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "samples"


def ensure_demo_samples() -> None:
    """깨끗한 체크아웃에서 첫 시나리오 실행 전 시연 PDF를 생성한다."""
    if SAMPLES_DIR.is_dir() and any(SAMPLES_DIR.glob("*.pdf")):
        return
    from demo.fixtures.make_samples import main as make_samples

    make_samples()


ensure_demo_samples()
