/** 서식3·4 동의 값. */

export interface ConsentValue {
  /** 서식3 일반 개인정보 */
  privacy: string
  /** 서식3 고유식별정보(주민등록번호) */
  uniqueId: string
  /** 서식4 제3자(농협은행) 제공 */
  thirdParty: string
}

export const EMPTY_CONSENT: ConsentValue = { privacy: '', uniqueId: '', thirdParty: '' }

export const CONSENT_OPTIONS = ['동의함', '동의하지 않음'] as const
