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

/** 자격증명과 실제 응시료. 응시료가 한도(5만원)를 넘는 것도 섞는다. */
const CERTIFICATES: [string, number][] = [
  ['정보처리기사 필기', 19_400],
  ['정보처리기사 실기', 22_600],
  ['컴퓨터활용능력 1급 실기', 25_000],
  ['한국사능력검정시험 심화', 22_000],
  ['지게차운전기능사 실기', 29_000],
  ['전기기사 실기', 22_600],
  ['산업안전기사 실기', 34_000],
  ['사회복지사 2급 과정평가', 48_000],
  ['TOEIC 정기시험', 52_500],
  ['조리기능사 실기', 26_900],
  ['전산회계 1급', 30_000],
  ['미용사(일반) 실기', 64_000],
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

/** 목록 컬럼. `api/officer.LIST_COLUMNS`와 같은 순서·라벨. */
const LIST_COLUMNS = [
  { key: 'application_no', label: '신청번호' },
  { key: 'name', label: '성명' },
  { key: 'region', label: '시군' },
  { key: 'ai_status', label: 'AI판정' },
  { key: 'total_score', label: '점수' },
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

  // --- AI 판정. 소득 초과는 곧바로 부적합, 나머지는 확률로 섞는다.
  const dice = random()
  let aiStatus: DocStatus = 'PASS'
  if (overIncome) aiStatus = 'FAIL'
  else if (dice < 0.09) aiStatus = 'NEEDS_REVIEW'
  else if (dice < 0.13) aiStatus = 'FAIL'

  const reasons: Reason[] =
    aiStatus === 'FAIL'
      ? [overIncome ? FAIL_REASONS[0] : pick(random, FAIL_REASONS.slice(1))]
      : aiStatus === 'NEEDS_REVIEW'
        ? [pick(random, REVIEW_REASONS)]
        : []

  const missing =
    aiStatus === 'PASS'
      ? random() < 0.12
        ? 1
        : 0
      : aiStatus === 'NEEDS_REVIEW'
        ? between(random, 1, 2)
        : between(random, 1, 3)

  const insuranceType = random() < 0.8 ? '직장' : '지역'
  const { decision, officerRole, memo } = rollDecision(random, aiStatus)
  const submitted = submittedAt(random)
  const residenceDays = Math.round(
    (ANNOUNCEMENT_DATE.getTime() - new Date(transferIn).getTime()) / 86_400_000,
  )
  const workDays = Math.round(
    (ANNOUNCEMENT_DATE.getTime() - new Date(employedAt).getTime()) / 86_400_000,
  )

  const doc: MockDoc = {
    slotKey: 'nhis_payment',
    label: '건강보험료 납부확인서',
    docType: '건강보험료납부확인서',
    expectedDocType: '건강보험료납부확인서',
    dateField: '발급일',
    status: aiStatus,
    receiptAmount: null,
    fields: {
      성명: name,
      생년월일: birth,
      주소: address,
      전입일: transferIn,
      가구원수: `${householdSize}인`,
      가입구분: `${insuranceType}가입자`,
      건강보험료: `${monthlyPremium.toLocaleString('ko-KR')}원`,
      취업일: employedAt,
    },
    findings: reasons.map((r) => ({
      code: r.code,
      message: r.message,
      how_to_fix: '원본을 다시 발급받아 올리도록 안내하세요.',
      severity: aiStatus === 'FAIL' ? ('FAIL' as DocStatus) : ('NEEDS_REVIEW' as DocStatus),
    })),
  }

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
    },
    scored,
    birth,
    address,
    transferIn,
    employedAt,
    householdSize,
    monthlyPremium,
    insuranceType,
    reasons,
    docs: [doc],
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
}

/** 도외 주소 — 초본을 떼 보니 전북이 아닌 경우. */
const OUT_OF_REGION_ADDRESSES = [
  '대전광역시 서구 둔산동 1234',
  '충청남도 천안시 서북구 불당동 45',
  '서울특별시 관악구 신림동 77',
  '경기도 수원시 팔달구 인계동 210',
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
    return { key, count, receipts }
  })
}

