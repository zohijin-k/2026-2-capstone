"""Render extended synthetic forms using make_synth_eval's disjoint splits.

All examples are fictitious; OCR sees pixels only. No private input is opened.
Two content variants per training font and one per held-out test font by default.
No title or truth text is ever substituted for actual recognized text.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path

import numpy as np

from .catalog import CLASS_LABELS
from ..pipeline.ocr import run_ocr
from ..tools.fetch_synth_fonts import font_path
from ..tools.make_synth_eval import SPLITS, STAGES, render, split_documents, degrade_with_geometry

SEED = 20261111
ROOT = Path(__file__).resolve().parents[1] / 'data' / 'synth_eval' / 'classifier'

# Authored from public repository form/sample vocabulary, not personal documents.
# Form boilerplate is deliberately abbreviated, not claimed to be official artwork.
BODIES = {
    'resident_register': ['주민등록표 등본', '세대 구성 사유 및 일자', '세대주 및 관계', '세대원 가상시험 본인', '세대원 가상가족 배우자', '현주소 전북특별자치도 전주시 가상동'],
    'nhis_qualification': ['건강보험 자격확인서', '가입자 성명 가상시험', '가입자 구분 직장가입자', '건강보험증 번호 00000000000', '가구원 가상가족 2001.04.03', '세대원수 2', '현재 자격 사항 확인'],
    'nhis_acquisition_loss': ['건강보험 자격득실확인서', '가입자구분 사업장명칭 자격취득일 자격상실일', '직장가입자 가상사업장 2020.01.01 2022.03.01', '지역가입자 해당없음 2022.03.02 2023.01.01', '직장가입자 합성회사 2023.01.02', '조회기간 2020.01.01 ~ 2026.11.10'],
    'insurance_4': ['4대보험 가입내역 확인서', '사업장 가입자 가입내역', '국민연금 가입 2020.01.01', '건강보험 가입 2020.01.01', '고용보험 가입 2020.01.01', '산재보험 가입 2020.01.01', '사업장명칭 가상사업장'],
    'interview_confirm': ['면접확인서', '면접기업 가상회사', '면접일시 2026.04.02 10:00', '면접장소 전주시 가상동', '응시직군 사무직', '기업의 채용을 위한 면접에 참석하였음을 확인합니다', '담당자 가상담당 서명'],
    'exam_admission': ['응시확인서', '자격종목 정보처리기사', '응시일 2026.03.22', '시험장 전주시 합성시험장', '응시번호 000001', '상기인이 검정시험에 응시하였음을 확인합니다'],
    'exam_score': ['성적표', '자격종목 정보처리기사', '응시일 2026.03.22', '수험번호 000001', '과목 필기 점수 80', '합격 여부 합격'],
    'receipt': ['결제영수증', '품목 면접정장 대여', '결제금액 70,000', '결제일 2026.04.01', '결제수단 카드 승인번호 000000', '공급가액 63,636 부가세 6,364', '가상상점'],
    'id_photo_copy': ['면접용 증명사진 사본', '성명 가상시험', '증명사진 제출용', '사진관 가상사진관', '촬영일 2026.03.25'],
    'admin_info_consent': ['행정정보 공동이용 사전동의서', '이용기관 전북특별자치도', '이용사무 전북청년 함께 두배적금', '공동이용 행정정보 주민등록표 초본 건강보험 자격확인서', '본인정보의 공동이용에 동의합니다', '동의자 가상시험 서명'],
    'application_form': ['전북청년 함께 두배적금 참여 신청서', '저축 목적 주거자금', '유사 자산형성사업 참여 여부 미참여', '기본정보 인적 사항 신청자', '근로형태 상용직 가상사업장', '거주기간 2년 이상', '위와 같이 사업 참여를 신청합니다'],
    'self_check': ['신청자격 자가진단 및 필수사항 확인 동의서', '전북청년 함께 두배적금', '점검 내용 확인 동의', '전북특별자치도 거주자입니까 예', '근로 경력이 있습니까 예', '필수 사항에 모두 동의합니다', '자가진단 확인 서명'],
    'consent_form': ['개인정보 수집 및 이용 동의서', '전북청년 함께 두배적금 사업 대상자 선정', '수집 이용 항목 성명 주소 건강보험료', '개인정보 보유 이용 기간 5년', '개인정보 수집 이용에 동의합니다', '고유식별정보 처리에 동의합니다'],
    'third_party_consent': ['개인 신용정보 제3자 제공 동의서', '전북청년 함께 두배적금', '제공받는 자 농협은행', '적금상품 가입 및 계좌 관리', '거래 종료일로부터 5년 보유 이용', '제3자 제공에 동의합니다'],
    'job_application': ['청년 취업지원패키지 신청서', '신청분야 면접비 면접정장비 면접사진촬영비 자격증 응시료', '면접기업 소재지 전북특별자치도', '면접일 응시직군 면접비용', '자격증 시험명 시행처 응시일 시험비용', '전북청년허브센터 귀하'],
    'job_consent': ['개인정보 수집 이용 제공 동의서', '청년정책 및 취업지원 서비스 제공', '전북청년허브센터', '수집범위 성명 생년월일 계좌번호', '제공받는 자 전북창조경제혁신센터', '개인정보 보유기간 5년', '수집 이용 및 제3자 제공 동의함'],
}
OTHER_BODIES = (
    ['건강보험료 고지서', '고지년월 2026.10', '납부할 금액 110,000', '납부기한 2026.11.10', '납부 전 안내 납부 사실을 증명하지 않습니다'],
    ['전기요금 고지서', '사용기간 2026.10', '청구금액 30,000', '납부기한 2026.11.10', '고객번호 000001'],
    ['물품 거래 명세서', '합성용품 수량 2 단가 15,000', '합계 30,000', '공급자 가상상점', '대금 지급 예정'],
    ['건강보험 납부 안내문', '건강보험료 납부할 금액 110,000', '납기 내 납부 바랍니다', '문의 가상상담소', '납부 확인 증빙이 아닙니다'],
)


def document_cells(split, variant=0):
    """Reuse source train/test layout for core cases; extend same layout families."""
    if split not in SPLITS:
        raise ValueError('split must be train or test')
    core = {kind: cells for kind, cells, _ in split_documents(split)}
    for index, key in enumerate(CLASS_LABELS):
        if key in ('resident_abstract', 'nhis_payment'):
            cells = list(core[key])
        else:
            if key == 'other':
                lines = OTHER_BODIES[variant % 2 if split == 'train' else 2 + variant % 2]
                # Every split includes a health insurance bill confounder.
                if variant == 0:
                    lines = OTHER_BODIES[0]
            else:
                lines = BODIES[key]
            title = [(10, 8, lines[0])]
            if split == 'train':
                header = [(10, 15, '성명'), (10, 19, '가상시험'),
                          (38, 15, '생년월일'), (38, 19, '1999.01.01'),
                          (68, 15, '발급일'), (68, 19, '2026.11.10')]
                body = [(14, 31 + i*5, line) for i, line in enumerate(lines[1:])]
            else:
                header = [(10, 14, '성명'), (25, 14, '가상시험'),
                          (10, 18, '생년월일'), (30, 18, '1999.01.01'),
                          (10, 22, '발급일'), (30, 22, '2026.11.10')]
                body = [(10, 27 + i*5, line) for i, line in enumerate(lines[1:])]
            cells = title + header + body + [(10, 75, '합성 평가 전용 가짜 서류 - 실제 인물 및 기관 발급 문서 아님')]
        # Vary common nuisance fields independently of the target category.
        name = ('가상시험', '합성인물', '가상사람')[variant % 3]
        replacements = {'가상시험': name, '1999.01.01': ('1999.01.01','2000.02.02','1998.03.03')[variant % 3]}
        cells = [(x, y, _replace(text, replacements)) for x, y, text in cells]
        yield key, sorted(cells, key=lambda c: (c[1], c[0]))


def _replace(text, replacements):
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def generate(split, output=None, seed=SEED, variants=None, stages=STAGES):
    """Render and recognize sequentially; cache contains actual own OCR only."""
    output = Path(output) if output else ROOT / split
    variants = variants if variants is not None else (2 if split == 'train' else 1)
    if variants < 1 or split not in SPLITS or not set(stages).issubset(STAGES):
        raise ValueError('Invalid split, variants or stages')
    fonts = {name: font_path(name) for name in SPLITS[split]['fonts']}
    from ..tools.fetch_own_models import verify_models
    verify_models()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    total = len(fonts)*variants*len(CLASS_LABELS)*len(stages)
    for font_index, (font, path) in enumerate(fonts.items()):
        for variant in range(variants):
            for class_index, (kind, cells) in enumerate(document_cells(split, variant)):
                base = render(cells, path)
                for stage in stages:
                    stage_index = STAGES.index(stage)
                    sample_id = f'{split}_{font_index:02}_{variant:02}_{class_index:02}_{stage_index:02}'
                    rng = np.random.default_rng(np.random.SeedSequence([seed, 0 if split=='train' else 1, font_index, variant, class_index, stage_index]))
                    img, _, _ = degrade_with_geometry(base, stage, rng)
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    raw = buf.getvalue()
                    # Content-addressed cache is only an optimization, with no GT input.
                    digest = hashlib.sha256(raw).hexdigest()
                    cache = output / f'{sample_id}.ocr.json'
                    if cache.exists():
                        stored = json.loads(cache.read_text(encoding='utf-8'))
                    else:
                        stored = {}
                    if stored.get('image_sha256') == digest:
                        words, seconds = stored['words'], stored['ocr_seconds']
                    else:
                        result = run_ocr('own', raw, img.size)
                        if result.error:
                            raise RuntimeError('Own OCR failed; check model installation')
                        words, seconds = [asdict(w) for w in result.words], result.elapsed_sec
                    record = {'id': sample_id, 'synthetic': True, 'split': split,
                              'seed': seed, 'font': font,
                              'template_id': kind+':'+SPLITS[split]['template'],
                              'document_type': kind, 'degradation': stage,
                              'pixel_size': list(img.size), 'words': words,
                              'image_sha256': digest, 'ocr_seconds': seconds}
                    (output/f'{sample_id}.png').write_bytes(raw)
                    cache.write_text(json.dumps(record, ensure_ascii=False)+'\n', encoding='utf-8')
                    records.append(record)
                    print(f'{split} {len(records)}/{total}: {kind} {font} {stage}', flush=True)
    corpus = {'schema_version': 1, 'synthetic': True, 'split': split, 'seed': seed,
              'split_policy': SPLITS, 'samples': records}
    (output/'corpus.json').write_text(json.dumps(corpus, ensure_ascii=False)+'\n', encoding='utf-8')
    return corpus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=tuple(SPLITS), required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--variants', type=int)
    args = parser.parse_args()
    generate(args.split, args.output, args.seed, args.variants)


if __name__ == '__main__':
    main()
