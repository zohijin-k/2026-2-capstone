/**
 * 담당자 화면 목업 데이터 — 백엔드 없이 "다양한 사람이 신청하면 이렇게 보인다"를
 * 보여주기 위한 프론트엔드 전용 데이터셋이다.
 *
 * 이 모듈이 지키는 규칙 셋:
 *
 *   1. **모양은 백엔드 응답과 같다.** `api.ts`의 `OfficerList`·`ReviewDetailData`를
 *      그대로 만족시킨다. 화면 컴포넌트는 목업인지 실데이터인지 모른 채 동작한다.
 *   2. **계산은 백엔드 규칙을 그대로 옮긴다.** 배점 구간(`rules/scoring.py`),
 *      동점자 키(시행지침 ①~④), 시군별 정원(`rules/programs.py`), 역할 3계층
 *      (`rules/roles.py`)이 서버 값과 어긋나면 목업을 보고 내린 판단이 실제와
 *      달라진다. 상수를 여기서 다시 쓰되 출처를 주석으로 남긴다.
 *   3. **행은 하드코딩하지 않고 생성한다.** 시연에 필요한 규모(시군별 정원 대비
 *      진행률·커트라인)는 수천 건이라 손으로 못 적는다. 대신 **고정 시드 난수**로
 *      만들어 새로고침해도 같은 화면이 나오게 한다.
 *
 * 목업을 켜는 방법과 다른 두 가지 대안(실제 신청 플로우 시드 / DB 직접 삽입)은
 * `demo/docs/officer-mock-data.md`에 적어 두었다.
 */

import type {
  DecisionKey,
  DocStatus,
  OfficerDocument,
  OfficerList,
  OfficerListQuery,
  OfficerRole,
  OfficerRow,
  OfficerRowDoc,
  QuotaRow,
  ReviewDetailData,
  ScoreItemRow,
} from '../../api.ts'

/** 목업 신청 건의 id 시작점. 실제 DB id(1부터)와 절대 겹치지 않게 띄워 둔다. */
export const MOCK_ID_BASE = 900_000

export const isMockId = (applicationId: number) => applicationId >= MOCK_ID_BASE

// ---------------------------------------------------------------- 서버 상수 사본

const DOUBLE_SAVINGS = 'double_savings'
const JOB_PACKAGE = 'job_package'

const PROGRAM_NAMES: Record<string, string> = {
  [DOUBLE_SAVINGS]: '전북청년 함께 두배적금',
  [JOB_PACKAGE]: '전북청년 취업지원패키지',
}

/** 시행지침 '26년 시군별 배정 인원 (총 1,300명). `rules/programs.py`와 같은 값. */
const QUOTA: Record<string, number> = {
  전주시: 550,
  군산시: 180,
  익산시: 200,
  정읍시: 75,
  남원시: 50,
  김제시: 50,
  완주군: 60,
  진안군: 15,
  무주군: 15,
  장수군: 15,
  임실군: 15,
  순창군: 15,
  고창군: 30,
  부안군: 30,
}

const REGIONS = Object.keys(QUOTA)

// ---------------------------------------------------------------- 취업지원패키지
//
// 아래 값은 전부 「2026년 전북청년 취업지원패키지 사업계획」 원문이다. 이 사업은
// **점수표가 없다** — 선착순으로 받고, 담당자가 볼 것은 "신청한 항목마다 필요한
// 서류가 다 왔는가, 그 서류가 **인정 기간 안의 것인가**"뿐이다.

/** 「3. 지원금 지급 — 지원규모 : 총 900건」. 성과목표 4종의 합과 같다. */
const JOB_PACKAGE_QUOTA = 900

/**
 * 「※ 2026. 1. 1. 이후의 서류만 인정」.
 *
 * 이 한 줄이 취업패키지 심사의 축이다. 면접확인서의 면접일, 영수증의 결제일,
 * 응시확인서의 응시일, 초본의 발급일이 모두 이 날짜 이후여야 한다.
 */
const JOB_DOC_CUTOFF = '2026-01-01'

/** 「신청기간」 1차 2026. 4. 6.(월) ~ 5. 1.(금) / 2차 2026. 9. 7.(월) ~ 10. 2.(금). */
const JOB_APPLY_ROUNDS: { label: string; from: string; to: string; share: number }[] = [
  // 1차는 마감됐고, 2차는 접수 중이다 — 담당자 화면에 마감된 건과 진행 중인 건이
  // 같이 보여야 보완 기한 D-day가 뜻을 갖는다.
  { label: '1차', from: '2026-04-06', to: '2026-05-01', share: 0.74 },
  { label: '2차', from: '2026-09-07', to: '2026-09-16', share: 0.26 },
]

/** 「7일 내 서류 보완안내 / 미보완시 지원대상자 제외 및 후순위자 선정」. */
const JOB_SUPPLEMENT_DAYS = 7

type ItemKey = 'interview' | 'suit' | 'photo' | 'certificate'

/** 서류 한 칸의 명세. `dateField`가 인정 기간(2026.1.1. 이후)을 재는 기준 항목이다. */
interface JobDocSpec {
  suffix: string
  docType: string
  label: string
  /** 인정 기간 판정의 기준이 되는 날짜 항목. */
  dateField: string
  /** 이 자리에 인정되는 서류가 여럿인 경우 (응시확인서 **또는** 성적표). */
  accepted?: string[]
}

/**
 * 지원 항목 4종 — 사업계획서 「지원내용」 표 + 「신청서류」 표.
 *
 * | 구분 | 지원금액 | 비고 | 추가서류 |
 * |---|---|---|---|
 * | 면 접 비 | 50,000원(회당) | 최대 2회 | 면접확인서 |
 * | 정 장 비 | 50,000원(실비) | 최대 2회 | 면접확인서 + 결제영수증 |
 * | 면접사진 | 20,000원(실비) | 1회 | 면접용 사진사본 + 결제영수증 |
 * | 자 격 증 | 50,000원(실비) | 최대 2회 | 응시확인서 또는 성적표(응시일 표기 필수) + 결제영수증 |
 *
 * **면접비만 정액**이다("회당"). 나머지 3종은 "(실비)"라 영수증 금액과 한도 중
 * 작은 값을 지급한다. `rules/subsidy.py`의 `LIMITS`와 같은 값이다.
 */
const JOB_ITEMS: Record<
  ItemKey,
  {
    label: string
    unitCap: number
    maxCount: number
    actualCost: boolean
    /** 「4. 성과목표」 건수. 항목을 고르는 가중치로 쓴다. */
    target: number
    docs: JobDocSpec[]
  }
> = {
  interview: {
    label: '면접비',
    unitCap: 50_000,
    maxCount: 2,
    actualCost: false,
    target: 330,
    docs: [
      {
        suffix: 'confirmation',
        docType: '면접확인서',
        label: '면접확인서',
        dateField: '면접일',
      },
    ],
  },
  suit: {
    label: '면접정장비',
    unitCap: 50_000,
    maxCount: 2,
    actualCost: true,
    target: 20,
    docs: [
      {
        suffix: 'confirmation',
        docType: '면접확인서',
        label: '면접확인서',
        dateField: '면접일',
      },
      { suffix: 'receipt', docType: '결제영수증', label: '결제영수증', dateField: '결제일' },
    ],
  },
  photo: {
    label: '면접사진비',
    unitCap: 20_000,
    maxCount: 1,
    actualCost: true,
    target: 150,
    docs: [
      {
        suffix: 'photo',
        docType: '면접용사진사본',
        label: '면접용 사진사본',
        dateField: '촬영일',
      },
      { suffix: 'receipt', docType: '결제영수증', label: '결제영수증', dateField: '결제일' },
    ],
  },
  certificate: {
    label: '자격증 응시료',
    unitCap: 50_000,
    maxCount: 2,
    actualCost: true,
    target: 400,
    docs: [
      {
        suffix: 'exam',
        docType: '응시확인서',
        label: '응시확인서 또는 성적표',
        // 사업계획서 신청서류 표의 괄호 주석: "(응시일 표기 필수)"
        dateField: '응시일',
        accepted: ['응시확인서', '성적표'],
      },
      { suffix: 'receipt', docType: '결제영수증', label: '결제영수증', dateField: '결제일' },
    ],
  },
}

const ITEM_ORDER: ItemKey[] = ['interview', 'suit', 'photo', 'certificate']

/** 면접확인서를 발급하는 도내 기업·기관. */
const JOB_EMPLOYERS = [
  '(주)전주정밀',
  '익산바이오소재(주)',
  '군산조선기자재(주)',
  '전북테크노파크',
  '(재)전북문화관광재단',
  '전주정보문화산업진흥원',
  '완주신재생에너지(주)',
  '정읍첨단과학산업단지(주)',
  '(주)남원식품',
  '김제자유무역지역관리원',
  '전북대학교병원',
  '(주)부안해상풍력',
]

/** 자격증명 · 실제 응시료 · 시험 시행기관. 응시료가 한도(5만원)를 넘는 것도 섞는다. */
const CERTIFICATES: [string, number, string][] = [
  ['정보처리기사 필기', 19_400, '한국산업인력공단'],
  ['정보처리기사 실기', 22_600, '한국산업인력공단'],
  ['컴퓨터활용능력 1급 실기', 25_000, '대한상공회의소'],
  ['한국사능력검정시험 심화', 22_000, '국사편찬위원회'],
  ['지게차운전기능사 실기', 29_000, '한국산업인력공단'],
  ['전기기사 실기', 22_600, '한국산업인력공단'],
  ['산업안전기사 실기', 34_000, '한국산업인력공단'],
  ['사회복지사 2급 과정평가', 48_000, '한국사회복지사협회'],
  ['TOEIC 정기시험', 52_500, 'YBM 한국TOEIC위원회'],
  ['조리기능사 실기', 26_900, '한국산업인력공단'],
  ['전산회계 1급', 30_000, '한국세무사회'],
  ['전산세무 2급', 30_000, '한국세무사회'],
  ['미용사(일반) 실기', 64_000, '한국산업인력공단'],
  ['토익스피킹(TOEIC Speaking)', 84_000, 'YBM 한국TOEIC위원회'],
  ['OPIc 영어', 84_000, '(주)크레듀'],
  ['투자자산운용사', 50_000, '금융투자협회'],
]

/** 정장 대여 가맹점과 대여비. 한도(5만원)를 넘는 금액이 절반쯤 섞인다. */
const SUIT_SHOPS: [string, number][] = [
  ['전주 슈트렌탈', 35_000],
  ['청년정장 전주점', 45_000],
  ['익산 포멀웨어', 50_000],
  ['군산 수트하우스', 70_000],
  ['전주 클래식슈트', 90_000],
  ['전북 정장대여센터', 120_000],
]

/** 증명사진 촬영 스튜디오와 촬영비. 한도는 2만원이다. */
const PHOTO_STUDIOS: [string, number][] = [
  ['전주 시그니처스튜디오', 15_000],
  ['익산 프로필사진관', 18_000],
  ['군산 데일리스튜디오', 20_000],
  ['전주 취업사진관', 25_000],
  ['정읍 포토그레이', 30_000],
]

/** 시군별 읍·면·동. 읍면동 역할이 관할을 고를 때 쓴다. */
const TOWNS: Record<string, string[]> = {
  전주시: ['효자동', '인후동', '서신동', '평화동', '삼천동', '송천동', '덕진동', '우아동'],
  군산시: ['나운동', '수송동', '미룡동', '조촌동', '옥산면', '개정면'],
  익산시: ['영등동', '부송동', '어양동', '모현동', '함열읍', '황등면'],
  정읍시: ['수성동', '연지동', '상동', '신태인읍', '태인면'],
  남원시: ['도통동', '죽항동', '향교동', '운봉읍', '인월면'],
  김제시: ['요촌동', '신풍동', '검산동', '만경읍', '백산면'],
  완주군: ['삼례읍', '봉동읍', '용진읍', '이서면', '소양면'],
  진안군: ['진안읍', '마령면', '부귀면'],
  무주군: ['무주읍', '설천면', '안성면'],
  장수군: ['장수읍', '번암면', '계남면'],
  임실군: ['임실읍', '오수면', '강진면'],
  순창군: ['순창읍', '인계면', '동계면'],
  고창군: ['고창읍', '흥덕면', '대산면', '해리면'],
  부안군: ['부안읍', '줄포면', '계화면', '변산면'],
}

/** 항목 1. 중위소득 — (하한 %, 점수, 구간 라벨). `rules/scoring.INCOME_BANDS`. */
const INCOME_BANDS: [number, number, string][] = [
  [130, 28, '130% 이상'],
  [120, 31, '120% 이상 ~ 130% 미만'],
  [110, 34, '110% 이상 ~ 120% 미만'],
  [100, 37, '100% 이상 ~ 110% 미만'],
  [0, 40, '100% 미만'],
]

/** 항목 2. 도 거주기간 — 만 경과 연수 → (점수, 구간 라벨). */
const RESIDENCE_BANDS: [number, string][] = [
  [15, '1년 미만'],
  [17, '1년 이상 ~ 2년 미만'],
  [19, '2년 이상 ~ 3년 미만'],
  [21, '3년 이상 ~ 4년 미만'],
  [23, '4년 이상 ~ 5년 미만'],
  [25, '5년 이상'],
]

/** 항목 3. 현직장 근로기간. */
const WORK_BANDS: [number, string][] = [
  [16, '1년 미만'],
  [19, '1년 이상 ~ 2년 미만'],
  [22, '2년 이상 ~ 3년 미만'],
  [25, '3년 이상'],
]

/** 항목 4. 연령 — (상한 만나이, 점수, 구간 라벨). */
const AGE_BANDS: [number, number, string][] = [
  [24, 10, '24세 이하'],
  [29, 9, '25~29세'],
  [34, 8, '30~34세'],
  [200, 7, '35세 이상'],
]

/** 신청 자격 상한. 넘으면 점수와 무관하게 부적합이다. */
const INCOME_LIMIT_PERCENT = 140

/** 거주·근로기간 역산 기준일이자 공고일. */
const ANNOUNCEMENT_DATE = new Date('2026-03-03T00:00:00')

const AI_STATUS_LABELS: Record<DocStatus, string> = {
  PASS: '적합',
  FAIL: '부적합',
  NEEDS_REVIEW: '확인필요',
}

