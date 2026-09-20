/** 서식1 입력값과 선택지. 문구는 시행지침 p.23~24 원문 그대로. */

import { EMPTY_YMD, type YMD } from './ymd.ts'

export const SAVING_PURPOSES = [
  '주거자금',
  '창업자금',
  '본인 및 자녀의 교육·훈련비',
  '대출상환',
  '결혼자금',
  '기타 꿈을 위한 준비자금',
] as const

export const HOUSEHOLD_TYPES = [
  '기초생활보장급여 수급 가구',
  '법정 차상위계층 가구',
  '그 외 일반 가구',
] as const

export const HOUSEHOLD_SIZES = [
  '1인', '2인', '3인', '4인', '5인',
  '6인', '7인', '8인', '9인', '10인 이상',
] as const

export const WORK_TYPES = [
  '상용직(노동계약기간 1년 이상)',
  '임시직(노동계약기간 1개월 이상 1년 미만)',
  '일용직(노동계약기간 1개월 미만)',
  '기타(상용직, 임시직, 일용직 혼합)',
] as const

export const WORKPLACE_REGIONS = [
  '전북특별자치도 내 지역',
  '전북특별자치도 외 지역',
] as const

export const ADMIN_WORK_FORMS = ['무기계약 근로자', '기간제 근로자'] as const

export const REFERRAL_PATHS = [
  'TV 자막광고·신문 등 방송매체',
  '홈페이지(도, 시군, 청년센터 등)',
  'SNS(인스타그램)',
  '현수막',
  '전광판, 버스 등 옥외매체',
  '지인소개',
  '기타',
] as const

export const FORM1_AGREEMENTS = [
  '위 기재사실 및 제출서류에 허위가 있는 경우 선정이 취소될 수 있으며, 제출한 서류는 선정여부와 상관없이 일체 반환하지 않는 것에 동의합니다.',
  '위의 내용 및 사업 공고문과 신청 안내문을 확인하였고 해당내용에 동의합니다.',
  '신청조사와 별도로 가입기간 중 실시하는 확인조사를 통해 기준 부적합 시 중도해지하는 것에 동의합니다.',
] as const

export interface Form1Value {
  savingPurpose: string
  priorJoined: string
  priorName: string
  priorPeriod: string
  priorAmount: string
  name: string
  birth: YMD
  gender: string
  address: string
  mobile: string
  email: string
  ecName: string
  ecRelation: string
  ecContact: string
  transferIn: YMD
  householdType: string
  householdSize: string
  workType: string
  employedAt: YMD
  workplaceRegion: string
  workplaceName: string
  adminWorkForm: string
  workplaceAddress: string
  workplaceContact: string
  bankName: string
  accountNo: string
  accountHolder: string
  /** 통장 사본(본인 명의) 첨부 파일명. 데모는 파일 자체를 보내지 않고 이름만 든다. */
  bankbookFileName: string
  referralPaths: string[]
}

export const EMPTY_FORM1: Form1Value = {
  savingPurpose: '',
  priorJoined: '',
  priorName: '',
  priorPeriod: '',
  priorAmount: '',
  name: '',
  birth: EMPTY_YMD,
  gender: '',
  address: '',
  mobile: '',
  email: '',
  ecName: '',
  ecRelation: '',
  ecContact: '',
  transferIn: EMPTY_YMD,
  householdType: '',
  householdSize: '',
  workType: '',
  employedAt: EMPTY_YMD,
  workplaceRegion: '',
  workplaceName: '',
  adminWorkForm: '',
  workplaceAddress: '',
  workplaceContact: '',
  bankName: '',
  accountNo: '',
  accountHolder: '',
  bankbookFileName: '',
  referralPaths: [],
}