/** 신청서(온라인 작성본)의 문제. 서류를 떼기 전에 신청서부터 틀리는 경우다. */
function formIssue(random: () => number, name: string): Issue | null {
  const dice = random()
  if (dice < 0.05) {
    return {
      code: 'ITEM_NOT_SELECTED',
      severity: 'FAIL',
      message: '신청분야(지원 항목) 체크가 비어 있습니다.',
      howToFix: '어떤 항목을 신청하는지 체크한 신청서를 다시 받아야 합니다.',
      reason: '신청서의 신청분야 체크가 누락되었습니다.',
      patch: { 신청분야: '(미체크)' },
    }
  }
  if (dice < 0.09) {
    return {
      code: 'CONSENT_UNCHECKED',
      severity: 'FAIL',
      message: '개인정보 수집·이용·제공 동의서 체크가 누락되었습니다.',
      howToFix: '동의 항목을 체크한 신청서를 다시 받아야 합니다.',
      reason: '개인정보 동의서 체크가 누락되었습니다.',
      patch: { '개인정보 동의': '(미체크)' },
    }
  }
  if (dice < 0.13) {
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
  if (dice < 0.04) {
    return {
      code: 'DOC_NOT_SUBMITTED',
      severity: 'FAIL',
      message: '주민등록초본이 제출되지 않았습니다.',
      howToFix: '공통서류입니다. 초본을 제출해야 접수가 인정됩니다.',
      reason: '공통서류인 주민등록초본이 제출되지 않았습니다.',
      patch: { 발급일: '(미제출)', 주소: '(미제출)', 발급기관: '(미제출)' },
    }
  }
  if (dice < 0.09) {
    return {
      code: 'WRONG_DOC_TYPE',
      severity: 'FAIL',
      message: '주민등록등본이 제출되었습니다. 이 자리는 초본이어야 합니다.',
      howToFix: '등본에는 주소 이력이 없습니다. 주민등록초본을 다시 발급받아야 합니다.',
      reason: '주민등록등본이 제출되었습니다. (초본 필요)',
    }
  }
  if (dice < 0.13) {
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
  if (dice < 0.16) {
    const outside = pick(random, OUT_OF_REGION_ADDRESSES)
    return {
      code: 'OUT_OF_REGION',
      severity: 'FAIL',
      message: `주민등록 주소지가 도외입니다. (${outside})`,
      howToFix: '전북특별자치도 내 거주 청년만 신청할 수 있습니다.',
      reason: `주민등록 주소지가 전북특별자치도 밖입니다. (${outside})`,
      patch: { 주소: outside, 발급기관: outside.split(' ')[0] + '장' },
    }
  }
  if (dice < 0.19) {
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
  if (dice < 0.14 && examDate > applyPeriodEnd) {
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

  if (dice < 0.1) {
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

  if (key === 'certificate' && dice < 0.14) {
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

  if (dice < 0.18) {
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
  if (dice < 0.22 && receipt !== null && listPrice > 0) {
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
    }
  }

  // 결제일이 사건일보다 뒤. 시험을 치고 나서 결제된 것으로 읽히면 확인이 필요하다.
  if (dice < 0.26 && paidAt > eventDate) {
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
  if (key === 'suit' && dice < 0.34) {
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

  if (dice < 0.38) {
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
  // 접수일에서 몇 주 앞이 기본이다. 신청기간 이후 응시 사례를 위해 뒤쪽도 조금 둔다.
  const eventDate =
    random() < 0.06
      ? daysAfterDate(submittedDate, between(random, 10, 45))
      : daysBefore(submittedDate, between(random, 5, 95))
  const paidAt = daysAfterDate(eventDate, random() < 0.25 ? between(random, 1, 30) : 0)

  const employer = pick(random, JOB_EMPLOYERS)
  const cert = key === 'certificate' ? pick(random, CERTIFICATES) : ['', 0] as [string, number]
  const shop =
    key === 'suit'
      ? pick(random, SUIT_SHOPS)[0]
      : key === 'photo'
        ? pick(random, PHOTO_STUDIOS)[0]
        : cert[0]

  for (const spec of item.docs) {
    const isReceipt = spec.suffix === 'receipt'
    const fields: Record<string, string> = { 성명: name }
    let issue: Issue | null = null

    if (spec.suffix === 'exam') {
      fields['자격증명'] = cert[0]
      fields['응시일'] = eventDate
      fields['발급기관'] = '한국산업인력공단'
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

  // --- 공통서류 ② 주민등록초본. ③ 통장 사본은 계좌 입력으로 갈음한다.
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
      const receiptDoc = made.docs.find((d) => d.slotKey.endsWith('_receipt'))
      if (receiptDoc) selection.receipts[index - 1] = receiptDoc.receiptAmount
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
    },
    scored: null,
    birth,
    address,
    transferIn: '',
    employedAt: '',
    householdSize: 0,
    monthlyPremium: 0,
    insuranceType: '',
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
  const quota = quotaRows(role, role.requires_region ? [pickedRegion] : REGIONS)

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
      sorts: [
        { value: 'score', label: '점수순 (두배적금)' },
        { value: 'submitted', label: '접수순 (취업패키지)' },
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
    columns: LIST_COLUMNS,
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
    ocr_confidence: doc.status === 'PASS' ? 0.97 : 0.68,
    ocr_tier: doc.status === 'PASS' ? 'pdftext' : 'fallback',
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
  work: '취업일',
  age: '생년월일',
}

function scoreItems(entry: MockEntry): ScoreItemRow[] {
  if (!entry.scored) return []
  // 두배적금은 서류가 한 장이라 근거 원본도 그 한 장이다.
  const source = entry.docs[0]
  const doc = entry.row.application_id * 100
  return entry.scored.items.map((item) => {
    const field = SCORE_SOURCE_FIELD[item.key]
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
      source_doc: '건강보험료납부확인서',
      source_document_id: doc,
      source_origin: '목업 판독값',
      bbox: bboxOf(source.fields, field),
      incomplete: false,
      source_slot_key: 'nhis_payment',
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
    warnings.push('영수증이 인정되지 않은 회차가 있어 합계가 확정 금액이 아닙니다.')
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
      stage1_status: entry.row.ai_status === 'FAIL' && !overIncome ? 'FAIL' : 'PASS',
      stage2_status: overIncome ? 'FAIL' : entry.row.ai_status,
      recommended_action:
        entry.row.ai_status === 'PASS'
          ? '자동 승인'
          : entry.row.ai_status === 'FAIL'
            ? '반려 검토'
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