const PENDING = 'pending'

/**
 * 두배적금 업로드 슬롯의 순서·표기. `api/officer.DOC_COLUMNS`와 같은 순서다.
 *
 * 목록의 서류 컬럼이 이 배열에서 나온다. 서버 응답과 컬럼 개수·순서·라벨이
 * 어긋나면 목업 화면과 실데이터 화면이 다른 표가 되고, 그러면 목업으로 시연한
 * 것이 실제로 되는지 아무도 확신할 수 없다.
 */
const SAVINGS_DOC_COLUMNS: [string, string][] = [
  ['resident_abstract', '초본'],
  ['nhis_payment', '건보료'],
  ['nhis_qualification', '자격확인'],
  ['nhis_acquisition_loss', '자격득실'],
  ['work_proof', '근로확인서류'],
  ['__other__', '기타'],
]

/** 실제로 올려야 하는 슬롯. `기타`는 컬럼이지 슬롯이 아니다. */
const SAVINGS_SLOT_ORDER = SAVINGS_DOC_COLUMNS.slice(0, 5).map(([slot]) => slot)

/** 헤더가 서류명을 쥐는 칸. 서버의 `FIXED_DOC_COLUMNS`와 같다. */
const FIXED_DOC_COLUMNS = new Set(SAVINGS_SLOT_ORDER.slice(0, 4))

/** 서류 칸의 상태 표기. 서버의 `DOC_STATE_LABELS`와 같다. */
const DOC_STATE_LABELS: Record<string, string> = {
  PASS: '적합',
  FAIL: '부적합',
  NEEDS_REVIEW: '확인필요',
}

/** 목록 컬럼 (점수제). `api/officer.LIST_COLUMNS`와 같은 순서·라벨. */
const LIST_COLUMNS = [
  { key: 'application_no', label: '신청번호' },
  { key: 'name', label: '성명' },
  { key: 'region', label: '시군' },
  { key: 'ai_status', label: 'AI판정' },
  { key: 'total_score', label: '점수' },
  { key: 'missing_count', label: '미비서류' },
  // 서류 컬럼은 미비 개수 바로 뒤에 온다 — 개수를 보고 "어디가 걸렸나"로 눈이
  // 이어지는 순서다. 목록은 `SAVINGS_DOC_COLUMNS`에서 조립한다.
  ...SAVINGS_DOC_COLUMNS.map(([slot, label]) => ({ key: `doc:${slot}`, label })),
  { key: 'submitted_at', label: '접수일시' },
  { key: 'decision', label: '처리상태' },
]

/**
 * 목록 컬럼 (선착순).
 *
 * 점수 칸을 **신청 항목**으로 바꾼다. 취업패키지에는 심사표가 없어 점수 칸이
 * 전건 비어 있고, 담당자가 목록에서 먼저 보는 것은 "이 사람이 무엇을 신청했고
 * 그 항목 서류가 몇 장 걸렸는가"이기 때문이다.
 */
const FIRST_COME_COLUMNS = [
  { key: 'application_no', label: '신청번호' },
  { key: 'name', label: '성명' },
  { key: 'region', label: '시군' },
  { key: 'items', label: '신청 항목' },
  { key: 'ai_status', label: 'AI판정' },
  { key: 'missing_count', label: '미비서류' },
  { key: 'submitted_at', label: '접수일시' },
  { key: 'decision', label: '처리상태' },
]

// ---------------------------------------------------------------- 역할 3계층

/** `rules/roles.py`의 ROLES를 그대로 옮긴 것. 문구가 어긋나면 안 된다. */
export const MOCK_ROLES: OfficerRole[] = [
  {
    key: 'town',
    name: '읍·면·동',
    stage: '선발절차 2·3·4단계',
    scope: '관할 읍·면·동 접수 건',
    requires_region: true,
    requires_town: true,
    quota_ratio: null,
    can_bulk: false,
    notes: [
      '구비서류 완비 여부(서명·직인 포함)를 건별로 확인합니다.',
      '자격요건과 제외대상을 확인하고 심사표를 작성합니다.',
      '건별 확인이 원칙이라 일괄 처리는 제공하지 않습니다.',
    ],
    actions: [
      { key: 'approve', label: '구비서류 완비 확인', result_label: '서류 완비 확인', tone: 'primary' },
      { key: 'hold', label: '보류', result_label: '보류', tone: 'neutral' },
      { key: 'reject', label: '반려', result_label: '반려', tone: 'danger' },
    ],
  },
  {
    key: 'city',
    name: '시군',
    stage: '선발절차 1·5단계',
    scope: '관할 시군 전체',
    requires_region: true,
    requires_town: false,
    quota_ratio: 1.2,
    can_bulk: true,
    notes: [
      '읍·면·동이 작성한 심사표를 취합·검토합니다.',
      '고득점순으로 배정인원의 120%를 선발해 도에 공문으로 제출합니다.',
    ],
    actions: [
      { key: 'approve', label: '1차 선발 (배정인원 120%)', result_label: '1차 선발', tone: 'primary' },
      { key: 'hold', label: '보류', result_label: '보류', tone: 'neutral' },
      { key: 'reject', label: '반려', result_label: '반려', tone: 'danger' },
    ],
  },
  {
    key: 'province',
    name: '도·청년허브센터',
    stage: '선발절차 6단계',
    scope: '14개 시군 전체',
    requires_region: false,
    requires_town: false,
    quota_ratio: 1.0,
    can_bulk: true,
    notes: ['2차 검증(중복 조회) 후 고득점순으로 100%를 최종 선정·공고합니다.'],
    actions: [
      { key: 'approve', label: '최종 선정 (100%)', result_label: '최종 선정', tone: 'primary' },
      { key: 'hold', label: '보류', result_label: '보류', tone: 'neutral' },
      { key: 'reject', label: '반려', result_label: '반려', tone: 'danger' },
    ],
  },
]

const roleOf = (key: string): OfficerRole =>
  MOCK_ROLES.find((r) => r.key === key) ?? MOCK_ROLES[2]

/** 저장된 판단값 → 역할별 화면 표기. `rules/roles.decision_label`과 같다. */
function decisionLabel(roleKey: string | null, decision: DecisionKey | null): string {
  if (!decision) return '미처리'
  const role = MOCK_ROLES.find((r) => r.key === roleKey)
  const action = role?.actions.find((a) => a.key === decision)
  if (action) return action.result_label
  return { approve: '승인', reject: '반려', hold: '보류' }[decision]
}

// ---------------------------------------------------------------- 난수

/**
 * 고정 시드 난수 (mulberry32).
 *
 * 새로고침할 때마다 목록이 바뀌면 시연 대본을 쓸 수 없다. 같은 시드로 항상 같은
 * 2천여 건이 나오게 한다.
 */
function rng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const pick = <T,>(random: () => number, xs: readonly T[]): T =>
  xs[Math.floor(random() * xs.length)]

const between = (random: () => number, lo: number, hi: number): number =>
  lo + Math.floor(random() * (hi - lo + 1))

/**
 * 가운데가 두툼한 분포 (균등분포 `draws`회의 평균).
 *
 * 균등분포로 뽑으면 만점자가 너무 많이 나온다 — 신청자 2천 명 중 100명이 100점이면
 * 심사표에 변별력이 없다는 뜻이라 커트라인 시연이 무의미해진다. 연령과 소득을
 * 중앙에 모아 실제 접수 분포에 가깝게 만든다.
 */
function bell(random: () => number, lo: number, hi: number, draws = 2): number {
  let sum = 0
  for (let i = 0; i < draws; i += 1) sum += lo + random() * (hi - lo)
  return sum / draws
}

// ---------------------------------------------------------------- 신청자 이름

const SURNAMES = [
  '김', '이', '박', '최', '정', '강', '조', '윤', '장', '임',
  '한', '오', '서', '신', '권', '황', '안', '송', '전', '홍',
  '유', '고', '문', '양', '손', '배', '백', '허', '남', '심',
]

const GIVEN_NAMES = [
  '지훈', '서연', '민준', '하은', '도윤', '수아', '시우', '지우', '예준', '하윤',
  '주원', '서윤', '건우', '지민', '현우', '유진', '준서', '다인', '민재', '채원',
  '태현', '소율', '지한', '예은', '승우', '나윤', '은우', '시은', '지호', '가은',
  '동현', '혜원', '세준', '수빈', '재원', '다현', '우진', '연우', '성민', '윤서',
  '진우', '보라', '경민', '슬기', '영수', '미영', '정호', '은지', '상현', '지아',
]

// ---------------------------------------------------------------- 채점

interface Scored {
  incomePercent: number
  residenceYears: number
  workYears: number
  age: number
  items: { key: string; band: string; score: number; max: number }[]
  total: number
}

function bandOf<T extends [number, ...unknown[]]>(bands: T[], value: number): T {
  return bands.find((b) => value >= b[0]) ?? bands[bands.length - 1]
}

function score(incomePercent: number, residenceYears: number, workYears: number, age: number): Scored {
  const income = bandOf(INCOME_BANDS, incomePercent)
  const residence = RESIDENCE_BANDS[Math.min(residenceYears, RESIDENCE_BANDS.length - 1)]
  const work = WORK_BANDS[Math.min(workYears, WORK_BANDS.length - 1)]
  const ageBand = AGE_BANDS.find((b) => age <= b[0]) ?? AGE_BANDS[AGE_BANDS.length - 1]

  const items = [
    { key: 'income', band: income[2], score: income[1], max: 40 },
    { key: 'residence', band: residence[1], score: residence[0], max: 25 },
    { key: 'work', band: work[1], score: work[0], max: 25 },
    { key: 'age', band: ageBand[2], score: ageBand[1], max: 10 },
  ]
  return {
    incomePercent,
    residenceYears,
    workYears,
    age,
    items,
    total: items.reduce((sum, i) => sum + i.score, 0),
  }
}

// ---------------------------------------------------------------- 한 건

/** 엔진이 내는 판정 사유 한 줄. */
interface Reason {
  stage: string
  code: string
  message: string
  doc_type: string | null
}

/**
 * 업로드 서류 1장 (목업).
 *
 * 취업패키지 심사는 이 배열을 훑는 일이 전부다 — 항목마다 필요한 서류가 왔는지,
 * 그 서류의 기준 날짜가 2026. 1. 1. 이후인지.
 */
interface MockDoc {
  slotKey: string
  label: string
  docType: string
  expectedDocType: string
  /** 판독 결과. 화면의 '판독 결과' 패널과 bbox 하이라이트가 이 순서를 쓴다. */
  fields: Record<string, string>
  /** 인정 기간을 재는 기준 항목의 이름 (면접일·응시일·결제일·발급일). */
  dateField: string
  status: DocStatus
  findings: { code: string; message: string; how_to_fix: string; severity: DocStatus }[]
  /** 영수증이면 판독된 결제금액. 정액 항목·비영수증 서류는 null. */
  receiptAmount: number | null
}

/** 신청자가 고른 지원 항목 1종. 회차마다 서류가 따로 붙는다. */
interface JobSelection {
  key: ItemKey
  count: number
  /** 회차별 영수증 금액. 정액 항목(면접비)은 전부 null. */
  receipts: (number | null)[]
  /**
   * 금액은 읽었지만 그대로 지급하면 안 되는 회차.
   *
   * 실제 사례: "전산세무 2급 시험료는 3만원인데 결제영수증이 6만원이라 지원금이
   * 총 89,500원. 이거 확인필요함." 금액이 계산은 되지만 담당자가 한 번 봐야 한다.
   */
  receiptFlagged: boolean[]
}

/** 목록 행 + 상세 화면이 같이 읽는 목업 1건. */
interface MockEntry {
  row: OfficerRow
  scored: Scored | null
  birth: string
  address: string
  transferIn: string
  employedAt: string
  householdSize: number
  monthlyPremium: number
  insuranceType: string
  /** 근로확인서류 1종을 정하는 축. 취업패키지 건에서는 쓰지 않는다. */
  workCategory: WorkCategory | null
  reasons: Reason[]
  /** 상세 화면 좌측 탭에 뜨는 서류들. */
  docs: MockDoc[]
  /** 취업패키지에서 고른 지원 항목. 두배적금은 빈 배열이다. */
  selections: JobSelection[]
  /** 서류 보완 기한 (접수 + 7일). 보완 대상이 아니면 null. */
  supplementDeadline: string | null
  /** 동점자 정렬 키 (시행지침 ①~④). 오름차순 정렬이 곧 순위다. */
  tiebreak: number[]
  memo: string | null
  decidedAt: string | null
}

const iso = (d: Date) => d.toISOString().slice(0, 19)

