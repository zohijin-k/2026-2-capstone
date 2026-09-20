/**
 * 앱 부팅 시 URL 쿼리를 **한 번만** 읽어 얼려 둔다.
 *
 * 탭을 옮길 때 `history.replaceState`로 `?view=`를 갱신하는데, 파라미터를 읽는
 * 쪽이 각자 모듈 최상위에서 `window.location.search`를 보면 **읽는 시점에 따라
 * 값이 달라진다**. 특히 현황 화면은 첫 진입 때 지연 로드되므로, 그 모듈의 최상위
 * 파싱은 이미 바뀐 URL을 읽게 된다. 여기서 한 번 얼려 두면 그 순서 의존성이
 * 통째로 사라진다.
 *
 * 링크로 특정 화면을 열기 위한 파라미터들:
 *
 *   ?view=apply|officer|status   첫 화면 (없으면 신청자)
 *   ?mock=1|0                    담당자 목업 강제 / 차단
 *   ?data=mock|live              현황 데이터 소스 강제 (없으면 자동)
 *   ?role=city|province          현황을 담당자 시점으로 연다 (배점·커트라인 포함)
 *   ?date=YYYY-MM-DD             현황 기준일
 *   ?region=전주시                현황 시군 필터
 *   ?theme=light|dark            현황 차트 테마 (없으면 OS 설정)
 */

export type TabKey = 'apply' | 'officer' | 'status'

export const TAB_KEYS: readonly TabKey[] = ['apply', 'officer', 'status']

const params = new URLSearchParams(window.location.search)

/** 허용 목록에 있을 때만 돌려준다. 오타나 장난 값으로 화면이 깨지지 않게 한다. */
function pick<T extends string>(name: string, allowed: readonly T[]): T | null {
  const value = params.get(name)
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : null
}

export const INITIAL = {
  view: pick('view', TAB_KEYS) ?? 'apply',
  mock: pick('mock', ['1', 'on', '0', 'off'] as const),
  data: pick('data', ['mock', 'live'] as const),
  role: pick('role', ['city', 'province'] as const),
  //: 날짜 형식만 본다. 접수 기간 안으로 보정하는 것은 읽는 쪽 몫이다.
  date: params.get('date')?.match(/^\d{4}-\d{2}-\d{2}$/)?.[0] ?? null,
  //: 실제 시군 이름인지는 읽는 쪽이 14개 목록과 대조한다.
  region: params.get('region'),
  theme: pick('theme', ['light', 'dark'] as const),
} as const

/**
 * 탭 전환을 주소창에 반영한다. **나머지 파라미터는 건드리지 않는다** — 현황
 * 화면을 `?date=&region=`으로 열어 둔 채 다른 탭에 다녀와도 링크가 살아 있어야
 * 한다. 기본 화면인 신청자일 때는 `?view=`를 지워 주소를 깔끔하게 둔다.
 */
export function syncViewParam(view: TabKey): void {
  const next = new URLSearchParams(window.location.search)
  if (view === 'apply') next.delete('view')
  else next.set('view', view)
  const qs = next.toString()
  window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname)
}
