"""OCR 어댑터: 엔진마다 다른 출력을 하나의 형식(OcrWord)으로 통일한다.

후보
- applevision : macOS 내장 Vision (pip install ocrmac). 맥 전용 → 기준선용, 서버 배포 불가
- easyocr     : pip install easyocr (torch 포함). 리눅스 배포 가능
- paddle      : pip install paddlepaddle paddleocr. 리눅스 배포 가능, 설치 까다로움

모든 엔진은 로컬에서만 돈다. 서류 이미지를 외부로 보내지 않는다.
엔진 라이브러리는 실제로 쓸 때만 import 한다 (설치 안 된 엔진이 있어도 나머지는 동작).
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field


@dataclass
class OcrWord:
    text: str
    confidence: float                          # 0~1
    bbox_px: tuple[float, float, float, float]  # 좌상단 원점 픽셀 (x0, y0, x1, y1)


@dataclass
class OcrResult:
    engine: str
    words: list[OcrWord] = field(default_factory=list)
    elapsed_sec: float = 0.0
    error: str | None = None

    @property
    def text(self) -> str:
        """위→아래, 왼→오른 순서로 이어 붙인 전체 텍스트."""
        ws = sorted(self.words, key=lambda w: (round(w.bbox_px[1] / 15), w.bbox_px[0]))
        return " ".join(w.text for w in ws)


def _with_tempfile(png: bytes, fn):
    """일부 엔진은 파일 경로만 받는다. 임시파일을 쓰고 반드시 지운다 (개인정보)."""
    fd, path = tempfile.mkstemp(suffix=".png")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(png)
        return fn(path)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# 엔진별 구현
# ---------------------------------------------------------------------------

def _run_applevision(png: bytes, size: tuple[int, int]) -> list[OcrWord]:
    from ocrmac import ocrmac

    w, h = size

    def run(path):
        return ocrmac.OCR(path, language_preference=["ko-KR", "en-US"]).recognize()

    out = []
    for text, conf, (x, y, bw, bh) in _with_tempfile(png, run):
        # Vision 좌표: 0~1 정규화, 좌하단 원점 → 좌상단 원점 픽셀로 변환
        x0, x1 = x * w, (x + bw) * w
        y0, y1 = (1 - y - bh) * h, (1 - y) * h
        out.append(OcrWord(text, float(conf), (x0, y0, x1, y1)))
    return out


_easyocr_reader = None


def _run_easyocr(png: bytes, size) -> list[OcrWord]:
    global _easyocr_reader
    import easyocr

    if _easyocr_reader is None:
        _easyocr_reader = easyocr.Reader(["ko", "en"], gpu=False)
    out = []
    for poly, text, conf in _easyocr_reader.readtext(png):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        out.append(OcrWord(text, float(conf), (min(xs), min(ys), max(xs), max(ys))))
    return out


_paddle = None


def _run_paddle(png: bytes, size) -> list[OcrWord]:
    global _paddle
    from paddleocr import PaddleOCR

    if _paddle is None:
        try:  # PaddleOCR 3.x
            _paddle = PaddleOCR(
                lang="korean",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:  # 2.x
            _paddle = PaddleOCR(lang="korean", use_angle_cls=False, show_log=False)

    def run(path):
        if hasattr(_paddle, "predict"):
            return ("v3", _paddle.predict(path))
        return ("v2", _paddle.ocr(path, cls=False))

    ver, res = _with_tempfile(png, run)
    out = []
    if ver == "v3":
        for r in res:
            texts, scores = r["rec_texts"], r["rec_scores"]
            polys = r.get("rec_polys") if hasattr(r, "get") else r["rec_polys"]
            for t, s, poly in zip(texts, scores, polys):
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                out.append(OcrWord(t, float(s), (min(xs), min(ys), max(xs), max(ys))))
    else:
        for line in (res[0] or []):
            poly, (t, s) = line
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            out.append(OcrWord(t, float(s), (min(xs), min(ys), max(xs), max(ys))))
    return out


ENGINES = {
    "applevision": _run_applevision,
    "easyocr": _run_easyocr,
    "paddle": _run_paddle,
}


def run_ocr(engine: str, png: bytes, size: tuple[int, int]) -> OcrResult:
    if engine not in ENGINES:
        raise ValueError(f"알 수 없는 엔진: {engine} (가능: {list(ENGINES)})")
    t0 = time.perf_counter()
    try:
        words = ENGINES[engine](png, size)
        return OcrResult(engine, words, time.perf_counter() - t0)
    except ImportError as e:
        return OcrResult(engine, error=f"미설치: {e.name}")
    except Exception as e:  # noqa: BLE001 — 비교 도구이므로 엔진 오류는 기록만
        return OcrResult(engine, elapsed_sec=time.perf_counter() - t0, error=f"{type(e).__name__}: {e}")
