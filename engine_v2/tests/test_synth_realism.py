"""Independent coverage for split isolation, phone image formation and rectification."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from engine_v2.pipeline.perspective import rectify_document
from engine_v2.tools.make_synth_eval import (
    SPLITS, phone_capture, split_documents, generate,
)


def test_splits_exclude_shared_fonts_and_template_layouts():
    assert not set(SPLITS['train']['fonts']) & set(SPLITS['test']['fonts'])
    assert SPLITS['train']['template'] != SPLITS['test']['template']
    for train, test in zip(split_documents('train'), split_documents('test')):
        assert train[0] == test[0]
        assert train[1] != test[1]
        assert train[2] == test[2]
    with pytest.raises(ValueError, match='cannot overlap'):
        generate('/tmp/unused-synth-split', split='train', fonts=['nanumgothic'])


@pytest.mark.parametrize('stage,low,high', [('phone_weak',.03,.05), ('phone_strong',.06,.08)])
def test_phone_has_reproducible_geometry_shadow_background(stage, low, high):
    base = Image.new('RGB', (400,600), 'white')
    first, matrix, info = phone_capture(base, stage, np.random.default_rng(42))
    second, _, _ = phone_capture(base, stage, np.random.default_rng(42))
    assert first.tobytes() == second.tobytes()
    offsets = np.asarray(info['corner_displacement_magnitudes'])
    assert np.all(offsets >= low) and np.all(offsets <= high)
    assert first.width > base.width and first.height > base.height
    assert np.asarray(first)[0,0].mean() < 120  # exposed desk
    center = np.asarray(first)[first.height//3:2*first.height//3, first.width//3:2*first.width//3]
    assert center.std() > 5  # nonuniform illumination on blank sheet
    assert np.isfinite(matrix).all() and abs(np.linalg.det(matrix)) > .01
    corners = np.array([[0,0,1], [399,0,1], [399,599,1], [0,599,1]])
    transformed = corners @ matrix.T
    transformed = transformed[:,:2] / transformed[:,2:]
    np.testing.assert_allclose(transformed, info['document_corners_px'], atol=1e-3)


def test_rectification_finds_independent_quad_and_fails_closed_on_blank():
    canvas = Image.new('RGB', (600,800), (70,60,50))
    draw = ImageDraw.Draw(canvas)
    draw.polygon([(80,60),(510,105),(530,740),(60,700)], fill='white')
    draw.text((180,220), 'SYNTHETIC', fill='black')
    result = rectify_document(canvas)
    assert result.applied
    assert result.image.width < canvas.width and result.image.height < canvas.height
    assert result.corners is not None and np.isfinite(result.matrix).all()
    blank = Image.new('RGB', (400,600), 'white')
    untouched = rectify_document(blank)
    assert not untouched.applied
    assert untouched.image.tobytes() == blank.tobytes()


def test_rectifier_uses_pixels_without_ground_truth_corners():
    base = Image.new('RGB', (400,600), 'white')
    image, _, _ = phone_capture(base, 'phone_strong', np.random.default_rng(42))
    result = rectify_document(image)
    assert result.applied
    pixels = np.asarray(result.image)
    assert pixels.mean() > np.asarray(image).mean()


def test_font_hash_failure_does_not_silently_render_substitute(tmp_path):
    from engine_v2.tools.fetch_synth_fonts import FONTS, font_path
    filename, _ = FONTS['nanumgothic']
    (tmp_path / filename).write_bytes(b'corrupt font bytes')
    with pytest.raises(ValueError, match='hash mismatch'):
        font_path('nanumgothic', tmp_path)
