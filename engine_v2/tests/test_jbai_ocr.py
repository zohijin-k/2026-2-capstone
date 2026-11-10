from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..pipeline import jbai_ocr


def openai_response(content: str) -> tuple[int, bytes, dict[str, str]]:
    body = {"choices": [{"message": {"content": content}}]}
    return 200, json.dumps(body).encode(), {}


def configure(monkeypatch):
    monkeypatch.setenv("JBAI_API_KEY", "fake-jbai-test-key")
    monkeypatch.setenv("JBAI_BASE_URL", "https://ocr.example.invalid/open-api/v1")
    monkeypatch.delenv("JBAI_ALLOW_REAL_DOCS", raising=False)
    monkeypatch.setattr(jbai_ocr._RATE_LIMITER, "acquire", lambda: None)


def test_three_page_pdf_calls_backend_in_page_order(tmp_path: Path, monkeypatch):
    import pymupdf

    configure(monkeypatch)
    pdf_path = tmp_path / "synthetic.pdf"
    document = pymupdf.open()
    for index in range(3):
        page = document.new_page(width=300, height=400)
        page.insert_text((30, 60), f"SYNTHETIC PAGE {index + 1}")
    document.save(pdf_path)
    document.close()

    requests = []

    def fake_post(request, timeout):
        payload = json.loads(request.data)
        requests.append((request.full_url, request.method, timeout, payload))
        content = f"page {len(requests) - 1}"
        return openai_response(content)

    monkeypatch.setattr(jbai_ocr, "_http_post", fake_post)
    result = jbai_ocr.run_jbai_pdf(pdf_path)

    assert len(requests) == 3
    assert [page.page for page in result.pages] == [0, 1, 2]
    assert [page.text_lines for page in result.pages] == [["page 0"], ["page 1"], ["page 2"]]
    assert all(method == "POST" and timeout == 600 for _, method, timeout, _ in requests)
    assert all(url.endswith("/ocr/chat/completions") for url, _, _, _ in requests)
    first_payload = requests[0][3]
    assert first_payload["model"] == jbai_ocr.MODEL
    message = first_payload["messages"][0]
    assert message["content"][0] == {"type": "text", "text": "OCR:"}
    assert message["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_base_url_trailing_slash_keeps_endpoint_path(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("JBAI_BASE_URL", "https://ocr.example.invalid/open-api/v1/")
    requests = []
    monkeypatch.setattr(
        jbai_ocr, "_http_post",
        lambda request, timeout: (requests.append(request.full_url) or openai_response("ok")),
    )

    jbai_ocr.run_jbai_ocr(b"fake png", (10, 10))

    assert requests == ["https://ocr.example.invalid/open-api/v1/ocr/chat/completions"]


def test_429_retries_then_succeeds(monkeypatch):
    configure(monkeypatch)
    attempts = []
    sleeps = []

    def fake_post(request, timeout):
        attempts.append(request)
        if len(attempts) == 1:
            return 429, b"", {"Retry-After": "0"}
        return openai_response("합성 OCR 결과")

    monkeypatch.setattr(jbai_ocr, "_http_post", fake_post)
    result = jbai_ocr.run_jbai_ocr(b"fake png", (10, 10), sleep=sleeps.append)
    assert len(attempts) == 2
    assert sleeps == [0.0]
    assert result.text_lines == ["합성 OCR 결과"]


def test_429_retry_limit_is_clear(monkeypatch):
    configure(monkeypatch)
    attempts = []
    monkeypatch.setattr(jbai_ocr, "_http_post", lambda *_: (attempts.append(1) or (429, b"", {"Retry-After": "0"})))
    with pytest.raises(jbai_ocr.JBAIRateLimitError, match="재시도"):
        jbai_ocr.run_jbai_ocr(b"fake png", (10, 10), sleep=lambda _: None)
    assert len(attempts) == jbai_ocr.MAX_ATTEMPTS


def test_401_error_never_includes_api_key(monkeypatch):
    configure(monkeypatch)
    secret = "private-test-secret"
    monkeypatch.setenv("JBAI_API_KEY", secret)
    monkeypatch.setattr(jbai_ocr, "_http_post", lambda *_: (401, b"", {}))
    with pytest.raises(jbai_ocr.JBAIAuthenticationError) as caught:
        jbai_ocr.run_jbai_ocr(b"fake png", (10, 10))
    assert "JBAI_API_KEY" in str(caught.value)
    assert secret not in str(caught.value)


def test_missing_key_is_clear_and_sends_no_request(monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv("JBAI_API_KEY")
    sent = []
    monkeypatch.setattr(jbai_ocr, "_http_post", lambda *_: sent.append(True))
    with pytest.raises(jbai_ocr.JBAIConfigurationError, match="JBAI_API_KEY"):
        jbai_ocr.run_jbai_ocr(b"fake png", (10, 10))
    assert sent == []


def test_private_file_and_demo_upload_are_blocked_by_default(tmp_path: Path, monkeypatch):
    configure(monkeypatch)
    private_root = tmp_path / "private"
    monkeypatch.setattr(jbai_ocr, "PRIVATE_DIR", private_root)
    sent = []
    monkeypatch.setattr(jbai_ocr, "_http_post", lambda *_: sent.append(True))
    with pytest.raises(jbai_ocr.JBAIRealDocumentBlocked, match="data/private"):
        jbai_ocr.run_jbai_ocr(b"fake png", (10, 10), source_path=private_root / "synthetic.pdf")
    with pytest.raises(jbai_ocr.JBAIRealDocumentBlocked, match="데모 업로드"):
        jbai_ocr.run_jbai_ocr(b"fake png", (10, 10), is_demo_upload=True)
    assert sent == []


def test_table_html_keeps_rowspan_and_colspan():
    html = """<table>
      <tr><th rowspan="2">MONTH</th><th colspan="2">BILLED AMOUNT</th></tr>
      <tr><th>HEALTH</th><th>CARE</th></tr>
      <tr><td>2025-10</td><td>10000</td><td>500</td></tr>
    </table>"""
    tables = jbai_ocr.parse_html_tables(html)
    assert len(tables) == 1
    rows = tables[0].rows
    assert rows[0][0] == jbai_ocr.JBAITableCell("MONTH", rowspan=2, colspan=1, header=True)
    assert rows[0][1] == jbai_ocr.JBAITableCell("BILLED AMOUNT", rowspan=1, colspan=2, header=True)
    assert [cell.text for cell in rows[1]] == ["HEALTH", "CARE"]
    assert [cell.text for cell in rows[2]] == ["2025-10", "10000", "500"]
