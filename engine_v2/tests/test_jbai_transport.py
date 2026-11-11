"""전북AI 전송 형식(JPEG)·주민번호 즉시 가림·시간 초과 분류. 실제 네트워크는 쓰지 않는다."""

from __future__ import annotations

import base64
import io
import json
import os
import socket
import urllib.error
from pathlib import Path

import pytest
from PIL import Image

from ..pipeline import jbai_ocr

JPEG_PREFIX = "data:image/jpeg;base64,"


def configure(monkeypatch):
    monkeypatch.setenv("JBAI_API_KEY", "fake-jbai-test-key")
    monkeypatch.setenv("JBAI_BASE_URL", "https://ocr.example.invalid/open-api/v1")
    monkeypatch.delenv("JBAI_ALLOW_REAL_DOCS", raising=False)
    monkeypatch.setattr(jbai_ocr._RATE_LIMITER, "acquire", lambda: None)

    def no_network(*_args, **_kwargs):
        raise AssertionError("테스트에서 실제 네트워크를 열면 안 됩니다.")

    monkeypatch.setattr(jbai_ocr.urllib.request, "urlopen", no_network)


def recorder(monkeypatch, content: str = "ok"):
    sent: list[dict] = []

    def fake_post(request, timeout):
        payload = json.loads(request.data)
        parts = payload["messages"][0]["content"]
        url = parts[1]["image_url"]["url"]
        sent.append({"task": parts[0]["text"], "url": url, "timeout": timeout,
                     "image": base64.b64decode(url.split(",", 1)[1]) if url.startswith(JPEG_PREFIX) else b""})
        body = {"choices": [{"message": {"content": content}}]}
        return 200, json.dumps(body).encode(), {}

    monkeypatch.setattr(jbai_ocr, "_http_post", fake_post)
    return sent


def _pdf(path: Path, pages: int = 2) -> Path:
    import pymupdf

    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page(width=300, height=400)
        page.draw_rect(pymupdf.Rect(20, 20, 120, 80), color=(1, 0, 0), fill=(0, 0, 1))
        page.insert_text((30, 120), f"SYNTHETIC PAGE {index + 1}")
    document.save(path)
    document.close()
    return path


def _about_200dpi(size: tuple[int, int], page_pt: tuple[int, int]) -> bool:
    """PyMuPDF는 픽셀 크기를 올림하므로 1px 차이는 허용한다."""
    return all(abs(px - pt * 200 / 72) <= 1 for px, pt in zip(size, page_pt))


def test_pdf_pages_are_sent_as_200dpi_rgb_jpeg(tmp_path: Path, monkeypatch):
    configure(monkeypatch)
    sent = recorder(monkeypatch)

    result = jbai_ocr.run_jbai_pdf_pair(_pdf(tmp_path / "synthetic.pdf"))

    assert len(result.pages) == 2
    assert [item["task"] for item in sent] == ["OCR:", "Table Recognition:"] * 2
    for item in sent:
        assert item["url"].startswith(JPEG_PREFIX)
        assert item["image"][:2] == b"\xff\xd8"
        with Image.open(io.BytesIO(item["image"])) as image:
            assert image.format == "JPEG"
            assert image.mode == "RGB"
            assert _about_200dpi(image.size, (300, 400))


def test_render_helper_returns_jpeg_bytes(tmp_path: Path):
    rendered = jbai_ocr.render_pdf_pages_200dpi(_pdf(tmp_path / "synthetic.pdf", pages=1))
    index, image, size = rendered[0]
    assert index == 0 and image[:2] == b"\xff\xd8" and _about_200dpi(size, (300, 400))


def test_photo_with_alpha_is_converted_to_rgb_jpeg(tmp_path: Path, monkeypatch):
    configure(monkeypatch)
    sent = recorder(monkeypatch)
    photo = tmp_path / "photo.png"
    Image.new("RGBA", (64, 48), (0, 0, 0, 0)).save(photo)  # 완전 투명 → 흰 바탕이어야 한다

    result = jbai_ocr.run_jbai_file_pair(photo)

    assert len(result.pages) == 1 and len(sent) == 2
    for item in sent:
        assert item["url"].startswith(JPEG_PREFIX)
        assert item["image"][:2] == b"\xff\xd8"
        with Image.open(io.BytesIO(item["image"])) as image:
            assert image.mode == "RGB" and image.size == (64, 48)
            assert min(image.getpixel((32, 24))) > 240