/** 공고일(2026-03-03)에서 대략 `years`년 전의 날짜 하나. 월·일은 무작위다. */
function dateYearsBefore(random: () => number, years: number): string {
  const year = ANNOUNCEMENT_DATE.getFullYear() - years
  const month = between(random, 1, 12)
  const day = between(random, 1, 28)
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/**
 * 그 날짜부터 공고일까지의 **만 경과 연수**.
 *
 * 배점 구간도 근거 문장도 이 값 하나만 본다. 둘이 다른 값을 쓰면 담당자가 읽는
 * 근거와 실제 점수가 어긋난다.
 */
function fullYears(fromIso: string): number {
  const from = new Date(`${fromIso}T00:00:00`)
  let years = ANNOUNCEMENT_DATE.getFullYear() - from.getFullYear()
  const months = ANNOUNCEMENT_DATE.getMonth() - from.getMonth()
  if (months < 0 || (months === 0 && ANNOUNCEMENT_DATE.getDate() < from.getDate())) years -= 1
  return Math.max(0, years)
}

/** 접수 일시 — 두배적금 신청기간 2026.3.3.(화) 09:00 ~ 3.16.(월) 18:00 안에서 고른다. */
function submittedAt(random: () => number): string {
  const day = between(random, 3, 16)
  return `2026-03-${String(day).padStart(2, '0')}T${clockOf(random)}`
}

const clockOf = (random: () => number) =>
  `${String(between(random, 9, 17)).padStart(2, '0')}:${String(between(random, 0, 59)).padStart(
    2,
    '0',
  )}:${String(between(random, 0, 59)).padStart(2, '0')}`

const dayNumber = (isoDate: string) => Math.floor(Date.parse(`${isoDate}T00:00:00Z`) / 86_400_000)

const dateFromDayNumber = (day: number) =>
  new Date(day * 86_400_000).toISOString().slice(0, 10)

/** 취업패키지 접수 일시 — 1차(4.6~5.1) 또는 2차(9.7~9.16) 안에서 고른다. */
function jobSubmittedAt(random: () => number): string {
  const dice = random()
  let acc = 0
  let round = JOB_APPLY_ROUNDS[0]
  for (const candidate of JOB_APPLY_ROUNDS) {
    acc += candidate.share
    if (dice <= acc) {
      round = candidate
      break
    }
  }
  const from = dayNumber(round.from)
  const to = dayNumber(round.to)
  return `${dateFromDayNumber(between(random, from, to))}T${clockOf(random)}`
}

/** `base`에서 `days`일 앞선 날짜. 서류 발급일을 접수일에서 거슬러 잡을 때 쓴다. */
const daysBefore = (baseIsoDate: string, days: number) =>
  dateFromDayNumber(dayNumber(baseIsoDate) - days)

const daysAfter = (baseIso: string, days: number) =>
  new Date(Date.parse(`${baseIso}Z`) + days * 86_400_000).toISOString().slice(0, 19)

/** 부적합·확인필요 사유 풀. 엔진 1·2단계가 실제로 내는 코드를 쓴다. */
const FAIL_REASONS = [
  {
    stage: 'stage2',
    code: 'INCOME_OVER_LIMIT',
    message: '가구 기준 중위소득 140%를 초과합니다.',
    doc_type: '건강보험료납부확인서',
  },
  {
    stage: 'stage1',
    code: 'WRONG_DOC_TYPE',
    message: '주민등록초본이 아닌 주민등록등본이 제출되었습니다.',
    doc_type: '주민등록등본',
  },
  {
    stage: 'stage1',
    code: 'ISSUED_BEFORE_CUTOFF',
    message: "공고일('26. 3. 3.) 이전 발급분입니다.",
    doc_type: '주민등록초본',
  },
  {
    stage: 'stage2',
    code: 'OUT_OF_REGION',
    message: '주민등록 주소지가 전북특별자치도 밖입니다.',
    doc_type: '주민등록초본',
  },
]

const REVIEW_REASONS = [
  {
    stage: 'stage1',
    code: 'LOW_CONFIDENCE',
    message: '판독 신뢰도가 낮아 담당자 확인이 필요합니다. (0.62)',
    doc_type: '주민등록초본',
  },
  {
    stage: 'stage1',
    code: 'MISSING_ADDRESS_HISTORY',
    message: '초본에 과거 주소 이력이 포함되지 않았습니다.',
    doc_type: '주민등록초본',
  },
  {
    stage: 'stage1',
    code: 'FILE_ENCRYPTED',
    message: '파일 암호가 해제되지 않아 일부 항목을 읽지 못했습니다.',
    doc_type: '건강보험자격확인서',
  },
]

const MEMOS = [
  '초본 주소 이력 확인 완료.',
  '자격확인서 가구원수 재확인 필요.',
  '전화 확인 — 재직 중 맞음.',
  '보완 서류 접수 대기.',
  '중복 수혜 이력 없음 확인.',
]

/** 두 사업이 공통으로 쓰는 신청자 한 사람. */
function makePerson(random: () => number, region: string) {
  const town = pick(random, TOWNS[region])
  return {
    town,
    name: `${pick(random, SURNAMES)}${pick(random, GIVEN_NAMES)}`,
    address: `전북특별자치도 ${region} ${town} ${between(random, 1, 999)}`,
  }
}

/** 담당자 처리 상태를 굴린다. 접수 초기라 대부분 미처리로 둔다. */
function rollDecision(
  random: () => number,
  aiStatus: DocStatus,
): { decision: DecisionKey | null; officerRole: string | null; memo: string | null } {
  const handled = random()
  if (handled < 0.22 && aiStatus !== 'FAIL') {
    return {
      decision: 'approve',
      officerRole: random() < 0.5 ? 'town' : 'city',
      memo: pick(random, MEMOS),
    }
  }
  if (handled < 0.28) {
    return {
      decision: aiStatus === 'FAIL' ? 'reject' : 'hold',
      officerRole: 'town',
      memo: pick(random, MEMOS),
    }
  }
  return { decision: null, officerRole: null, memo: null }
}

// ---------------------------------------------------------------- 두배적금 서류 5종
//
// 공고문 제출서류 중 **업로드 대상**은 5종이다 — ⑧ 초본, ⑦ 소득재산 증빙 3종,
// ⑥ 근로확인서류 1종. ①~⑤는 화면 작성으로 갈음한다(`rules/required_docs.py`).
// 이 중 ⑥만 근로유형에 따라 5종 중 하나로 갈린다 — 목록의 `근로확인서류` 칸에
// 사람마다 다른 서류명이 뜨는 이유다.

/** `rules/required_docs.WorkCategory`. 문자열까지 서버와 같아야 한다. */
type WorkCategory =
  | '직장가입자'
  | '지역가입자·피부양자'
  | '사업소득 사업자'
  | '농업·임업'
  | '어업'

/**
 * 근로유형 분포. 근로청년 사업이라 직장가입자가 압도적으로 두껍고,
 * 농·어업 경영주는 드물게 섞인다. 목록에서 `근로확인서류` 칸이 대부분 같은
 * 서류명이되 가끔 다른 것이 섞여야 그 칸이 무엇을 위한 것인지 보인다.
 */
const WORK_CATEGORY_WEIGHTS: [WorkCategory, number][] = [
  ['직장가입자', 0.65],
  ['지역가입자·피부양자', 0.15],
  ['사업소득 사업자', 0.12],
  ['농업·임업', 0.06],
  ['어업', 0.02],
]

const BIZ_NAMES = ['한옥마을공방', 'OO스튜디오', 'OO커피로스터스', 'OO디자인', 'OO상회']
const FARM_TYPES = ['논벼', '시설채소', '한우', '과수(사과)', '밭작물']
const FISHERY_TYPES = ['연안어업', '양식어업', '내수면어업']

/** 근로확인서류를 만드는 데 필요한 사실값. */
interface WorkProofContext {
  name: string
  birth: string
  region: string
  employedAt: string
  issued: string
  employer: string
  bizName: string
  bizNo: string
  farmNo: string
}

/**
 * 근로유형 → 그 사람이 내야 하는 근로확인서류 1종.
 *
 * `label`은 `rules/required_docs._work_proof`의 문구, `short`는
 * `api/officer.DOC_SHORT_BY_TYPE`의 표기와 같은 값이다. 목업과 서버가 다른 이름을
 * 보여주면 담당자가 두 화면을 같은 화면으로 읽지 못한다.
 */
const WORK_PROOF: Record<
  WorkCategory,
  {
    label: string
    short: string
    docType: string
    dateField: string
    fields: (ctx: WorkProofContext) => Record<string, string>
  }
> = {
  직장가입자: {
    label: '근로확인서류(4대보험 가입내역 확인서)',
    short: '4대보험 가입내역',
    docType: '4대보험가입내역확인서',
    dateField: '발급일',
    fields: (c) => ({
      성명: c.name,
      생년월일: c.birth,
      사업장명: c.employer,
      자격취득일: c.employedAt,
      가입내역: '국민연금 · 건강보험 · 고용보험 · 산재보험',
      발급일: c.issued,
    }),
  },
  '지역가입자·피부양자': {
    label: '근로확인서류(고용·산재보험 일용근로내역서)',
    short: '일용근로내역서',
    docType: '일용근로내역서',
    dateField: '발급일',
    fields: (c) => ({
      성명: c.name,
      생년월일: c.birth,
      사업장명: c.employer,
      최초근로일: c.employedAt,
      '최근 3개월 근로일수': '54일',
      발급일: c.issued,
    }),
  },
  '사업소득 사업자': {
    label: '근로확인서류(사업자등록증명)',
    short: '사업자등록증명',
    docType: '사업자등록증명',
    dateField: '발급일',
    fields: (c) => ({
      성명: c.name,
      생년월일: c.birth,
      상호: c.bizName,
      사업자등록번호: c.bizNo,
      개업일: c.employedAt,
      발급일: c.issued,
    }),
  },
  '농업·임업': {
    label: '근로확인서류(농업경영체 증명서)',
    short: '농업경영체 증명서',
    docType: '농업경영체증명서',
    dateField: '발급일',
    fields: (c) => ({
      성명: c.name,
      생년월일: c.birth,
      경영체등록번호: c.farmNo,
      경영형태: '단독경영주',
      영농형태: c.bizName,
      등록일: c.employedAt,
      발급일: c.issued,
    }),
  },
  어업: {
    label: '근로확인서류(어업경영체 증명서)',
    short: '어업경영체 증명서',
    docType: '어업경영체증명서',
    dateField: '발급일',
    fields: (c) => ({
      성명: c.name,
      생년월일: c.birth,
      경영체등록번호: c.farmNo,
      경영형태: '단독경영주',
      어업형태: c.bizName,
      등록일: c.employedAt,
      발급일: c.issued,
    }),
  },
}

/**
 * 판정 사유가 가리키는 서류 → 슬롯.
 *
 * 예전에는 서류가 한 장이라 사유를 아무 데나 얹어도 됐다. 이제 목록에 **어느
 * 서류가 걸렸는가**가 칸으로 보이므로, 사유가 엉뚱한 서류에 붙으면 담당자가
 * 클릭해 들어간 원본에 그 문제가 없다.
 */
const DOC_TYPE_TO_SLOT: Record<string, string> = {
  주민등록초본: 'resident_abstract',
  주민등록등본: 'resident_abstract',
  건강보험료납부확인서: 'nhis_payment',
  건강보험자격확인서: 'nhis_qualification',
  건강보험자격득실확인서: 'nhis_acquisition_loss',
}

/**
 * 목록의 서류 칸. 백엔드 `api/officer._doc_cells`와 **같은 규칙**을 따른다.
 *
 * `document_id`는 `toOfficerDocument`가 쓰는 것과 같은 식(신청건 × 100 + 순번)으로
 * 낸다. 목록에서 누른 칸과 상세의 탭이 같은 서류를 가리켜야 하기 때문이다.
 */
function savingsDocCells(applicationId: number, docs: MockDoc[]): OfficerRowDoc[] {
  const byIndex = new Map(docs.map((d, index) => [d.slotKey, { doc: d, index }]))
  return SAVINGS_SLOT_ORDER.map((slot) => {
    const found = byIndex.get(slot)
    const proofLabel =
      slot === 'work_proof' && found
        ? (Object.values(WORK_PROOF).find((p) => p.docType === found.doc.docType)?.short ??
          found.doc.label)
        : ''
    return {
      column: slot,
      slot_key: slot,
      // 안 낸 서류에는 판독된 라벨이 없다. 체크리스트가 정한 이름을 쓴다.
      label: found?.doc.label ?? SLOT_FALLBACK_LABELS[slot],
      short_label: FIXED_DOC_COLUMNS.has(slot) ? '' : proofLabel || '근로확인서류',
      status: found?.doc.status ?? null,
      status_label: found ? DOC_STATE_LABELS[found.doc.status] : '미제출',
      document_id: found ? applicationId * 100 + found.index : null,
      required: true,
    }
  })
}

/** 안 낸 서류 칸에 띄울 이름. 체크리스트 표기를 그대로 쓴다. */
const SLOT_FALLBACK_LABELS: Record<string, string> = {
  resident_abstract: '주민등록초본',
  nhis_payment: '2025년 건강보험료 납부확인서',
  nhis_qualification: '건강보험 자격확인서',
  nhis_acquisition_loss: '건강보험 자격득실확인서',
  work_proof: '근로확인서류',
}

/** 가중치 표에서 하나 뽑기. */
function weighted<T>(random: () => number, table: [T, number][]): T {
  const dice = random()
  let acc = 0
  for (const [value, share] of table) {
    acc += share
    if (dice <= acc) return value
  }
  return table[table.length - 1][0]
}

function makeSavingsEntry(
  random: () => number,
  id: number,
  seq: number,
  region: string,
): MockEntry {
  const { town, name, address } = makePerson(random, region)

  // --- 사람마다 다른 사실값. 날짜를 먼저 뽑고, 점수와 근거 문장은 **그 날짜에서**
  // 역산한다. 목표 연수로 점수를 매기고 날짜만 따로 찍으면 "취업일 2021-09-13 ·
  // 공고일 기준 5년 경과"처럼 근거 문장이 하루도 안 맞는 일이 생긴다.
  //
  // 근로청년 사업이라 20대 후반~30대 초반이 가장 두껍다.
  const birth = dateYearsBefore(random, Math.round(bell(random, 19, 39, 4)))
  const transferIn = dateYearsBefore(random, between(random, 0, 9))
  const employedAt = dateYearsBefore(random, between(random, 0, 5))
  const age = fullYears(birth)
  const residenceYears = fullYears(transferIn)
  const workYears = fullYears(employedAt)
  const householdSize = between(random, 1, 5)

  // 중위소득 비율. 중위 근처가 두껍고 140% 초과(자격 부적합)가 꼬리로 섞인다.
  const incomePercent = Math.round(bell(random, 55, 152, 3) * 10) / 10
  const overIncome = incomePercent > INCOME_LIMIT_PERCENT
  // 고지금액은 비율에서 역산한 느낌만 낸다 (가구원수 4인 직장가입자 기준선 311,031원).
  const monthlyPremium = Math.round((311_031 * (incomePercent / 140)) / 10) * 10

  const scored = score(incomePercent, residenceYears, workYears, age)

  // 근로유형이 근로확인서류 1종을 정한다. 건강보험 가입구분은 **여기서 따라
  // 나온다** — 건보료 확인서에 "지역가입자"라고 찍혀 있는데 4대보험 가입내역
  // 확인서를 낸 건은 말이 안 된다.
  const workCategory = weighted(random, WORK_CATEGORY_WEIGHTS)
  const insuranceType = workCategory === '직장가입자' ? '직장' : '지역'

  const submitted = submittedAt(random)
  const residenceDays = Math.round(
    (ANNOUNCEMENT_DATE.getTime() - new Date(transferIn).getTime()) / 86_400_000,
  )
  const workDays = Math.round(
    (ANNOUNCEMENT_DATE.getTime() - new Date(employedAt).getTime()) / 86_400_000,
  )

  // --- 서류 5종. 발급일은 공고일(2026-03-03) 이후, 접수일 이전이어야 인정된다.
  const submittedDate = submitted.slice(0, 10)
  const issued = daysBefore(submittedDate, between(random, 0, 8))
  const employer = pick(random, JOB_EMPLOYERS)
  const proof = WORK_PROOF[workCategory]
  const proofCtx: WorkProofContext = {
    name,
    birth,
    region,
    employedAt,
    issued,
    employer,
    bizName:
      workCategory === '농업·임업'
        ? pick(random, FARM_TYPES)
        : workCategory === '어업'
          ? pick(random, FISHERY_TYPES)
          : `${region} ${pick(random, BIZ_NAMES)}`,
    bizNo: `${between(random, 100, 999)}-${between(random, 10, 99)}-${between(random, 10_000, 99_999)}`,
    farmNo: `${between(random, 1000, 9999)}-${between(random, 1000, 9999)}-${between(random, 10, 99)}`,
  }

  // 판독값은 전부 **위에서 뽑은 사실값에서 나온다**. 점수 근거 문장이 같은
  // 날짜들에서 역산되므로, 서류가 다른 값을 보이면 심사표와 원본이 어긋난다.
  const docs: MockDoc[] = [
    {
      slotKey: 'resident_abstract',
      label: '주민등록초본',
      docType: '주민등록초본',
      expectedDocType: '주민등록초본',
      dateField: '발급일',
      status: 'PASS',
      receiptAmount: null,
      findings: [],
      fields: {
        성명: name,
        생년월일: birth,
        주소: address,
        전입일: transferIn,
        '최근 5년 주소변동': `${between(random, 1, 4)}회 (포함)`,
        병역사항: age >= 20 ? '만기전역' : '해당없음',
        발급일: issued,
      },
    },
    {
      slotKey: 'nhis_payment',
      label: '2025년 건강보험료 납부확인서',
      docType: '건강보험료납부확인서',
      expectedDocType: '건강보험료납부확인서',
      dateField: '발급일',
      status: 'PASS',
      receiptAmount: null,
      findings: [],
      fields: {
        성명: name,
        생년월일: birth,
        가입구분: `${insuranceType}가입자`,
        가구원수: `${householdSize}인`,
        건강보험료: `${monthlyPremium.toLocaleString('ko-KR')}원`,
        납부기간: "'25. 10월 ~ 12월 (3개월)",
        발급일: issued,
      },
    },
    {
      slotKey: 'nhis_qualification',
      label: '건강보험 자격확인서',
      docType: '건강보험자격확인서',
      expectedDocType: '건강보험자격확인서',
      dateField: '발급일',
      status: 'PASS',
      receiptAmount: null,
      findings: [],
      fields: {
        성명: name,
        생년월일: birth,
        가입구분: `${insuranceType}가입자`,
        가구원수: `${householdSize}인`,
        가구원: `본인 외 ${householdSize - 1}인`,
        발급일: issued,
      },
    },
    {
      slotKey: 'nhis_acquisition_loss',
      label: '건강보험 자격득실확인서',
      docType: '건강보험자격득실확인서',
      expectedDocType: '건강보험자격득실확인서',
      dateField: '발급일',
      status: 'PASS',
      receiptAmount: null,
      findings: [],
      fields: {
        성명: name,
        생년월일: birth,
        사업장명: employer,
        취득일: employedAt,
        상실일: '(재직 중)',
        '최근 5년 변동내역': `${between(random, 1, 3)}건 (포함)`,
        발급일: issued,
      },
    },
    {
      slotKey: 'work_proof',
      label: proof.label,
      docType: proof.docType,
      expectedDocType: proof.docType,
      dateField: proof.dateField,
      status: 'PASS',
      receiptAmount: null,
      findings: [],
      fields: proof.fields(proofCtx),
    },
  ]

  // --- 문제를 **어느 서류에** 얹을지 고른다.
  //
  // 소득 140% 초과는 서류가 멀쩡해도 자격이 안 되는 경우라, 건보료 확인서에
  // 붙는다. 나머지는 사유의 `doc_type`이 가리키는 서류에 붙인다 — 담당자가
  // 목록에서 빨간 칸을 눌러 들어갔는데 그 원본에 문제가 없으면 안 된다.
  const reasons: Reason[] = []
  let reasonSeverity: DocStatus = 'PASS'
  const dice = random()
  if (overIncome) {
    reasons.push(FAIL_REASONS[0])
    reasonSeverity = 'FAIL'
  } else if (dice < 0.09) {
    reasons.push(pick(random, REVIEW_REASONS))
    reasonSeverity = 'NEEDS_REVIEW'
  } else if (dice < 0.13) {
    reasons.push(pick(random, FAIL_REASONS.slice(1)))
    reasonSeverity = 'FAIL'
  }

  for (const reason of reasons) {
    const slot = DOC_TYPE_TO_SLOT[reason.doc_type ?? ''] ?? 'nhis_payment'
    const target = docs.find((d) => d.slotKey === slot)
    if (!target) continue
    target.findings.push({
      code: reason.code,
      message: reason.message,
      how_to_fix: '원본을 다시 발급받아 올리도록 안내하세요.',
      severity: reasonSeverity === 'PASS' ? 'NEEDS_REVIEW' : reasonSeverity,
    })
    // 2단계 사유(소득 초과·도외 주소)는 **서류의 흠이 아니라 자격의 문제**다.
    // 근거로 남기되 서류 판정은 건드리지 않는다 — 백엔드의 `missing_count`도
    // 1단계(`stage1_status`)만 세므로, 여기서 서류를 부적합으로 눕히면 목업의
    // 미비 개수가 실데이터보다 부풀어 오른다.
    if (reason.stage === 'stage1') target.status = reasonSeverity
  }

  // --- 안 낸 서류. 전건이 완비면 `미제출` 칸이 한 번도 안 보여서, 그 컬럼이
  //     무엇을 위한 것인지 시연에서 드러나지 않는다.
  if (random() < 0.12) {
    const dropped = between(random, 0, docs.length - 1)
    docs.splice(dropped, 1)
  }

  // --- 판정과 미비 개수는 **서류에서 역산한다**. 따로 굴리면 목록의 숫자와
  //     서류 칸이 따로 논다 (취업패키지 쪽이 이미 이 방식이다).
  // 최종 판정은 1단계 서류 판정과 2단계 자격 사유 중 **더 나쁜 쪽**이다.
  const verdicts: DocStatus[] = [...docs.map((d) => d.status), reasonSeverity]
  const aiStatus: DocStatus = verdicts.includes('FAIL')
    ? 'FAIL'
    : verdicts.includes('NEEDS_REVIEW')
      ? 'NEEDS_REVIEW'
      : 'PASS'
  const missing =
    SAVINGS_SLOT_ORDER.length -
    docs.length +
    docs.filter((d) => d.status !== 'PASS').length

  const { decision, officerRole, memo } = rollDecision(random, aiStatus)

  return {
    row: {
      application_id: id,
      application_no: `DS-2026-${String(seq).padStart(6, '0')}`,
      name,
      region,
      town,
      program_code: DOUBLE_SAVINGS,
      program_name: PROGRAM_NAMES[DOUBLE_SAVINGS],
      ai_status: aiStatus,
      ai_status_label: AI_STATUS_LABELS[aiStatus],
      total_score: scored.total,
      max_total: 100,
      missing_count: missing,
      submitted_at: submitted,
      status: decision ? 'decided' : 'submitted',
      decision,
      decision_label: decisionLabel(officerRole, decision),
      officer_role: officerRole,
      rank: null,
      // 목록의 서류 칸. 서류가 정해진 뒤라야 채울 수 있어 여기서 만든다.
      documents: savingsDocCells(id, docs),
    },
    scored,
    birth,
    address,
    transferIn,
    employedAt,
    householdSize,
    monthlyPremium,
    insuranceType,
    workCategory,
    reasons,
    docs,
    selections: [],
    // 두배적금은 보완 자체가 없다 (공고문: 미비 시 추가·보충서류를 요청하지 않음).
    supplementDeadline: null,
    // 시행지침 ①소득 적은 순 ②거주 긴 순 ③근로 긴 순 ④연령 낮은 순.
    tiebreak: [
      -scored.total,
      incomePercent,
      -residenceDays,
      -workDays,
      -new Date(birth).getTime() / 86_400_000,
    ],
    memo,
    decidedAt: decision ? submittedAt(random) : null,
  }
}

// ---------------------------------------------------------------- 취업패키지 불인정 사유
//
// 아래 목록은 **실제 심사에서 나온 반려 사유**를 옮긴 것이다. 가공한 예시가 아니라
// 담당자가 실제로 적어 낸 문장이라, 목업이 이것을 재현하지 못하면 화면을 아무리
// 채워 놔도 "실제로 무엇을 보는 화면인지"를 보여주지 못한다.
//
// 가장 많은 것이 **인정 기간**이다 — 결제일 251222 / 251231 / 251217 / 251226,
// 초본이 25년도. 사업계획서의 "※ 2026. 1. 1. 이후의 서류만 인정" 한 줄이 실무에서
// 이렇게 걸린다. 그 다음이 **서류 자체가 근거가 못 되는 경우**다 — 등본 제출,
// 접수확인서로 영수증 대체, 성적표에 응시자 이름 없음, 계좌이체 영수증의 예금주
// 불명. 마지막이 **지원 취지와 안 맞는 것**이다 — 정장을 구입한 것으로 보임,
// 아르바이트 면접, 신청기간 이후 응시.

/** 판독 결과에 얹는 문제 하나. `patch`는 판독 필드를 문제 있는 값으로 바꾼다. */
interface Issue {
  code: string
  severity: DocStatus
  /** 서류 탭에 붙는 문장. */
  message: string
  howToFix: string
  /** 목록·최종판정 패널에 올라가는 사유. 비우면 `message`를 쓴다. */
  reason?: string
  patch?: Record<string, string>
  /** 지급액 계산에서 이 회차를 미확정으로 돌린다. */
  voidsAmount?: boolean
  /** 판독된 결제금액을 이 값으로 바꾼다. 지급 계산도 이 값을 쓴다. */
  amount?: number
}

/** 도외 주소 — 초본을 떼 보니 전북이 아닌 경우. */
const OUT_OF_REGION_ADDRESSES: [string, string][] = [
  ['대전광역시 서구 둔산동 1234', '대전광역시 서구청장'],
  ['충청남도 천안시 서북구 불당동 45', '천안시 서북구청장'],
  ['서울특별시 관악구 신림동 77', '서울특별시 관악구청장'],
  ['경기도 수원시 팔달구 인계동 210', '수원시 팔달구청장'],
]

/** 아르바이트로 보이는 면접처. 지원 대상인지 담당자가 판단해야 한다. */
const PART_TIME_EMPLOYERS = ['전주 OO편의점', '익산 OO카페', '군산 OO물류센터 단기']

/** 2025년 결제일 — 실제 반려 사례에 나온 날짜를 그대로 쓴다. */
const STALE_PAYMENT_DATES = ['2025-12-22', '2025-12-31', '2025-12-17', '2025-12-26']

// ---------------------------------------------------------------- 취업지원패키지 한 건

/** `YYYY-MM-DD`에서 `days`일 뒤. */
const daysAfterDate = (isoDate: string, days: number) =>
  dateFromDayNumber(dayNumber(isoDate) + days)

/** 인정 기간(2026-01-01)을 벗어난 날짜에 대한 사유 문장. */
const beforeCutoff = (docType: string, dateField: string, value: string): Reason => ({
  stage: 'stage1',
  code: 'ISSUED_BEFORE_CUTOFF',
  message: `${dateField} ${value} — 2026. 1. 1. 이후의 서류만 인정됩니다.`,
  doc_type: docType,
})

/**
 * 지원 항목을 고른다 (사업계획서 "복수선택가능").
 *
 * 성과목표 건수(면접비 330 · 정장 20 · 사진 150 · 자격증 400)를 가중치로 쓴다.
 * 정장비는 목표가 20건뿐이라 목록에서도 드물게 보여야 맞다.
 */
function pickSelections(random: () => number): JobSelection[] {
  const weights = ITEM_ORDER.map((k) => JOB_ITEMS[k].target)
  const total = weights.reduce((a, b) => a + b, 0)
  const drawItem = (): ItemKey => {
    let x = random() * total
    for (let i = 0; i < ITEM_ORDER.length; i += 1) {
      x -= weights[i]
      if (x <= 0) return ITEM_ORDER[i]
    }
    return ITEM_ORDER[0]
  }

  const keys = new Set<ItemKey>([drawItem()])
  if (random() < 0.24) keys.add(drawItem())
  if (random() < 0.05) keys.add(drawItem())

  return ITEM_ORDER.filter((k) => keys.has(k)).map((key) => {
    const item = JOB_ITEMS[key]
    const count = item.maxCount === 1 ? 1 : random() < 0.28 ? 2 : 1
    const receipts: (number | null)[] = []
    for (let i = 0; i < count; i += 1) {
      if (!item.actualCost) {
        receipts.push(null)
        continue
      }
      if (key === 'suit') receipts.push(pick(random, SUIT_SHOPS)[1])
      else if (key === 'photo') receipts.push(pick(random, PHOTO_STUDIOS)[1])
      else receipts.push(pick(random, CERTIFICATES)[1])
    }
    return { key, count, receipts, receiptFlagged: receipts.map(() => false) }
  })
}

/** 신청서(온라인 작성본)의 문제. 서류를 떼기 전에 신청서부터 틀리는 경우다. */
function formIssue(random: () => number, name: string): Issue | null {
  const dice = random()
  if (dice < 0.03) {
    return {
      code: 'ITEM_NOT_SELECTED',
      severity: 'FAIL',
      message: '신청분야(지원 항목) 체크가 비어 있습니다.',
      howToFix: '어떤 항목을 신청하는지 체크한 신청서를 다시 받아야 합니다.',
      reason: '신청서의 신청분야 체크가 누락되었습니다.',
      patch: { 신청분야: '(미체크)' },
    }
  }
  if (dice < 0.055) {
    return {
      code: 'CONSENT_UNCHECKED',
      severity: 'FAIL',
      message: '개인정보 수집·이용·제공 동의서 체크가 누락되었습니다.',
      howToFix: '동의 항목을 체크한 신청서를 다시 받아야 합니다.',
      reason: '개인정보 동의서 체크가 누락되었습니다.',
      patch: { '개인정보 동의': '(미체크)' },
    }
  }
  if (dice < 0.075) {
    const other = `${name[0]}*${pick(random, GIVEN_NAMES).slice(-1)}`
    return {
      code: 'ACCOUNT_HOLDER_MISMATCH',
      severity: 'FAIL',
      message: `통장 사본의 예금주가 신청자와 다릅니다. (예금주 ${other})`,
      howToFix: '지원금은 본인 명의 계좌로만 지급됩니다. 본인 명의 통장으로 다시 받아야 합니다.',
      reason: `입금 계좌 예금주(${other})가 신청자 본인이 아닙니다.`,
      patch: { 예금주: other },
    }
  }
  return null
}

/** 주민등록초본의 문제. 실제 반려 사유에서 가장 자주 나온 자리다. */
function abstractIssue(
  random: () => number,
  issuedAt: string,
  region: string,
): Issue | null {
  const dice = random()
  if (dice < 0.025) {
    return {
      code: 'DOC_NOT_SUBMITTED',
      severity: 'FAIL',
      message: '주민등록초본이 제출되지 않았습니다.',
      howToFix: '공통서류입니다. 초본을 제출해야 접수가 인정됩니다.',
      reason: '공통서류인 주민등록초본이 제출되지 않았습니다.',
      patch: { 발급일: '(미제출)', 주소: '(미제출)', 발급기관: '(미제출)' },
    }
  }
  if (dice < 0.05) {
    return {
      code: 'WRONG_DOC_TYPE',
      severity: 'FAIL',
      message: '주민등록등본이 제출되었습니다. 이 자리는 초본이어야 합니다.',
      howToFix: '등본에는 주소 이력이 없습니다. 주민등록초본을 다시 발급받아야 합니다.',
      reason: '주민등록등본이 제출되었습니다. (초본 필요)',
    }
  }
  if (dice < 0.075) {
    const stale = `2025-${String(between(random, 9, 12)).padStart(2, '0')}-${String(
      between(random, 1, 28),
    ).padStart(2, '0')}`
    return {
      code: 'ISSUED_BEFORE_CUTOFF',
      severity: 'FAIL',
      message: `발급일 ${stale} — 2026. 1. 1. 이후의 서류만 인정됩니다.`,
      howToFix: '초본을 다시 발급받아 올리도록 안내하세요.',
      reason: `주민등록초본 발급일 ${stale} — 25년도 서류라 인정되지 않습니다.`,
      patch: { 발급일: stale },
    }
  }
  if (dice < 0.095) {
    const [outside, issuer] = pick(random, OUT_OF_REGION_ADDRESSES)
    return {
      code: 'OUT_OF_REGION',
      severity: 'FAIL',
      message: `주민등록 주소지가 도외입니다. (${outside})`,
      howToFix: '전북특별자치도 내 거주 청년만 신청할 수 있습니다.',
      reason: `주민등록 주소지가 전북특별자치도 밖입니다. (${outside})`,
      patch: { 주소: outside, 발급기관: issuer },
    }
  }
  if (dice < 0.115) {
    return {
      code: 'RRN_UNREADABLE',
      severity: 'NEEDS_REVIEW',
      message: '주민등록번호 표기가 규정과 달라 확인이 필요합니다.',
      howToFix: '생년월일까지만 보이도록 재발급받거나, 담당자가 신분 확인 후 처리하세요.',
      reason: '초본의 주민등록번호 표기 수정이 필요합니다.',
      patch: { 주민등록번호: '******-*******' },
    }
  }
  void issuedAt
  void region
  return null
}

/** 면접확인서의 문제. */
function confirmationIssue(random: () => number, interviewDate: string): Issue | null {
  if (random() < 0.04) {
    const where = pick(random, PART_TIME_EMPLOYERS)
    return {
      code: 'PART_TIME_INTERVIEW',
      severity: 'NEEDS_REVIEW',
      message: `아르바이트 면접으로 보입니다. (${where}) 지원 대상인지 확인이 필요합니다.`,
      howToFix: '사업계획서는 "도내 기업·기관 등 면접"만 정하고 있습니다. 담당자 판단이 필요합니다.',
      reason: `아르바이트 면접(${where})으로 보입니다. 지원 대상 여부 확인이 필요합니다.`,
      patch: { 면접기업: where },
    }
  }
  void interviewDate
  return null
}

/** 응시확인서·성적표의 문제. */
function examIssue(
  random: () => number,
  examDate: string,
  applyPeriodEnd: string,
): Issue | null {
  const dice = random()
  if (dice < 0.06) {
    return {
      code: 'EXAM_DATE_MISSING',
      severity: 'FAIL',
      message: '응시확인서·성적표에 응시일이 표기되어 있지 않습니다.',
      howToFix: '사업계획서상 응시일 표기가 필수입니다. 응시일이 찍힌 서류를 다시 받아야 합니다.',
      reason: '응시확인서에 응시일이 표기되어 있지 않습니다. (응시일 표기 필수)',
      patch: { 응시일: '(표기 없음)' },
    }
  }
  if (dice < 0.1) {
    return {
      code: 'EXAMINEE_UNIDENTIFIABLE',
      severity: 'NEEDS_REVIEW',
      message: '성적표에 응시자 성명이 없어 본인이 응시한 건인지 확인할 수 없습니다.',
      howToFix: '성명이 표기된 응시확인서를 추가로 받아야 합니다.',
      reason: '성적표에 응시자 성명이 없어 본인 응시 여부를 확인할 수 없습니다.',
      patch: { 성명: '(표기 없음)', 비고: '등급만 표기된 성적표' },
    }
  }
  if (examDate > applyPeriodEnd) {
    return {
      code: 'EXAM_AFTER_APPLY_PERIOD',
      severity: 'NEEDS_REVIEW',
      message: `신청기간(~${applyPeriodEnd}) 이후에 응시한 건입니다. (응시일 ${examDate})`,
      howToFix: '신청 시점에 아직 발생하지 않은 비용입니다. 차수 이월 여부를 판단해야 합니다.',
      reason: `신청기간 이후 응시(${examDate})입니다. 지원 대상인지 확인이 필요합니다.`,
    }
  }
  return null
}

/** 결제영수증의 문제. 실제 반려 사유가 가장 다양하게 나온 자리다. */
function receiptIssue(
  random: () => number,
  key: ItemKey,
  eventDate: string,
  paidAt: string,
  receipt: number | null,
  listPrice: number,
): Issue | null {
  const dice = random()

  if (dice < 0.055) {
    const stale = pick(random, STALE_PAYMENT_DATES)
    return {
      code: 'ISSUED_BEFORE_CUTOFF',
      severity: 'FAIL',
      message: `결제일 ${stale} — 2026. 1. 1. 이후의 서류만 인정됩니다.`,
      howToFix: '인정 기간 안에 결제한 건만 지원됩니다.',
      reason: `결제일 ${stale} — 25년도 결제라 인정되지 않습니다.`,
      patch: { 결제일: stale },
      voidsAmount: true,
    }
  }

  if (key === 'certificate' && dice < 0.08) {
    return {
      code: 'NOT_A_RECEIPT',
      severity: 'FAIL',
      message: '접수확인서가 제출되었습니다. 결제일이 표기된 결제영수증이 필요합니다.',
      howToFix: '접수확인서는 결제영수증을 대신할 수 없습니다. 결제내역서를 받아야 합니다.',
      reason: '접수확인서는 결제영수증을 대신할 수 없습니다. (결제일 명시 필요)',
      patch: { 서류종류: '접수확인서', 결제일: '(표기 없음)', 결제금액: '(표기 없음)' },
      voidsAmount: true,
    }
  }

  if (dice < 0.11) {
    const payee = `${pick(random, SURNAMES)}*${pick(random, GIVEN_NAMES).slice(-1)}`
    return {
      code: 'TRANSFER_PAYEE_UNVERIFIED',
      severity: 'NEEDS_REVIEW',
      message: `계좌이체 영수증입니다. 입금 계좌 예금주(${payee})가 해당 업체 대표인지 증명이 필요합니다.`,
      howToFix: '사업자등록증이나 업체 명의 확인서를 추가로 받아야 합니다.',
      reason: `계좌이체 입금 예금주(${payee})가 업체 대표인지 증명이 필요합니다.`,
      patch: { 결제수단: '계좌이체', 입금계좌예금주: payee },
    }
  }

  // 영수증 금액이 실제 응시료·대여료와 다른 경우. 정가를 아는 항목에서만 잡는다.
  if (dice < 0.14 && receipt !== null && listPrice > 0) {
    const inflated = listPrice * 2
    return {
      code: 'AMOUNT_MISMATCH',
      severity: 'NEEDS_REVIEW',
      message: `영수증 금액(${inflated.toLocaleString('ko-KR')}원)이 정가(${listPrice.toLocaleString(
        'ko-KR',
      )}원)와 다릅니다. 2인 결제 여부 확인이 필요합니다.`,
      howToFix: '결제 내역을 확인해 본인 응시분만 정산해야 합니다.',
      reason: `영수증 금액이 정가의 2배입니다. (${inflated.toLocaleString('ko-KR')}원 / 정가 ${listPrice.toLocaleString('ko-KR')}원)`,
      patch: { 결제금액: `${inflated.toLocaleString('ko-KR')}원` },
      amount: inflated,
    }
  }

  // 결제일이 사건일보다 뒤. 시험을 치고 나서 결제된 것으로 읽히면 확인이 필요하다.
  if (dice < 0.17 && paidAt > eventDate) {
    const label = key === 'certificate' ? '응시일' : '면접일'
    return {
      code: 'PAID_AFTER_EVENT',
      severity: 'NEEDS_REVIEW',
      message: `결제일(${paidAt})이 ${label}(${eventDate})보다 뒤입니다.`,
      howToFix: '같은 건의 결제가 맞는지 결제 내역으로 확인해야 합니다.',
      reason: `결제일(${paidAt})이 ${label}(${eventDate})보다 늦습니다. 확인이 필요합니다.`,
    }
  }

  // 정장은 '대여'만 지원한다. 결제일과 면접일이 멀면 구입으로 읽힌다.
  if (key === 'suit' && dice < 0.45) {
    const paidEarly = daysBefore(eventDate, between(random, 40, 70))
    return {
      code: 'RENTAL_VS_PURCHASE',
      severity: 'NEEDS_REVIEW',
      message: `결제일 ${paidEarly} · 면접일 ${eventDate} — 기본 대여 기간(3박 4일)과 간격이 큽니다. 대여가 아니라 구입일 수 있습니다.`,
      howToFix: '대여 계약서나 반납 확인을 추가로 받아야 합니다.',
      reason: `정장 결제일(${paidEarly})과 면접일(${eventDate}) 간격이 커 대여가 아닌 구입으로 보입니다.`,
      patch: { 결제일: paidEarly, 품목: '남성정장 1벌' },
    }
  }

  if (dice < 0.20) {
    return {
      code: 'RECEIPT_AMOUNT_UNREADABLE',
      severity: 'NEEDS_REVIEW',
      message: '결제금액을 판독하지 못했습니다. 담당자 확인이 필요합니다.',
      howToFix: '금액이 선명한 영수증을 다시 올리도록 안내하세요.',
      reason: '결제영수증의 금액을 판독하지 못했습니다.',
      patch: { 결제금액: '(판독 실패)' },
      voidsAmount: true,
    }
  }

  return null
}

/** `issue`를 서류에 얹는다. 판정·판독값·사유가 한 번에 바뀐다. */
function applyIssue(doc: MockDoc, issue: Issue | null, reasons: Reason[]): void {
  if (!issue) return
  Object.assign(doc.fields, issue.patch ?? {})
  doc.status = issue.severity
  doc.findings.push({
    code: issue.code,
    message: issue.message,
    how_to_fix: issue.howToFix,
    severity: issue.severity,
  })
  reasons.push({
    stage: 'stage1',
    code: issue.code,
    message: issue.reason ?? issue.message,
    doc_type: doc.docType,
  })
  if (issue.voidsAmount) doc.receiptAmount = null
  else if (issue.amount !== undefined) doc.receiptAmount = issue.amount
}

/**
 * 항목 1회차의 서류를 만든다.
 *
 * 이 사업 심사의 전부가 여기 있다 — 항목마다 필요한 서류가 왔는가, 그 서류의
 * 기준 날짜(면접일·응시일·결제일)가 2026. 1. 1. 이후인가, 그 서류가 지원 취지에
 * 맞는 근거인가.
 */
function makeItemDocs(
  random: () => number,
  key: ItemKey,
  index: number,
  receipt: number | null,
  name: string,
  submittedDate: string,
  applyPeriodEnd: string,
): { docs: MockDoc[]; reasons: Reason[] } {
  const item = JOB_ITEMS[key]
  const docs: MockDoc[] = []
  const reasons: Reason[] = []

  // 항목 1회차의 '사건'이 일어난 날 (면접을 본 날 / 시험을 친 날 / 사진을 찍은 날).
  // 접수일에서 몇 주 앞이 기본이다.
  //
  // 4%는 **신청기간이 끝난 뒤**로 보낸다. "상반기 모집기간이 4월 한 달인데 시험을
  // 5/16에 봤다" — 실제 심사에서 나온 사례다. 신청 시점에 아직 발생하지 않은
  // 비용이라 담당자 판단이 필요하다.
  const eventDate =
    random() < 0.04
      ? daysAfterDate(applyPeriodEnd, between(random, 3, 40))
      : daysBefore(submittedDate, between(random, 5, 95))
  const paidAt = daysAfterDate(eventDate, random() < 0.25 ? between(random, 1, 30) : 0)

  const employer = pick(random, JOB_EMPLOYERS)
  const cert: [string, number, string] =
    key === 'certificate' ? pick(random, CERTIFICATES) : ['', 0, '']
  // 영수증의 '가맹점'은 돈을 받은 곳이다 — 자격증이면 시험 시행기관이지 자격증명이 아니다.
  const shop =
    key === 'suit'
      ? pick(random, SUIT_SHOPS)[0]
      : key === 'photo'
        ? pick(random, PHOTO_STUDIOS)[0]
        : cert[2]

  for (const spec of item.docs) {
    const isReceipt = spec.suffix === 'receipt'
    const fields: Record<string, string> = { 성명: name }
    let issue: Issue | null = null

    if (spec.suffix === 'exam') {
      fields['자격증명'] = cert[0]
      fields['응시일'] = eventDate
      fields['발급기관'] = cert[2]
      issue = examIssue(random, eventDate, applyPeriodEnd)
    } else if (spec.suffix === 'confirmation') {
      fields['면접기업'] = employer
      fields['면접일'] = eventDate
      fields['발급일'] = daysAfterDate(eventDate, between(random, 0, 5))
      issue = confirmationIssue(random, eventDate)
    } else if (spec.suffix === 'photo') {
      fields['촬영업체'] = shop
      fields['촬영일'] = eventDate
      fields['규격'] = '3.5 × 4.5 cm (증명사진)'
    } else {
      fields['가맹점'] = shop
      if (key === 'certificate') fields['품목'] = cert[0]
      fields['결제일'] = paidAt
      fields['결제금액'] = receipt === null ? '(판독 실패)' : `${receipt.toLocaleString('ko-KR')}원`
      fields['결제수단'] = pick(random, ['신용카드', '체크카드', '계좌이체'])
      issue = receiptIssue(random, key, eventDate, paidAt, receipt, cert[1])
    }

    const doc: MockDoc = {
      slotKey: `${key}_${index}_${spec.suffix}`,
      label: `${spec.label} — ${item.label}` + (item.maxCount > 1 ? ` ${index}회차` : ''),
      docType: spec.accepted ? pick(random, spec.accepted) : spec.docType,
      expectedDocType: spec.accepted ? spec.accepted.join(' 또는 ') : spec.docType,
      dateField: spec.dateField,
      status: 'PASS',
      findings: [],
      receiptAmount: isReceipt ? receipt : null,
      fields,
    }

    applyIssue(doc, issue, reasons)

    // 문제를 얹은 뒤에 인정 기간을 다시 잰다. issue가 날짜를 바꿔 놓았을 수 있다.
    const dateShown = doc.fields[spec.dateField] ?? ''
    const unreadable = dateShown.startsWith('(')
    if (doc.status === 'PASS' && !unreadable && dateShown < JOB_DOC_CUTOFF) {
      doc.status = 'FAIL'
      doc.receiptAmount = null
      doc.findings.push({
        code: 'ISSUED_BEFORE_CUTOFF',
        message: `${spec.dateField} ${dateShown} — 2026. 1. 1. 이후의 서류만 인정됩니다.`,
        how_to_fix: '인정 기간 안의 서류로 다시 제출하도록 안내하세요.',
        severity: 'FAIL',
      })
      reasons.push(beforeCutoff(doc.docType, spec.dateField, dateShown))
    }

    docs.push(doc)
  }

  return { docs, reasons }
}

function makeJobEntry(
  random: () => number,
  id: number,
  seq: number,
  region: string,
): MockEntry {
  const { town, name, address } = makePerson(random, region)

  // 자격요건은 나이와 거주지뿐이다 (사업계획서 「2. 서류심사」). 소득·근로 요건이 없다.
  // 대상 연령은 2026년 기준 18~39세 = 1987. 1. 1. ~ 2008. 12. 31. 출생.
  const birth = dateYearsBefore(random, Math.round(bell(random, 19, 39, 3)))
  const submitted = jobSubmittedAt(random)
  const submittedDate = submitted.slice(0, 10)
  const round =
    submittedDate <= JOB_APPLY_ROUNDS[0].to ? JOB_APPLY_ROUNDS[0] : JOB_APPLY_ROUNDS[1]

  const selections = pickSelections(random)
  const docs: MockDoc[] = []
  const reasons: Reason[] = []

  // --- 공통서류 ① 신청서. 온라인 작성본이라 업로드가 없지만, 담당자가 확인하는
  //     대상이라는 점은 종이와 같다. 신청분야·동의·계좌를 여기서 본다.
  const formDoc: MockDoc = {
    slotKey: 'application_form',
    label: '청년 취업지원패키지 신청서 (작성본)',
    docType: '신청서',
    expectedDocType: '신청서',
    dateField: '작성일',
    status: 'PASS',
    receiptAmount: null,
    findings: [],
    fields: {
      성명: name,
      생년월일: birth,
      연락처: `010-${between(random, 2000, 9999)}-${between(random, 1000, 9999)}`,
      주소: address,
      신청분야: selections.map((s) => JOB_ITEMS[s.key].label).join(', '),
      '개인정보 동의': '동의함 (수집·이용 / 제3자 제공)',
      예금주: name,
      계좌번호: `${pick(random, ['농협', '전북은행', '국민', '카카오뱅크'])} ${between(random, 100, 999)}-${between(random, 1000, 9999)}-${between(random, 1000, 9999)}`,
      작성일: submittedDate,
    },
  }
  applyIssue(formDoc, formIssue(random, name), reasons)
  docs.push(formDoc)

  // --- 공통서류 ② 주민등록초본. ③ 통장 사본은 신청서의 계좌 칸에서 첨부한다.
  const abstractIssued = daysBefore(submittedDate, between(random, 1, 40))
  const abstractDoc: MockDoc = {
    slotKey: 'resident_abstract',
    label: '주민등록초본',
    docType: '주민등록초본',
    expectedDocType: '주민등록초본',
    dateField: '발급일',
    status: 'PASS',
    receiptAmount: null,
    findings: [],
    fields: {
      성명: name,
      생년월일: birth,
      주소: address,
      발급일: abstractIssued,
      발급기관: `${region}장`,
    },
  }
  applyIssue(abstractDoc, abstractIssue(random, abstractIssued, region), reasons)
  if (abstractDoc.status === 'PASS' && abstractIssued < JOB_DOC_CUTOFF) {
    abstractDoc.status = 'FAIL'
    abstractDoc.findings.push({
      code: 'ISSUED_BEFORE_CUTOFF',
      message: `발급일 ${abstractIssued} — 2026. 1. 1. 이후의 서류만 인정됩니다.`,
      how_to_fix: '초본을 다시 발급받아 올리도록 안내하세요.',
      severity: 'FAIL',
    })
    reasons.push(beforeCutoff('주민등록초본', '발급일', abstractIssued))
  }
  docs.push(abstractDoc)

  // --- 항목별 추가서류.
  for (const selection of selections) {
    for (let index = 1; index <= selection.count; index += 1) {
      const made = makeItemDocs(
        random,
        selection.key,
        index,
        selection.receipts[index - 1] ?? null,
        name,
        submittedDate,
        round.to,
      )
      docs.push(...made.docs)
      reasons.push(...made.reasons)
      // 판독 실패·인정 불가한 영수증은 지급액 계산에서도 미확정으로 다뤄야 한다.
      // 금액은 읽혔지만 확인이 필요한 회차(정가 불일치·예금주 불명)는 금액을 살려
      // 두되 표시만 남긴다 — 담당자가 얼마인지는 봐야 판단할 수 있다.
      const receiptDoc = made.docs.find((d) => d.slotKey.endsWith('_receipt'))
      if (receiptDoc) {
        selection.receipts[index - 1] = receiptDoc.receiptAmount
        selection.receiptFlagged[index - 1] = receiptDoc.status === 'NEEDS_REVIEW'
      }
    }
  }

  // --- 최종 판정은 서류 판정의 합이다. 하나라도 부적합이면 부적합.
  const aiStatus: DocStatus = docs.some((d) => d.status === 'FAIL')
    ? 'FAIL'
    : docs.some((d) => d.status === 'NEEDS_REVIEW')
      ? 'NEEDS_REVIEW'
      : 'PASS'
  const missing = docs.filter((d) => d.status !== 'PASS').length

  const { decision, officerRole, memo } = rollDecision(random, aiStatus)

  return {
    row: {
      application_id: id,
      application_no: `JP-2026-${String(seq).padStart(6, '0')}`,
      name,
      region,
      town,
      program_code: JOB_PACKAGE,
      program_name: PROGRAM_NAMES[JOB_PACKAGE],
      ai_status: aiStatus,
      ai_status_label: AI_STATUS_LABELS[aiStatus],
      // 선착순 사업이라 심사표가 없다. 점수 컬럼은 비운다.
      total_score: null,
      max_total: null,
      missing_count: missing,
      submitted_at: submitted,
      status: decision ? 'decided' : 'submitted',
      decision,
      decision_label: decisionLabel(officerRole, decision),
      officer_role: officerRole,
      rank: null,
      items_label: selections
        .map(
          (s) =>
            `${JOB_ITEMS[s.key].label}${JOB_ITEMS[s.key].maxCount > 1 ? ` ${s.count}회` : ''}`,
        )
        .join(' · '),
    },
    scored: null,
    birth,
    address,
    transferIn: '',
    employedAt: '',
    householdSize: 0,
    monthlyPremium: 0,
    insuranceType: '',
    // 취업패키지는 체크리스트가 근로유형이 아니라 **고른 지원 항목**으로 갈린다.
    workCategory: null,
    reasons,
    docs,
    selections,
    // 「7일 내 서류 보완안내 · 미보완시 지원대상자 제외 및 후순위자 선정」.
    supplementDeadline: aiStatus === 'PASS' ? null : daysAfter(submitted, JOB_SUPPLEMENT_DAYS),
    // 점수순 정렬에서는 맨 뒤로 보내되, 그 안에서는 접수 순서를 지킨다.
    tiebreak: [999, Date.parse(`${submitted}Z`) / 86_400_000],
    memo,
    decidedAt: decision ? daysAfter(submitted, between(random, 1, 5)) : null,
  }
}

// ---------------------------------------------------------------- 데이터셋

/**
 * 시군별 접수 건수 배수.
 *
 * 정원 대비 진행률 배지와 커트라인이 뜻을 가지려면 접수가 정원 언저리까지 차 있어야
 * 한다. 도시는 정원을 넘기고 군 지역은 못 채우는 실제 양상을 흉내 낸다.
 */
const APPLY_RATIO: Record<string, number> = {
  전주시: 1.35,
  군산시: 1.15,
  익산시: 1.22,
  정읍시: 0.95,
  남원시: 0.86,
  김제시: 0.9,
  완주군: 1.05,
  진안군: 0.6,
  무주군: 0.53,
  장수군: 0.6,
  임실군: 0.73,
  순창군: 0.66,
  고창군: 0.83,
  부안군: 0.9,
}

function buildDataset(): MockEntry[] {
  const random = rng(20260303)
  const entries: MockEntry[] = []
  let seq = 1

  // 두배적금 — 시군별 정원 × 배수.
  for (const region of REGIONS) {
    const count = Math.round(QUOTA[region] * APPLY_RATIO[region])
    for (let i = 0; i < count; i += 1) {
      entries.push(makeSavingsEntry(random, MOCK_ID_BASE + entries.length, seq++, region))
    }
  }

  // 취업지원패키지 — 선착순. 신청 1건이 항목을 복수로 고르므로 **건수와 항목
  // 건수가 다르다**. 지원규모 900건은 성과목표 4종의 합(330+20+150+400)이라
  // 항목 건수로 읽는 것이 맞고, 여기서는 항목 건수가 900의 70% 근처가 되도록
  // 신청 건수를 잡는다.
  const jobCount = 430
  for (let i = 0; i < jobCount; i += 1) {
    // 인구 비례로 시군을 고른다. 정원 큰 시군이 더 자주 뽑히게 가중치를 준다.
    const region = weightedRegion(random)
    entries.push(makeJobEntry(random, MOCK_ID_BASE + entries.length, seq++, region))
  }

  return entries
}

function weightedRegion(random: () => number): string {
  const total = REGIONS.reduce((sum, r) => sum + QUOTA[r], 0)
  let x = random() * total
  for (const region of REGIONS) {
    x -= QUOTA[region]
    if (x <= 0) return region
  }
  return REGIONS[0]
}

/** 모듈 로드 시 한 번만 만든다. 담당자 판단은 이 배열을 직접 고친다. */
const ENTRIES: MockEntry[] = buildDataset()

const byId = new Map(ENTRIES.map((e) => [e.row.application_id, e]))

/**
 * 시군 내 고득점순 순위.
 *
 * 필터를 걸었다고 1등이 바뀌면 커트라인과 어긋난다. 그래서 순위는 언제나 **필터
 * 이전 전체**를 기준으로 매긴다 (`api/officer._rank_by_region`과 같은 규칙).
 */
function rankByRegion(): Map<number, number> {
  const ranks = new Map<number, number>()
  for (const region of REGIONS) {
    const ranked = ENTRIES.filter((e) => e.row.region === region && e.scored !== null).sort(
      (a, b) => compareTiebreak(a.tiebreak, b.tiebreak),
    )
    ranked.forEach((e, i) => ranks.set(e.row.application_id, i + 1))
  }
  return ranks
}

function compareTiebreak(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0)
    if (diff !== 0) return diff
  }
  return 0
}

