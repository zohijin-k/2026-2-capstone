"""Classifier corpus boundaries and honest metrics; no model download or OCR."""
import pytest

from engine_v2.classifier.catalog import CLASS_LABELS, rule_predict
from engine_v2.classifier.data import document_cells
from engine_v2.classifier.evaluate import metrics, validate_test


def test_all_categories_and_disjoint_layouts():
    train = dict(document_cells('train'))
    test = dict(document_cells('test'))
    assert set(train) == set(test) == set(CLASS_LABELS)
    assert all(train[key] != test[key] for key in CLASS_LABELS)
    insurance = ' '.join(cell[2] for cell in test['insurance_4'])
    acquisition = ' '.join(cell[2] for cell in test['nhis_acquisition_loss'])
    assert '자격득실' not in insurance
    assert '4대보험' not in acquisition


def test_rules_use_actual_body_and_abstain_not_other():
    assert rule_predict([{'text': '건강보험 자격득실확인서'}]) == 'nhis_acquisition_loss'
    assert rule_predict([{'text': '건강보험료 고지서'}]) is None
    assert rule_predict([{'text': '결제영수증'}]) == 'receipt'


def test_abstention_is_error_and_recall_denominator_includes_it():
    result = metrics(['other', 'receipt'], [None, 'receipt'])
    assert result['accuracy'] == .5
    assert result['abstention_rate'] == .5
    assert result['accepted_accuracy'] == 1
    assert result['class_metrics']['other']['recall'] == 0
    # Positive rules outside this catalog still occupy a confusion column.
    outside = metrics(['other'], ['labor_contract'])
    assert 'labor_contract' in outside['confusion_labels']
    assert sum(map(sum, outside['confusion_matrix'])) == 1


def test_test_provenance_rejects_training_and_wrong_fonts():
    with pytest.raises(ValueError):
        validate_test({'synthetic': True, 'split':'train', 'samples':[]})
    sample = {'synthetic':True,'split':'test','font':'nanumgothiccoding',
              'template_id':'receipt:inline_header_v1','document_type':'receipt'}
    with pytest.raises(ValueError):
        validate_test({'synthetic':True,'split':'test','samples':[sample]})