def test_size_limit_is_checked_on_jpeg_bytes(tmp_path: Path, monkeypatch):
    configure(monkeypatch)
    sent = recorder(monkeypatch)
    photo = tmp_path / "noise.png"
    Image.frombytes("RGB", (256, 256), os.urandom(256 * 256 * 3)).save(photo)
    jpeg, _ = jbai_ocr.image_file_to_jpeg(photo)
    assert photo.stat().st_size > len(jpeg)

    monkeypatch.setattr(jbai_ocr, "MAX_IMAGE_BYTES", len(jpeg))
    jbai_ocr.run_jbai_file_pair(photo)  # 원본 PNG는 제한보다 커도 보내는 JPEG가 맞으면 통과
    assert len(sent) == 2

    monkeypatch.setattr(jbai_ocr, "MAX_IMAGE_BYTES", len(jpeg) - 1)
    with pytest.raises(jbai_ocr.JBAIImageTooLarge):
        jbai_ocr.run_jbai_file_pair(photo)
    assert len(sent) == 2


def test_rrn_back_digits_are_masked_on_receipt(monkeypatch):
    configure(monkeypatch)
    content = ("성명 김가상\n주민등록번호 990101-2718281\n붙은번호 9901012718281\n"
               "띄어읽음 990101 – 2 718281\n<fcel>주민등록번호<fcel>990101-2718281<nl>")
    recorder(monkeypatch, content)

    page = jbai_ocr.run_jbai_ocr(b"\xff\xd8 synthetic", (10, 10))

    kept = [page.raw_content, *page.text_lines,
            *(cell.text for table in page.tables for row in table.rows for cell in row)]
    assert not any("718281" in text for text in kept)
    assert "주민등록번호 990101-2******" in page.text_lines
    assert "붙은번호 9901012******" in page.text_lines
    assert page.tables[0].rows[0][1].text == "990101-2******"


def test_mask_rrn_leaves_other_numbers():
    text = "문서확인번호 1234-5678-9012-34567 010-1234-5678 2025.10.01-2025.12.31 20251001-20251231 납부자번호 1234567890"
    assert jbai_ocr.mask_rrn(text) == text


@pytest.mark.parametrize("error", [
    TimeoutError("timed out"),
    socket.timeout("timed out"),
    urllib.error.URLError(TimeoutError("timed out")),
])
def test_timeout_is_classified_and_uses_given_limit(monkeypatch, error):
    configure(monkeypatch)
    seen = []

    def slow_post(request, timeout):
        seen.append(timeout)
        raise error

    monkeypatch.setattr(jbai_ocr, "_http_post", slow_post)
    with pytest.raises(jbai_ocr.JBAITimeoutError):
        jbai_ocr.run_jbai_ocr(b"\xff\xd8", (10, 10), timeout=7)
    assert seen == [7]


def test_http_errors_carry_status_without_body(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(jbai_ocr, "_http_post", lambda *_: (503, b"secret body 990101-2718281", {}))
    with pytest.raises(jbai_ocr.JBAIRequestError) as caught:
        jbai_ocr.run_jbai_ocr(b"\xff\xd8", (10, 10))
    assert caught.value.status == 503
    assert "718281" not in str(caught.value) and "secret" not in str(caught.value)


def test_empty_base_url_from_env_file_uses_default(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("JBAI_BASE_URL", "")  # .env의 `JBAI_BASE_URL=` 빈 줄
    urls = []
    monkeypatch.setattr(jbai_ocr, "_http_post", lambda request, timeout: (
        urls.append(request.full_url) or (200, json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode(), {})))
    jbai_ocr.run_jbai_ocr(b"\xff\xd8", (10, 10))
    assert urls == [jbai_ocr.DEFAULT_BASE_URL + "/ocr/chat/completions"]