const RANKS = rankByRegion()

/**
 * 취업패키지의 **선착순 접수 순번**.
 *
 * 이 사업에는 점수가 없다. 순위 칸에 넣을 값은 "몇 번째로 들어왔는가" 하나뿐이고,
 * 담당자가 예산 소진 시점을 가늠하는 근거도 그것이다. 백엔드(`api/officer.py`)는
 * 아직 점수제 순위만 매겨 이 칸을 비워 보내는데, 선착순 사업에서는 접수 순번을
 * 넣는 편이 맞다고 보고 목업이 먼저 그렇게 한다.
 */
function firstComeRanks(): Map<number, number> {
  const ranks = new Map<number, number>()
  ENTRIES.filter((e) => e.row.program_code === JOB_PACKAGE)
    .sort((a, b) => (a.row.submitted_at ?? '').localeCompare(b.row.submitted_at ?? ''))
    .forEach((e, i) => ranks.set(e.row.application_id, i + 1))
  return ranks
}

const JOB_RANKS = firstComeRanks()

const rankOf = (entry: MockEntry): number | null =>
  entry.row.program_code === JOB_PACKAGE
    ? (JOB_RANKS.get(entry.row.application_id) ?? null)
    : (RANKS.get(entry.row.application_id) ?? null)

// ---------------------------------------------------------------- 정원 배지

