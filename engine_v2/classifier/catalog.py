"""Content categories; preserve existing slots/engine keys, never infer from paths.

work_proof accepts several types, so insurance_4 names its document subtype.
Repeated interview/receipt slots likewise cannot be inferred from page content.
Form-only categories have no upload slot and use form identifiers here.
"""
from demo.backend.rules.doc_types import DocType

CLASS_LABELS = {
    'resident_abstract': '주민등록초본',
    'resident_register': '주민등록등본',
    'nhis_payment': '건강보험료 납부확인서',
    'nhis_qualification': '건강보험 자격확인서',
    'nhis_acquisition_loss': '건강보험 자격득실확인서',
    'insurance_4': '4대보험 가입내역 확인서',
    'interview_confirm': '면접확인서',
    'exam_admission': '응시확인서',
    'exam_score': '성적표',
    'receipt': '결제영수증',
    'id_photo_copy': '면접용 사진 사본',
    'admin_info_consent': '행정정보 공동이용 사전동의서',
    'application_form': '두배적금 참여 신청서',
    'self_check': '신청자격 자가진단 및 필수사항 확인 동의서',
    'consent_form': '개인정보 수집 및 이용 동의서',
    'third_party_consent': '개인 신용정보 제3자 제공 동의서',
    'job_application': '청년 취업지원패키지 신청서',
    'job_consent': '개인정보 수집 이용 제공 동의서',
    'other': '기타',
}

RULE_KEYS = {
    DocType.RESIDENT_ABSTRACT: 'resident_abstract',
    DocType.RESIDENT_CERTIFICATE: 'resident_register',
    DocType.NHIS_PAYMENT: 'nhis_payment',
    DocType.NHIS_QUALIFICATION: 'nhis_qualification',
    DocType.NHIS_ACQUISITION_LOSS: 'nhis_acquisition_loss',
    DocType.INSURANCE_4: 'insurance_4',
    DocType.INTERVIEW_CONFIRMATION: 'interview_confirm',
    DocType.EXAM_CONFIRMATION: 'exam_admission',
    DocType.EXAM_TRANSCRIPT: 'exam_score',
    DocType.PAYMENT_RECEIPT: 'receipt',
    DocType.ID_PHOTO_COPY: 'id_photo_copy',
    DocType.ADMIN_INFO_CONSENT: 'admin_info_consent',
}


def rule_predict(words):
    """Run unchanged production body rules on identical recognized text.

    No rule match is abstention, NOT a successful prediction of 'other'.
    Unsupported positive rule matches retain their enum name, not 'other'.
    """
    from demo.backend.ocr.pdftext import classify
    text = '\n'.join(w['text'] if isinstance(w, dict) else w.text for w in words)
    detected = classify(text)
    return RULE_KEYS.get(detected, detected.name.lower() if detected else None)
