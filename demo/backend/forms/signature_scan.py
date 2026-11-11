"""Private storage and image cleanup for applicant handwritten signature scans."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

FAINT_SIGNATURE_MESSAGE = "서명이 잘 보이지 않습니다. 흰 종이에 진하게 쓴 서명을 다시 올려 주세요."
MAX_IMAGE_PIXELS = 20_000_000


def signature_scan_paths(storage: Path, application_no: str) -> tuple[Path, Path]:
    folder = storage / "signatures" / application_no
    return folder / "scan-original", folder / "scan-processed.png"


def delete_signature_scan(storage: Path, application_no: str) -> None:
    original_base, processed = signature_scan_paths(storage, application_no)
    for candidate in original_base.parent.glob("scan-original.*"):
        candidate.unlink(missing_ok=True)
    processed.unlink(missing_ok=True)


def process_signature_scan(raw: bytes) -> bytes:
    """Orient, remove paper, crop ink, and return a transparent PNG."""
    try:
        with Image.open(BytesIO(raw)) as opened:
            if opened.format not in {"JPEG", "PNG"}:
                raise ValueError("JPG 또는 PNG 이미지 파일을 올려 주세요.")
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise ValueError("이미지 크기가 너무 큽니다.")
            image = ImageOps.exif_transpose(opened)
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("이미지 크기가 너무 큽니다.")
            gray = ImageOps.grayscale(image).convert("L")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("JPG 또는 PNG 이미지 파일을 확인해 주세요.") from exc

    # 밝은 종이와 연필 자국은 제거한다. 어두운 획은 불투명하게 보존한다.
    alpha_lut = [max(0, min(255, round((242 - value) * 255 / 150))) for value in range(256)]
    alpha = gray.point(alpha_lut)
    histogram = gray.histogram()
    ink_pixels = sum(histogram[:238])
    strong_ink = sum(histogram[:151])
    if ink_pixels < 30 or strong_ink < 20:
        raise ValueError(FAINT_SIGNATURE_MESSAGE)

    bounds = gray.point([255 if value < 238 else 0 for value in range(256)]).getbbox()
    if bounds is None:
        raise ValueError(FAINT_SIGNATURE_MESSAGE)
    left, top, right, bottom = bounds
    pad = max(2, round(max(right - left, bottom - top) * 0.025))
    left, top = max(0, left - pad), max(0, top - pad)
    right, bottom = min(gray.width, right + pad), min(gray.height, bottom + pad)
    cropped_alpha = alpha.crop((left, top, right, bottom))
    signature = Image.new("RGBA", cropped_alpha.size, (20, 24, 32, 0))
    signature.putalpha(cropped_alpha)
    output = BytesIO()
    signature.save(output, format="PNG", optimize=True)
    return output.getvalue()