function cutoff(ranked: MockEntry[], limit: number): number | null {
  if (limit <= 0 || ranked.length < limit) return null
  return ranked[limit - 1].row.total_score
}

function quotaRows(role: OfficerRole, regions: string[]): QuotaRow[] {
  return regions
    .filter((region) => QUOTA[region] !== undefined)
    .map((region) => {
      const limit = QUOTA[region]
      const mine = ENTRIES.filter((e) => e.row.region === region)
      const ranked = mine
        .filter((e) => e.scored !== null)
        .sort((a, b) => compareTiebreak(a.tiebreak, b.tiebreak))
      const limit120 = Math.ceil(limit * 1.2)
      return {
        region,
        quota: limit,
        applied: mine.length,
        selected: mine.filter((e) => e.row.decision === 'approve').length,
        limit_120: limit120,
        cutoff_120: cutoff(ranked, limit120),
        cutoff_100: cutoff(ranked, limit),
        role_cutoff: cutoff(ranked, Math.ceil(limit * (role.quota_ratio ?? 1.2))),
        rate_percent: Math.round((mine.length / limit) * 1000) / 10,
      }
    })
}

/**
 * 선착순 접수 진행률.
 *
 * 지원규모 900건은 성과목표 4종의 합(면접비 330 + 정장 20 + 사진 150 + 자격증
 * 400)이라 **항목 건수**로 읽는 것이 맞다. 신청 1건이 항목을 복수로 고르므로
 * 신청 건수와 항목 건수가 다르고, 예산 소진을 가늠하는 값은 항목 건수다.
 */
