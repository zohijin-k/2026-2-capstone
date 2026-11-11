/** 서식5 행정정보 공동이용 사전동의서 입력값. */

import { EMPTY_YMD, type YMD } from './ymd.ts'

export const SIGN_MODES = ['화면에 서명', '서명 이미지 올리기'] as const
export type SignMode = (typeof SIGN_MODES)[number]

export interface Form5Value {
  agree: string
  name: string
  signature: string
  /** 신청 건 비공개 저장소에 서명 스캔 이미지가 있는지 서버가 관리한다. */
  signatureScanUploaded: boolean
  /** 원문 "2026 년 월 일" 작성일 */
  writtenOn: YMD
  birth: YMD
  phone: string
}

export const EMPTY_FORM5: Form5Value = {
  agree: '',
  name: '',
  signature: '',
  signatureScanUploaded: false,
  writtenOn: EMPTY_YMD,
  birth: EMPTY_YMD,
  phone: '',
}
