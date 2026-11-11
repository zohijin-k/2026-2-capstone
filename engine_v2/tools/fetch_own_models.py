"""Fetch pinned public weights; no framework or credentials required."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import urllib.request

MODEL_DIR = Path(__file__).resolve().parents[1] / 'models' / 'own'
BASE = 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5'
ASSETS = {
    'det.onnx': (BASE + '/det/ch_PP-OCRv5_det_mobile.onnx', '4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae'),
    'rec.onnx': (BASE + '/rec/korean_PP-OCRv5_rec_mobile.onnx', 'cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b'),
    'korean_dict.txt': ('https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/v3.3.2/ppocr/utils/dict/ppocrv5_korean_dict.txt', 'a88071c68c01707489baa79ebe0405b7beb5cca229f4fc94cc3ef992328802d7'),
}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_models(directory: Path = MODEL_DIR) -> None:
    for name, (_, expected) in ASSETS.items():
        path = directory / name
        if not path.is_file():
            raise FileNotFoundError('own 모델 없음: .venv/bin/python engine_v2/tools/fetch_own_models.py')
        if digest(path) != expected:
            raise ValueError(f'own SHA256 mismatch: {name}; remove damaged file and run engine_v2/tools/fetch_own_models.py')


def fetch(directory: Path = MODEL_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in ASSETS.items():
        target = directory / name
        if target.exists():
            if digest(target) != expected:
                raise ValueError(f'SHA256 mismatch: {name}')
        else:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=directory, delete=False) as out:
                    temporary = Path(out.name)
                    with urllib.request.urlopen(url, timeout=120) as response:
                        while chunk := response.read(1024 * 1024):
                            out.write(chunk)
                if digest(temporary) != expected:
                    raise ValueError(f'SHA256 mismatch: {name}')
                temporary.replace(target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        print(f'{name}: {target.stat().st_size} bytes sha256={expected} OK')


if __name__ == '__main__':
    fetch()
