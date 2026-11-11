"""Download immutable OFL 1.1 Korean fonts and notices for synthetic rendering."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import tempfile
import urllib.request

FONT_DIR = Path(__file__).resolve().parents[1] / 'data' / 'synth_fonts'
REVISION = '1c96438dec81b2b5078557d91315e31fb29b9462'
BASE = f'https://raw.githubusercontent.com/google/fonts/{REVISION}/ofl'
FONTS = {
    'nanumgothic': ('NanumGothic-Regular.ttf', '76f45ef4a6bcff344c837c95a7dcc26e017e38b5846d5ae0cdcb5b86be2e2d31'),
    'nanummyeongjo': ('NanumMyeongjo-Regular.ttf', '7ed9e8653a8ed04285d51dc343ffea6eb3d9c73afc27383ea8929ee4ffd03205'),
    'nanumgothiccoding': ('NanumGothicCoding-Regular.ttf', '787effd7efed2abca88ade231faa8191f4e9fcf85b1805a13ee1dc3724b72089'),
}
LICENSE_HASHES = {
    'nanumgothic': 'eeacf16032901d0ed0456876ec77b8f0fda6b3fecec7d972f8543eb602e6c30f',
    'nanummyeongjo': '8eb1c1019fe7fe6d0b6e7d7bbbba1d9cbdd969d8c5f26455708f6cfb8a77284c',
    'nanumgothiccoding': 'eeacf16032901d0ed0456876ec77b8f0fda6b3fecec7d972f8543eb602e6c30f',
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def font_path(name, directory=FONT_DIR):
    filename, expected = FONTS[name]
    path = Path(directory) / filename
    if not path.is_file() or digest(path) != expected:
        raise ValueError('Font missing/hash mismatch; run python -m engine_v2.tools.fetch_synth_fonts')
    return path


def fetch(directory=FONT_DIR):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for family, (filename, checksum) in FONTS.items():
        for remote, local, expected in ((filename, filename, checksum),
                                         ('OFL.txt', family+'-OFL.txt', LICENSE_HASHES[family])):
            target = directory / local
            if target.exists():
                if digest(target) != expected:
                    raise ValueError(f'Font asset SHA256 mismatch: {local}')
            else:
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
                        temporary = Path(stream.name)
                        with urllib.request.urlopen(f'{BASE}/{family}/{remote}', timeout=120) as response:
                            while chunk := response.read(1024 * 1024):
                                stream.write(chunk)
                    if digest(temporary) != expected:
                        raise ValueError(f'Font asset SHA256 mismatch: {local}')
                    temporary.replace(target)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            print(f'{local}: sha256={expected} OK')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=FONT_DIR)
    fetch(parser.parse_args().output)