function firstComeSummary(programCode: string | undefined): OfficerList['first_come'] {
  if (programCode !== JOB_PACKAGE) return null
  const mine = ENTRIES.filter((e) => e.row.program_code === JOB_PACKAGE)
  const rounds = (list: MockEntry[]) =>
    list.reduce((sum, e) => sum + e.selections.reduce((n, s) => n + s.count, 0), 0)
  const applied = rounds(mine)
  return {
    program_code: JOB_PACKAGE,
    program_name: PROGRAM_NAMES[JOB_PACKAGE],
    quota: JOB_PACKAGE_QUOTA,
    applied,
    selected: rounds(mine.filter((e) => e.row.decision === 'approve')),
    remaining: Math.max(0, JOB_PACKAGE_QUOTA - applied),
    rate_percent: Math.round((applied / JOB_PACKAGE_QUOTA) * 1000) / 10,
    supplement_days: JOB_SUPPLEMENT_DAYS,
    notice: `신청 ${mine.length.toLocaleString('ko-KR')}건 · 지원 항목 ${applied.toLocaleString(
      'ko-KR',
    )}건. 선착순 접수이며 예산 소진 시 조기 마감됩니다.`,
  }
}

// ---------------------------------------------------------------- 목록

/** 접수 목록. 필터·정렬·페이지는 백엔드와 같은 순서로 적용한다. */
export function mockOfficerList(query: OfficerListQuery): OfficerList {
  const role = roleOf(query.role)

  // --- 역할 범위. 관할을 고르지 않았으면 접수가 있는 첫 관할을 자동으로 집는다.
  let scoped = ENTRIES
  let pickedRegion = ''
  let pickedTown = ''
  if (role.requires_region) {
    const available = REGIONS.filter((r) => ENTRIES.some((e) => e.row.region === r))
    pickedRegion = query.region || available[0] || REGIONS[0]
    scoped = scoped.filter((e) => e.row.region === pickedRegion)
  }
  if (role.requires_town) {
    const towns = [...new Set(scoped.map((e) => e.row.town))].sort()
    pickedTown = query.town || towns[0] || ''
    scoped = scoped.filter((e) => e.row.town === pickedTown)
  }

  // --- 정원 배지는 필터와 무관하게 역할의 관할 전체를 기준으로 낸다.
  //
  // 다만 시군별 정원은 **두배적금에만** 있는 개념이다(시행지침 배정 인원). 선착순
  // 사업을 고른 상태에서 두배적금 정원 배지를 띄우면 담당자가 지금 보는 목록의
  // 진행률로 읽는다. 그 자리는 선착순 접수 진행률 배지가 대신한다.
  const quota =
    query.program === JOB_PACKAGE
      ? []
      : quotaRows(role, role.requires_region ? [pickedRegion] : REGIONS)

  let rows = scoped
  if (query.program) rows = rows.filter((e) => e.row.program_code === query.program)
  if (query.ai_status) rows = rows.filter((e) => e.row.ai_status === query.ai_status)
  if (query.status === PENDING) rows = rows.filter((e) => !e.row.decision)
  else if (query.status) rows = rows.filter((e) => e.row.decision === query.status)
  if (query.submitted_from)
    rows = rows.filter((e) => (e.row.submitted_at ?? '') >= query.submitted_from!)
  if (query.submitted_to)
    rows = rows.filter((e) => (e.row.submitted_at ?? '').slice(0, 10) <= query.submitted_to!)

  // 두배적금은 점수순, 취업패키지는 접수순이 기본이다 — 선발 방식이 다르다.
  const defaultSort = query.program === JOB_PACKAGE ? 'submitted' : 'score'
  const sortKey = query.sort || defaultSort
  rows =
    sortKey === 'submitted'
      ? [...rows].sort((a, b) => (a.row.submitted_at ?? '').localeCompare(b.row.submitted_at ?? ''))
      : [...rows].sort((a, b) => compareTiebreak(a.tiebreak, b.tiebreak))

  const total = rows.length
  const page = Math.max(1, query.page ?? 1)
  const pageSize = Math.max(1, Math.min(query.page_size ?? 20, 200))
  const window = rows.slice((page - 1) * pageSize, (page - 1) * pageSize + pageSize)

  return {
    role,
    scope: {
      region: pickedRegion,
      town: pickedTown,
      region_locked: role.requires_region,
      town_locked: role.requires_town,
      regions: REGIONS,
      towns: pickedRegion ? [...TOWNS[pickedRegion]].sort() : [],
    },
    filters: {
      programs: Object.entries(PROGRAM_NAMES).map(([code, name]) => ({ code, name })),
      ai_statuses: (Object.keys(AI_STATUS_LABELS) as DocStatus[]).map((value) => ({
        value,
        label: AI_STATUS_LABELS[value],
      })),
      statuses: [
        { value: PENDING, label: '미처리' },
        ...role.actions.map((a) => ({ value: a.key, label: a.result_label })),
      ],
      // 선착순 사업에 점수순 정렬을 띄우면 누를 수는 있는데 아무 뜻이 없다.
      sorts:
        query.program === JOB_PACKAGE
          ? [{ value: 'submitted', label: '접수순 (선착순)' }]
          : [
              { value: 'score', label: '점수순 (두배적금)' },
              { value: 'submitted', label: '접수순' },
            ],
      applied: {
        program: query.program ?? null,
        status: query.status ?? null,
        ai_status: query.ai_status ?? null,
        submitted_from: query.submitted_from ?? null,
        submitted_to: query.submitted_to ?? null,
        sort: sortKey,
      },
    },
    columns: query.program === JOB_PACKAGE ? FIRST_COME_COLUMNS : LIST_COLUMNS,
    rank_label: query.program === JOB_PACKAGE ? '순번' : '순위',
    quota,
    first_come: firstComeSummary(query.program),
    total,
    page,
    page_size: pageSize,
    page_count: Math.max(1, Math.ceil(total / pageSize)),
    rows: window.map((e) => ({ ...e.row, rank: rankOf(e) })),
  }
}

