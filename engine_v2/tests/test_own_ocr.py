"""Model-free own adapter contracts and pinned-download failure modes."""
from io import BytesIO
import hashlib

import numpy as np
import pytest

from engine_v2.pipeline import ocr
from engine_v2.pipeline.ocr import own
from engine_v2.tools import fetch_own_models as fetcher


def test_ctc_blank_repeat_and_confidence():
    # Adjacent repeats collapse; a blank separates repeated letters.
    probs = np.array([[.05,.9,.05], [.1,.8,.1], [.9,.05,.05],
                      [.1,.8,.1], [.05,.05,.9]])
    text, score = own.ctc_decode(probs, ['가', '나'])
    assert text == '가가나'
    assert score == pytest.approx((.9+.8+.9)/3)
    assert own.ctc_decode(np.array([[1.,0.,0.]]), ['가','나']) == ('', 0.)
    assert own.ctc_decode(np.empty((0,3)), ['가','나']) == ('', 0.)
    with pytest.raises(ValueError, match='class count'):
        own.ctc_decode(probs, ['가'])


def test_coordinate_scaling_clipping_and_word_contract():
    bbox = own.polygon_bbox([[-2,5],[30,5],[30,25],[-2,25]], (200,100), (100,50))
    assert bbox == (0.,10.,60.,50.)
    word = ocr.OcrWord('가나다', .9, bbox)
    assert word.text == '가나다'
    assert word.confidence == .9
    assert len(word.bbox_px) == 4
    result = ocr.OcrResult('own', [ocr.OcrWord('아래', .8, (0,60,20,80)), word])
    assert result.text == '가나다 아래'


@pytest.mark.parametrize(('platform','expected'), [('darwin','applevision'), ('linux','own'), ('win32','own')])
def test_platform_default(monkeypatch, platform, expected):
    monkeypatch.delenv('ENGINE_V2_OCR', raising=False)
    monkeypatch.setattr(ocr.sys, 'platform', platform)
    assert ocr.default_engine() == expected
    monkeypatch.setenv('ENGINE_V2_OCR', 'easyocr')
    assert ocr.default_engine() == 'easyocr'


def test_missing_models_error_contains_fetch_command(tmp_path, monkeypatch):
    own.sessions.cache_clear()
    monkeypatch.setattr(own, 'MODEL_DIR', tmp_path)
    try:
        result = ocr.run_ocr('own', b'not an image', (1,1))
        assert result.words == []
        assert 'engine_v2/tools/fetch_own_models.py' in result.error
        assert 'FileNotFoundError' in result.error
    finally:
        own.sessions.cache_clear()


def test_existing_model_hash_mismatch_fails_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, 'ASSETS', {'det.onnx': ('https://example.invalid/model', '0'*64)})
    (tmp_path/'det.onnx').write_bytes(b'bad model')
    with pytest.raises(ValueError, match='SHA256 mismatch'):
        fetcher.fetch(tmp_path)
    with pytest.raises(ValueError, match='SHA256 mismatch'):
        fetcher.verify_models(tmp_path)


def test_download_hash_mismatch_does_not_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, 'ASSETS', {'det.onnx': ('https://example.invalid/model', '0'*64)})
    monkeypatch.setattr(fetcher.urllib.request, 'urlopen', lambda *a, **k: BytesIO(b'bad download'))
    with pytest.raises(ValueError, match='SHA256 mismatch'):
        fetcher.fetch(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_download_verified_and_cached(tmp_path, monkeypatch):
    content = b'synthetic model bytes'
    monkeypatch.setattr(fetcher, 'ASSETS', {'det.onnx': ('https://example.invalid/model', hashlib.sha256(content).hexdigest())})
    monkeypatch.setattr(fetcher.urllib.request, 'urlopen', lambda *a, **k: BytesIO(content))
    fetcher.fetch(tmp_path)
    fetcher.verify_models(tmp_path)
    monkeypatch.setattr(fetcher.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('cached model should not download'))
    fetcher.fetch(tmp_path)
    assert (tmp_path/'det.onnx').read_bytes() == content
