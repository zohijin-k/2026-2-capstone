"""Held-out synthetic evaluation against unchanged production body rules.

Abstention counts as wrong in deployed accuracy/F1. Top-1 candidate accuracy is
reported separately and must not be confused with accepted-only accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from .catalog import CLASS_LABELS, RULE_KEYS, rule_predict
from .model import DocumentClassifier, MODEL_DIR
from ..tools.make_synth_eval import SPLITS

ABSTAIN = 'unclassifiable'


def validate_test(corpus, training=None):
    if corpus.get('synthetic') is not True or corpus.get('split') != 'test':
        raise ValueError('Evaluation requires the synthetic held-out test split')
    samples = corpus.get('samples', [])
    if not samples:
        raise ValueError('Empty test corpus')
    for sample in samples:
        if (sample.get('synthetic') is not True or sample.get('split') != 'test'
                or sample.get('font') not in SPLITS['test']['fonts']
                or not sample.get('template_id', '').endswith(SPLITS['test']['template'])
                or sample.get('document_type') not in CLASS_LABELS):
            raise ValueError('Invalid held-out sample provenance')
    if {s['document_type'] for s in samples} != set(CLASS_LABELS):
        raise ValueError('Test corpus must include every catalog class')
    if training is not None:
        from .train import validate_training_corpus
        train_samples = validate_training_corpus(training)
        for field in ('font', 'template_id', 'image_sha256'):
            a = {s[field] for s in train_samples}
            b = {s[field] for s in samples}
            if a & b:
                raise ValueError('Train/test overlap: '+field)
    return samples


def metrics(truth, predictions):
    labels = list(CLASS_LABELS)
    normalized = [p if p is not None else ABSTAIN for p in predictions]
    matrix_labels = labels + [ABSTAIN] + sorted(set(normalized) - set(labels) - {ABSTAIN})
    precision, recall, f1, support = precision_recall_fscore_support(
        truth, normalized, labels=labels, zero_division=0)
    accepted = [i for i, p in enumerate(normalized) if p != ABSTAIN]
    return {'accuracy': float(accuracy_score(truth, normalized)),
            'macro_f1': float(np.mean(f1)),
            'abstention_rate': normalized.count(ABSTAIN)/len(truth),
            'accepted_accuracy': sum(truth[i] == normalized[i] for i in accepted)/len(accepted) if accepted else None,
            'class_metrics': {key: {'precision': float(precision[i]), 'recall': float(recall[i]),
                                   'f1': float(f1[i]), 'support': int(support[i])}
                              for i, key in enumerate(labels)},
            'confusion_labels': matrix_labels,
            'confusion_matrix': confusion_matrix(truth, normalized, labels=matrix_labels).tolist()}


def evaluate(corpus_path, model_dir=MODEL_DIR, training_path=None):
    corpus = json.loads(Path(corpus_path).read_text(encoding='utf-8'))
    training = json.loads(Path(training_path).read_text(encoding='utf-8')) if training_path else None
    samples = validate_test(corpus, training)
    model = DocumentClassifier.load(model_dir)
    if set(model.classes) != set(CLASS_LABELS):
        raise ValueError('Model classes do not match the evaluation catalog')
    if training_path and model.training_metadata.get('corpus_sha256') != hashlib.sha256(Path(training_path).read_bytes()).hexdigest():
        raise ValueError('Training corpus does not match the fitted artifact')
    truth, deployed, candidates, rules, rows, times = [], [], [], [], [], []
    for sample in samples:
        start = time.perf_counter()
        pred = model.predict(sample['words'], sample['pixel_size'])
        elapsed = time.perf_counter() - start
        rule = rule_predict(sample['words'])
        truth.append(sample['document_type'])
        deployed.append(pred.document_type)
        candidates.append(pred.candidate_type)
        rules.append(rule)
        times.append(elapsed)
        rows.append({'id': sample['id'], 'truth': sample['document_type'],
                     'font': sample['font'], 'degradation': sample['degradation'],
                     'prediction': pred.document_type, 'candidate': pred.candidate_type,
                     'probability': pred.probability, 'margin': pred.margin,
                     'needs_review': pred.needs_review, 'rule': rule,
                     'seconds': elapsed})
    bins = []
    for low, high in ((0,.5),(.5,.65),(.65,.8),(.8,.9),(.9,1.0000001)):
        selected = [r for r in rows if low <= r['probability'] < high]
        bins.append({'low': low, 'high': min(high,1), 'count': len(selected),
                     'candidate_accuracy': sum(r['candidate']==r['truth'] for r in selected)/len(selected) if selected else None,
                     'mean_confidence': np.mean([r['probability'] for r in selected]).item() if selected else None,
                     'abstentions': sum(r['needs_review'] for r in selected)})
    stages = {}
    for stage in sorted({r['degradation'] for r in rows}):
        selected = [r for r in rows if r['degradation'] == stage]
        stages[stage] = {'count':len(selected), **{key: sum(r[p]==r['truth'] for r in selected)/len(selected)
            for key,p in [('model_accuracy','prediction'),('candidate_accuracy','candidate'),('rule_accuracy','rule')]},
            'abstention_rate':sum(r['needs_review'] for r in selected)/len(selected)}
    common = [r for r in rows if r['truth'] in set(RULE_KEYS.values())]
    return {'schema_version':1, 'synthetic':True, 'test_count':len(rows),
            'model':metrics(truth,deployed), 'top1':metrics(truth,candidates), 'rule':metrics(truth,rules),
            'common_rule_coverage':{'count':len(common),
                'model_accuracy':sum(r['prediction']==r['truth'] for r in common)/len(common),
                'rule_accuracy':sum(r['rule']==r['truth'] for r in common)/len(common)},
            'confidence_bins':bins, 'degradations':stages,
            'timing':{'policy':'one page at a time, model already loaded; features, logits and explanations included; OCR, IO, load excluded; first prediction included',
                      'count':len(times), 'mean_seconds':float(np.mean(times)),
                      'median_seconds':float(np.median(times)), 'p95_seconds':float(np.quantile(times,.95)),
                      'max_seconds':max(times), 'under_100ms':all(t<.1 for t in times)},
            'corpus_sha256':hashlib.sha256(Path(corpus_path).read_bytes()).hexdigest(),
            'threshold':model.threshold, 'margin':model.margin, 'seed':model.seed, 'rows':rows}


def filename_experiment(corpus_path, model_dir=MODEL_DIR):
    """Four actual own-OCR calls: same-path content swap and misleading renames."""
    from .predict import predict_file
    path = Path(corpus_path)
    corpus = json.loads(path.read_text(encoding='utf-8'))
    samples = validate_test(corpus)
    model = DocumentClassifier.load(model_dir)
    selected = [next(s for s in samples if s['document_type'] == key and s['degradation'] == 'clean')
                for key in ('resident_abstract', 'nhis_payment')]
    contents = []
    for sample in selected:
        image = (path.parent / (sample['id']+'.png')).resolve()
        if image.parent != path.parent.resolve():
            raise ValueError('Synthetic image must be beside its corpus')
        contents.append(image.read_bytes())
    predictions = []
    with tempfile.TemporaryDirectory(prefix='synthetic-classifier-') as directory:
        # Both contents use this exact name; second run overwrites only our temp file.
        same = Path(directory) / '건강보험료납부확인서.png'
        renamed = Path(directory) / '주민등록초본.png'
        for target, raw in ((same, contents[0]), (same, contents[1]),
                            (renamed, contents[0]), (renamed, contents[1])):
            target.write_bytes(raw)
            predictions.append(predict_file(target, model)[0])
    keys = ['resident_abstract', 'nhis_payment'] * 2
    return {'actual_own_ocr_calls':4,
            'same_path_content_swap_correct':all(p.document_type == key for p,key in zip(predictions,keys)),
            'renames_identical':predictions[0] == predictions[2] and predictions[1] == predictions[3],
            'predictions':[{'expected':key,'prediction':p.document_type,'probability':p.probability}
                           for p,key in zip(predictions,keys)]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,required=True)
    parser.add_argument('--training-corpus',type=Path,required=True)
    parser.add_argument('--model',type=Path,default=MODEL_DIR)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--check-filenames',action='store_true',help='Run four extra real own-OCR calls on synthetic images')
    args=parser.parse_args()
    result=evaluate(args.corpus,args.model,args.training_corpus)
    if args.check_filenames:
        result['filename_experiment'] = filename_experiment(args.corpus,args.model)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:{m:result[k][m] for m in ('accuracy','macro_f1','abstention_rate')} for k in ('model','top1','rule')},ensure_ascii=False))
    print(json.dumps(result['timing']))


if __name__=='__main__':
    main()
