/** 서식5 행정정보 공동이용 사전동의서 입력값. */

import { EMPTY_YMD, type YMD } from './ymd.ts'

export const SIGN_MODES = ['전자서명', '자필 스캔본 업로드'] as const
export type SignMode = (typeof SIGN_MODES)[number]

export interface Form5Value {
  agree: string
  name: string
  signature: string
  /** 자필 스캔본 업로드로 대신한 경우의 파일명. 전자서명 대신 쓸 수 있다. */
  handwrittenFileName: string
  /** 원문 "2026 년 월 일" 작성일 */
  writtenOn: YMD
  birth: YMD
  phone: string
}

export const EMPTY_FORM5: Form5Value = {
  agree: '',
  name: '',
  signature: '',
  handwrittenFileName: '',
  writtenOn: EMPTY_YMD,
  birth: EMPTY_YMD,
  phone: '',
}