// ---------------------------------------------------------------- 상세

/**
 * 원본 서류 대역 이미지.
 *
 * 목업에는 업로드된 PDF가 없다. 그렇다고 좌측 뷰어를 비워 두면 "근거 클릭 →
 * 원본 하이라이트"라는 이 화면의 핵심 동작을 보여줄 수 없다. 그래서 신청자의
 * 판독값을 그대로 박은 서류 모양 SVG를 만들어 이미지 서류로 넘긴다. 아래
 * `FIELD_Y` 좌표가 곧 bbox 좌표라 하이라이트가 실제로 맞는다.
 */
const PAGE_W = 760
const PAGE_H = 1040
const VALUE_X0 = 320
const VALUE_X1 = 660

const FIELD_Y0 = 240
const FIELD_STEP = 60

const fieldY = (index: number) => FIELD_Y0 + index * FIELD_STEP

/** `fields`에서 `index`번째 항목의 원본 위치. 아래 SVG가 그리는 자리와 같다. */
const bboxAt = (index: number) => ({
  page: 0,
  x0: VALUE_X0 - 8,
  y0: fieldY(index) - 26,
  x1: VALUE_X1,
  y1: fieldY(index) + 10,
})

const bboxOf = (fields: Record<string, string>, field: string) => {
  const index = Object.keys(fields).indexOf(field)
  return index < 0 ? null : bboxAt(index)
}

/** SVG 텍스트에 들어가면 안 되는 문자. 판독값에 &, < 가 섞여도 깨지지 않게 한다. */
const esc = (value: string) =>
  value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

