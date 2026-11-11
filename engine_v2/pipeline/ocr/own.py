"""PP-OCRv5 DB detection + Korean CTC recognition, exclusively ONNX CPU.

Algorithms implemented here; model and upstream attribution in docs/own-ocr.md.
No automatic download and no filename-based recognition.
"""
from __future__ import annotations

from functools import lru_cache
import math

from ...tools.fetch_own_models import MODEL_DIR, verify_models
from . import OcrWord


def ctc_decode(probabilities, characters: list[str]) -> tuple[str, float]:
    """Blank=0, collapse adjacent repeats BEFORE removing blank; mean emitted score."""
    import numpy as np
    probs = np.asarray(probabilities)
    if probs.ndim != 2 or probs.shape[1] != len(characters) + 1:
        raise ValueError('CTC class count does not match pinned dictionary')
    if not len(probs):
        return '', 0.0
    ids = probs.argmax(axis=1)
    keep = (ids != 0) & np.r_[True, ids[1:] != ids[:-1]]
    text = ''.join(characters[int(i) - 1] for i in ids[keep])
    return text, float(probs[np.arange(len(ids))[keep], ids[keep]].mean()) if keep.any() else 0.0


def polygon_bbox(points, source_size, map_size):
    """Map polygon coordinates to top-left pixel bounds of original input."""
    import numpy as np
    pts = np.asarray(points, dtype=float) * (np.asarray(source_size) / np.asarray(map_size))
    pts = np.clip(pts, (0, 0), source_size)
    return tuple(float(v) for v in (*pts.min(axis=0), *pts.max(axis=0)))


@lru_cache(maxsize=1)
def sessions():
    verify_models(MODEL_DIR)
    import onnxruntime as ort
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    det, rec = [ort.InferenceSession(str(MODEL_DIR / name), sess_options=options,
                                    providers=['CPUExecutionProvider']) for name in ('det.onnx', 'rec.onnx')]
    chars = (MODEL_DIR / 'korean_dict.txt').read_text(encoding='utf-8').splitlines() + [' ']
    embedded = rec.get_modelmeta().custom_metadata_map.get('character')
    if embedded is not None and embedded.splitlines() != chars[:-1]:
        raise ValueError('own model metadata does not match pinned Korean dictionary')
    if rec.get_outputs()[0].shape[-1] != len(chars) + 1:
        raise ValueError('own recognition class count does not match dictionary')
    return det, rec, chars


def _ordered_box(points):
    import numpy as np
    # Sort left/right pairs, then top/bottom, avoiding duplicate corners on diamonds.
    p = points[np.argsort(points[:, 0])]
    left, right = p[:2][np.argsort(p[:2, 1])], p[2:][np.argsort(p[2:, 1])]
    return np.array([left[0], right[0], right[1], left[1]], dtype=np.float32)


def _detect(image, session):
    import cv2
    import numpy as np
    import pyclipper
    h, w = image.shape[:2]
    ratio = min(1.0, 1600 / max(h, w))
    rh, rw = [max(32, round(v * ratio / 32) * 32) for v in (h, w)]
    resized = cv2.resize(image, (rw, rh)).astype(np.float32) / 255
    tensor = ((resized - np.array([.485, .456, .406], dtype=np.float32)) /
              np.array([.229, .224, .225], dtype=np.float32)).transpose(2, 0, 1)[None]
    pred = session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0]
    mask = (pred > .3).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    mh, mw = pred.shape
    boxes = []
    for contour in contours[:2000]:
        rect = cv2.minAreaRect(contour)
        if min(rect[1]) < 3:
            continue
        region = np.zeros_like(mask)
        cv2.fillPoly(region, [contour], 1)
        if cv2.mean(pred, region)[0] < .5:
            continue
        poly = cv2.boxPoints(rect)
        perimeter = cv2.arcLength(poly, True)
        if perimeter <= 0:
            continue
        offset = pyclipper.PyclipperOffset()
        offset.AddPath((poly * 1024).astype(np.int64).tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        expanded = offset.Execute(cv2.contourArea(poly) * 1.5 / perimeter * 1024)
        if len(expanded) != 1:
            continue
        box = _ordered_box(cv2.boxPoints(cv2.minAreaRect(np.array(expanded[0], dtype=np.float32) / 1024)))
        box *= np.array([w / mw, h / mh], dtype=np.float32)
        box = np.clip(box, (0, 0), (w - 1, h - 1)).astype(np.float32)
        boxes.append(box)
    return boxes


def _crop(image, box):
    import cv2
    import numpy as np
    width = max(1, round(max(np.linalg.norm(box[0] - box[1]), np.linalg.norm(box[2] - box[3]))))
    height = max(1, round(max(np.linalg.norm(box[0] - box[3]), np.linalg.norm(box[1] - box[2]))))
    dst = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], dtype=np.float32)
    crop = cv2.warpPerspective(image, cv2.getPerspectiveTransform(box, dst), (width, height), borderMode=cv2.BORDER_REPLICATE)
    return np.rot90(crop) if height / width >= 1.5 else crop


def recognize(png: bytes, size: tuple[int, int]) -> list[OcrWord]:
    det, rec, chars = sessions()  # clear missing-model error even without optional image libraries
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[1::-1] != tuple(size):
        raise ValueError('own input size must match decoded image pixel size')
    words = []
    for box in _detect(image, det):
        crop = _crop(image, box)
        h, w = crop.shape[:2]
        width = max(320, math.ceil(48 * w / h))
        if width > 4096:
            raise ValueError('own text line exceeds supported width (4096)')
        content_w = min(width, math.ceil(48 * w / h))
        tensor = np.zeros((1, 3, 48, width), dtype=np.float32)
        normalized = cv2.resize(crop, (content_w, 48)).astype(np.float32) / 127.5 - 1
        tensor[0, :, :, :content_w] = normalized.transpose(2, 0, 1)
        pred = rec.run(None, {rec.get_inputs()[0].name: tensor})[0][0]
        text, confidence = ctc_decode(pred, chars)
        if text.strip():
            words.append(OcrWord(text, confidence, polygon_bbox(box, size, size)))
    return sorted(words, key=lambda word: (round(word.bbox_px[1] / 15), word.bbox_px[0]))