function paperSvg(
  title: string,
  subtitle: string,
  fields: Record<string, string>,
  footer: string,
): string {
  const rows = Object.entries(fields)
    .map(([label, value], index) => {
      const y = fieldY(index)
      // 판독하지 못했거나 비어 있는 값은 원본에서도 눈에 띄어야 한다.
      const missing = value.startsWith('(')
      return `
        <line x1="60" y1="${y + 14}" x2="700" y2="${y + 14}" stroke="#d8dde5" stroke-width="1"/>
        <text x="72" y="${y}" font-size="19" fill="#5b6472">${esc(label)}</text>
        <text x="${VALUE_X0}" y="${y}" font-size="19" fill="${
          missing ? '#c0392b' : '#111827'
        }">${esc(value)}</text>`
    })
    .join('')

  const height = Math.max(PAGE_H, fieldY(Object.keys(fields).length) + 160)
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${PAGE_W}" height="${height}" viewBox="0 0 ${PAGE_W} ${height}">
    <rect width="${PAGE_W}" height="${height}" fill="#ffffff"/>
    <rect x="40" y="40" width="680" height="${height - 80}" fill="none" stroke="#9aa4b2" stroke-width="2"/>
    <text x="${PAGE_W / 2}" y="120" font-size="28" text-anchor="middle" fill="#111827">${esc(title)} (목업)</text>
    <text x="${PAGE_W / 2}" y="158" font-size="16" text-anchor="middle" fill="#6b7280">${esc(subtitle)}</text>
    <line x1="60" y1="185" x2="700" y2="185" stroke="#111827" stroke-width="2"/>
    ${rows}
    <text x="72" y="${height - 90}" font-size="14" fill="#9aa4b2">※ 이 문서는 화면 시연용 목업입니다. 실제 발급 문서가 아닙니다.</text>
    <text x="72" y="${height - 64}" font-size="14" fill="#9aa4b2">${esc(footer)}</text>
  </svg>`
}

const dataUrl = (svg: string) =>
  `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`

/** 서류 종류별 발행처 한 줄. 원본 상단에 찍힌다. */
const ISSUER_LINE: Record<string, string> = {
  건강보험료납부확인서: '국민건강보험공단',
  건강보험자격확인서: '국민건강보험공단',
  건강보험자격득실확인서: '국민건강보험공단',
  '4대보험가입내역확인서': '국민건강보험공단',
  일용근로내역서: '근로복지공단',
  사업자등록증명: '국세청 홈택스',
  농업경영체증명서: '농림축산식품부 농산물품질관리원',
  어업경영체증명서: '해양수산부 수산물품질관리원',
  주민등록초본: '행정안전부 정부24',
  주민등록등본: '행정안전부 정부24',
  신청서: '전북청년허브센터 온라인 작성본',
  면접확인서: '면접 실시 기업·기관 발급',
  결제영수증: '가맹점 발행',
  접수확인서: '시험 시행기관 발행',
  면접용사진사본: '촬영 스튜디오 제공',
  응시확인서: '시험 시행기관 발행',
  성적표: '시험 시행기관 발행',
}

/** 목업 서류 1장 → 화면이 읽는 `OfficerDocument`. */
function toOfficerDocument(entry: MockEntry, doc: MockDoc, index: number): OfficerDocument {
  const dateShown = doc.fields[doc.dateField] ?? ''
  return {
    // 상세 화면은 탭을 document_id로 구분한다. 한 건 안에서 겹치지 않게 띄운다.
    document_id: entry.row.application_id * 100 + index,
    slot_key: doc.slotKey,
    label: doc.label,
    expected_doc_type: doc.expectedDocType,
    detected_doc_type: doc.docType,
    status: doc.status,
    findings: doc.findings.map((f) => ({
      code: f.code,
      message: f.message,
      how_to_fix: f.how_to_fix,
      link: '',
      severity: f.severity === 'FAIL' ? ('FAIL' as const) : ('NEEDS_REVIEW' as const),
    })),
    file_url: dataUrl(
      paperSvg(
        doc.docType,
        `${ISSUER_LINE[doc.docType] ?? ''} · ${doc.dateField} ${dateShown || '-'}`,
        doc.fields,
        `신청번호 ${entry.row.application_no}`,
      ),
    ),
    file_name: `${entry.row.application_no}_${doc.slotKey}.png`,
    // 목업 원본은 SVG 이미지다. 뷰어가 pdf가 아닌 것은 이미지로 그린다.
    file_format: 'png',
    page_index: null,
    extracted: doc.fields,
    bboxes: Object.fromEntries(Object.keys(doc.fields).map((k, i) => [k, bboxAt(i)])),
    // 신청서는 화면에서 작성한 값이라 판독할 것이 없다. 신뢰도를 붙이면
    // 담당자가 OCR 결과로 읽는다.
    ocr_confidence: doc.docType === '신청서' ? null : doc.status === 'PASS' ? 0.97 : 0.68,
    ocr_tier: doc.docType === '신청서' ? null : doc.status === 'PASS' ? 'pdftext' : 'fallback',
    declared_issue_date: dateShown.startsWith('(') ? null : dateShown || null,
    uploaded_at: entry.row.submitted_at ?? '',
  }
}

const SCORE_LABELS: Record<string, string> = {
  income: '1. 중위소득(가구소득)',
  residence: '2. 도 거주기간',
  work: '3. 근로기간(현 직장)',
  age: '4. 신청자 연령',
}

const SCORE_SOURCE_FIELD: Record<string, string> = {
  income: '건강보험료',
  residence: '전입일',
  // 근로기간의 근거는 자격득실확인서의 **취득일**이다. 서류마다 같은 사실을
  // 부르는 이름이 다르므로, 필드명은 그 서류의 표기를 따라야 하이라이트가 맞는다.
  work: '취득일',
  age: '생년월일',
}

/**
 * 심사 항목 → 그 점수의 근거가 되는 서류.
 *
 * 항목을 클릭하면 좌측 뷰어가 이 서류의 해당 좌표로 간다 (R4.3). 소득은 건보료
 * 확인서에, 거주기간·연령은 초본에, 근로기간은 자격득실확인서의 취득일에 근거가
 * 있다 — 항목마다 봐야 할 종이가 다르다.
 */
const SCORE_SOURCE_SLOT: Record<string, string> = {
  income: 'nhis_payment',
  residence: 'resident_abstract',
  work: 'nhis_acquisition_loss',
  age: 'resident_abstract',
}

function scoreItems(entry: MockEntry): ScoreItemRow[] {
  if (!entry.scored) return []
  return entry.scored.items.map((item) => {
    const field = SCORE_SOURCE_FIELD[item.key]
    // 근거 서류를 안 낸 건이면(미제출) 첫 서류로 떨어진다 — 하이라이트는 못
    // 하지만 심사표 자체는 그려야 한다.
    const index = entry.docs.findIndex((d) => d.slotKey === SCORE_SOURCE_SLOT[item.key])
    const sourceIndex = index < 0 ? 0 : index
    const source = entry.docs[sourceIndex]
    const doc = entry.row.application_id * 100 + sourceIndex
    const basis: Record<string, string> = {
      income: `가구원수 ${entry.householdSize}인 · 월 고지금액 ${entry.monthlyPremium.toLocaleString(
        'ko-KR',
      )}원 → 중위소득 ${entry.scored!.incomePercent}%`,
      residence: `전입일 ${entry.transferIn} · 공고일(2026-03-03) 기준 ${entry.scored!.residenceYears}년 경과`,
      work: `현 직장 취업일 ${entry.employedAt} · 공고일 기준 ${entry.scored!.workYears}년 경과`,
      age: `생년월일 ${entry.birth} · 2026-03-03 기준 만 ${entry.scored!.age}세`,
    }
    return {
      key: item.key,
      label: SCORE_LABELS[item.key],
      score: item.score,
      max_score: item.max,
      band: item.band,
      basis: basis[item.key],
      source_doc: source.docType,
      source_document_id: doc,
      source_origin: '목업 판독값',
      bbox: bboxOf(source.fields, field),
      incomplete: false,
      source_slot_key: source.slotKey,
      source_file_url: null,
      source_file_format: 'png',
    }
  })
}

const won = (value: number) => `${value.toLocaleString('ko-KR')}원`

/**
 * 항목별 지급 내역 (`rules/subsidy.py`의 `estimate`와 같은 계산).
 *
 * 면접비만 정액이고 나머지 3종은 실비다 — 영수증 금액과 한도 중 작은 값.
 * 영수증이 인정되지 않는 회차(작년 결제·판독 실패·접수확인서 제출)는 금액이
 * 비어 있으므로 **미확정**으로 둔다. 합계에 끼워 넣으면 담당자가 지급 가능한
 * 금액으로 오해한다.
 */
function subsidyEstimate(entry: MockEntry): ReviewDetailData['subsidy'] {
  const lines = []
  const warnings: string[] = []

  for (const selection of entry.selections) {
    const item = JOB_ITEMS[selection.key]
    for (let index = 1; index <= selection.count; index += 1) {
      const receipt = selection.receipts[index - 1] ?? null
      const flagged = selection.receiptFlagged[index - 1] ?? false
      let granted = 0
      let calculation: string
      let pending = false

      if (!item.actualCost) {
        granted = item.unitCap
        calculation = `정액 ${won(item.unitCap)}(회당) → ${won(granted)} 지급`
      } else if (receipt === null) {
        calculation = '영수증이 인정되지 않아 지급액이 확정되지 않았습니다.'
        pending = true
      } else if (receipt > item.unitCap) {
        granted = item.unitCap
        calculation = `영수증 ${won(receipt)} > 한도 ${won(item.unitCap)} → ${won(granted)} 지급`
      } else {
        granted = receipt
        calculation = `영수증 ${won(receipt)} ≤ 한도 ${won(item.unitCap)} → ${won(granted)} 지급`
      }

      // 금액은 읽혔지만 담당자가 봐야 하는 회차. 계산은 남기고 미확정으로 돌린다.
      // 이미 미확정인 줄(영수증 자체가 인정 안 됨)에는 덧붙이지 않는다.
      if (flagged && !pending) {
        pending = true
        calculation += ' · 영수증 확인 필요'
      }

      lines.push({
        item_type: selection.key,
        label: `${item.label}${item.maxCount > 1 ? ` ${index}회차` : ''}`,
        index,
        unit_cap: item.unitCap,
        actual_cost: item.actualCost,
        receipt_amount: receipt,
        granted_amount: granted,
        calculation,
        pending,
      })
    }
  }

  if (lines.some((l) => l.pending)) {
    warnings.push(
      '영수증이 인정되지 않았거나 확인이 필요한 회차가 있어 합계가 확정 금액이 아닙니다.',
    )
  }

  return {
    lines,
    total_granted: lines.reduce((sum, l) => sum + l.granted_amount, 0),
    warnings,
    pending: lines.some((l) => l.pending),
  }
}

/** 7일 보완 기한 카운트다운. 1차(4~5월) 건은 이미 기한이 지났다. */
function supplementView(entry: MockEntry): ReviewDetailData['supplement'] {
  if (!entry.supplementDeadline) return null
  const seconds = (Date.parse(`${entry.supplementDeadline}Z`) - Date.now()) / 1000
  return {
    days: JOB_SUPPLEMENT_DAYS,
    deadline: entry.supplementDeadline,
    days_left: Math.max(0, Math.ceil(seconds / 86_400)),
    hours_left: Math.max(0, Math.floor(seconds / 3600)),
    expired: seconds <= 0,
    targets: entry.docs
      .filter((d) => d.status !== 'PASS')
      .map((d) => ({ label: d.label, reason: d.findings[0]?.message ?? '확인이 필요합니다.' })),
    notice:
      seconds <= 0
        ? '보완 기한이 지났습니다. 미보완 시 지원대상에서 제외하고 후순위자를 선정합니다.'
        : '7일 내 보완 안내 대상입니다. 미보완 시 후순위자로 교체됩니다.',
  }
}

/** 심사 상세. 분할 뷰가 읽는 전부를 목업으로 채운다. */
export function mockReviewDetail(applicationId: number, roleKey: string): ReviewDetailData {
  const entry = byId.get(applicationId)
  if (!entry) throw new Error(`목업에 없는 신청 건입니다 (${applicationId})`)

  const role = roleOf(roleKey)
  const isSavings = entry.row.program_code === DOUBLE_SAVINGS
  const items = scoreItems(entry)
  const byKey = new Map(items.map((i) => [i.key, i]))
  const overIncome = entry.scored !== null && entry.scored.incomePercent > INCOME_LIMIT_PERCENT

  // 초본을 떼 보니 도외 주소인 건은 자격요건 ①이 무너진다.
  const outOfRegion = entry.docs.some((d) =>
    d.findings.some((f) => f.code === 'OUT_OF_REGION'),
  )
  const abstractDoc = entry.docs.find((d) => d.slotKey === 'resident_abstract')

  const eligibility = [
    {
      key: 'residence',
      label: isSavings
        ? '① 거주지 — 공고일 기준 전북특별자치도 주민등록'
        : '① 거주지 — 전북특별자치도 내 거주 청년',
      ok: !outOfRegion,
      basis: isSavings
        ? `주소지 ${entry.row.region} · ${byKey.get('residence')?.basis ?? entry.address}`
        : `주민등록초본 주소 ${abstractDoc?.fields['주소'] ?? entry.address}`,
    },
    {
      key: 'age',
      label: isSavings
        ? '② 연령 — 2026-03-03 기준 만 18~39세'
        : '② 연령 — 2026년 기준 18~39세 (1987.1.1. ~ 2008.12.31. 출생)',
      ok: true,
      basis: byKey.get('age')?.basis ?? `생년월일 ${entry.birth}`,
    },
  ]
  if (!isSavings) {
    // 사업계획서 「※ 2026. 1. 1. 이후의 서류만 인정」 — 이 사업 심사의 축이라
    // 자격요건 칸에 한 줄로 세운다.
    const stale = entry.docs.filter((d) =>
      d.findings.some((f) => f.code === 'ISSUED_BEFORE_CUTOFF'),
    )
    eligibility.push({
      key: 'doc_period',
      label: '③ 서류 인정 기간 — 2026. 1. 1. 이후 발급·결제분',
      ok: stale.length === 0,
      basis:
        stale.length === 0
          ? '제출 서류의 기준 날짜가 모두 인정 기간 안입니다.'
          : stale
              .map((d) => `${d.label}: ${d.dateField} ${d.fields[d.dateField]}`)
              .join(' · '),
    })
  }
  if (isSavings) {
    eligibility.push({
      key: 'work',
      label: '③ 근로 — 공고일 기준 계속 근로 중',
      ok: true,
      basis: byKey.get('work')?.basis ?? '',
    })
    eligibility.push({
      key: 'income',
      label: '④ 소득 — 가구 기준 중위소득 140% 이하',
      ok: !overIncome,
      basis: byKey.get('income')?.basis ?? '',
    })
  }

  const exclusions = isSavings
    ? [
        {
          label:
            '자가진단 6. 제외 대상(유사 자산형성사업 수혜자·직업군인·수급자 등) 해당 시 선정 취소에 동의',
          answer: '예',
          ok: true,
          source: '서식2 자가진단',
        },
        {
          label: '자가진단 8. 중도해지 사유(사망·전출·부정수급 등) 확인',
          answer: '예',
          ok: true,
          source: '서식2 자가진단',
        },
        {
          label: '동일 사업 중복 신청',
          answer: '해당 없음',
          ok: true,
          source: '엔진 2단계 (행복e음·일모아 조회 자리 — 데모는 미연동)',
        },
        {
          label: '유사 자산형성사업 동시 수혜',
          answer: '해당 없음',
          ok: true,
          source: '엔진 2단계 (행복e음·일모아 조회 자리 — 데모는 미연동)',
        },
      ]
    : [
        {
          label: '동일 사업 중복 신청',
          answer: '해당 없음',
          ok: true,
          source: '엔진 2단계 (행복e음·일모아 조회 자리 — 데모는 미연동)',
        },
      ]

  return {
    application_id: entry.row.application_id,
    application_no: entry.row.application_no,
    name: entry.row.name,
    program_code: entry.row.program_code,
    program_name: entry.row.program_name,
    region: entry.row.region,
    town: entry.row.town,
    status: entry.row.status,
    submitted_at: entry.row.submitted_at,
    ai: {
      final_status: entry.row.ai_status,
      final_status_label: entry.row.ai_status_label,
      // 1단계는 서류 적합성, 2단계는 자격 판정이다. 취업패키지의 2단계 자격요건은
      // 거주지와 나이뿐이라, 도외 주소일 때만 2단계가 무너진다.
      stage1_status: isSavings
        ? entry.row.ai_status === 'FAIL' && !overIncome
          ? 'FAIL'
          : 'PASS'
        : entry.row.ai_status,
      stage2_status: isSavings ? (overIncome ? 'FAIL' : entry.row.ai_status) : outOfRegion ? 'FAIL' : 'PASS',
      recommended_action:
        entry.row.ai_status === 'PASS'
          ? '자동 승인'
          : entry.row.ai_status === 'FAIL'
            ? isSavings
              ? '반려 검토'
              : '7일 내 서류 보완 안내'
            : '담당자 확인 필요',
      reasons: entry.reasons,
    },
    score_sheet: {
      items,
      total: entry.scored?.total ?? 0,
      max_total: 100,
      income_percent: entry.scored?.incomePercent ?? null,
      income_over_limit: overIncome,
      incomplete: false,
      tiebreak: entry.tiebreak,
      notes: ['목업 데이터입니다 — 실제 제출 서류에서 판독한 값이 아닙니다.'],
    },
    selection: isSavings ? 'scored' : 'first_come',
    subsidy: isSavings ? null : subsidyEstimate(entry),
    supplement: supplementView(entry),
    documents: entry.docs.map((d, i) => toOfficerDocument(entry, d, i)),
    forms: [],
    eligibility,
    exclusions,
    decision: {
      decision: entry.row.decision,
      label: entry.row.decision_label,
      memo: entry.memo,
      officer_role: entry.row.officer_role,
      decided_at: entry.decidedAt,
    },
    role,
  }
}

// ---------------------------------------------------------------- 담당자 처리

/**
 * 승인·반려·보류를 목업 배열에 그대로 반영한다.
 *
 * 새로고침하면 초기 상태로 돌아간다 — 목업은 브라우저 메모리에만 있다. 시연을
 * 다시 처음부터 돌리기에는 오히려 이 편이 편하다.
 */
export function mockDecide(
  applicationIds: number[],
  roleKey: string,
  decision: DecisionKey,
  memo: string,
): number {
  const now = iso(new Date())
  let processed = 0
  for (const id of applicationIds) {
    const entry = byId.get(id)
    if (!entry) continue
    entry.row.decision = decision
    entry.row.officer_role = roleKey
    entry.row.decision_label = decisionLabel(roleKey, decision)
    entry.row.status = 'decided'
    entry.memo = memo || entry.memo
    entry.decidedAt = now
    processed += 1
  }
  return processed
}
