/**
 * 현황 화면이 볼 데이터를 고른다.
 *
 * 실데이터가 먼저고, 없거나 못 받으면 목업으로 떨어진다. **둘을 섞지는 않는다.**
 * 섞으면 시연에서 보여주고 싶은 것이 오히려 안 보인다 — 전주시 목업 5,828건에
 * 실제 1건을 더해 봐야 12,821이 12,822가 될 뿐이고, 커트라인은 가짜 경쟁자
 * 5,827명 기준으로 계산되어 담당자용 패널이 통째로 오염된다.
 *
 *   ?data=mock  강제로 목업
 *   ?data=live  강제로 실데이터 (0건이면 빈 화면 그대로 — 확인용)
 *   (없음)       자동 — 호출 실패 또는 접수 0건이면 목업
 *
 * 건수 임계값은 두지 않는다. "N건 넘으면 실데이터"로 하면 시연 도중 기준을 넘는
 * 순간 화면이 통째로 갈아엎어진다. 담당자 화면의 폴백도 같은 이유로 0건이냐
 * 아니냐 하나뿐이다.
 */

import { INITIAL } from '../../../app/initial-params.ts'
import type { Application, Dataset, RegionName, ScoreRow, Schedule } from './types'

/** `demo/backend/api/dashboard.py` 의 DashboardDataset 과 짝이다. */
interface LiveResponse {
  source: 'live'
  total: number
  generatedAt: number
  schedule: Schedule
  regions: { name: string; quota: number }[]
  applications: Application[]
  scores: ScoreRow[] | null
  scoresWithheldReason: string | null
  notes: string[]
}

/**
 * 목업 생성기(12,821건)는 폴백이 정해진 뒤에만 불러온다.
 *
 * 목업에도 배점 규칙을 똑같이 적용한다. 값이 브라우저에서 만들어지므로 숨겨도
 * 메모리에는 남고, 그런 뜻에서 여기서의 권한 분리는 시연용이다. 그래도 적용하는
 * 이유는 이 데모가 보여주려는 것이 **권한 구조 자체**이기 때문이다 — 데이터 출처에
 * 따라 배점이 보였다 안 보였다 하면 그 구조가 흐려진다. 대신 시연용이라는 사실을
 * 화면 문구에 그대로 적는다.
 */
async function loadMock(role: string | null): Promise<Dataset> {
  const dataset = (await import('./generate')).generateDataset()
  if (role) return dataset
  return {
    ...dataset,
    scores: undefined,
    scoresWithheldReason:
      '배점·커트라인은 담당자 시점에서만 표시합니다. ' +
      '(목업 구간에서는 값이 브라우저에서 만들어지므로 권한 분리가 시연용입니다)',
  }
}

async function fetchLive(role: string | null): Promise<LiveResponse> {
  const params = new URLSearchParams({ program: 'double_savings' })
  if (role) params.set('role', role)
  const res = await fetch(`/api/dashboard/dataset?${params}`)
  if (!res.ok) throw new Error(`현황 데이터를 받지 못했습니다 (${res.status})`)
  return (await res.json()) as LiveResponse
}

function toDataset(body: LiveResponse): Dataset {
  return {
    applications: body.applications,
    schedule: body.schedule,
    source: 'live',
    // null 을 그대로 두면 "빈 배열"과 구분되지 않는다. undefined 여야 배점 분포·
    // 커트라인을 아예 계산하지 않는 경로로 간다.
    scores: body.scores ?? undefined,
    scoresWithheldReason: body.scoresWithheldReason,
    notes: body.notes,
    quotaByRegion: Object.fromEntries(body.regions.map((r) => [r.name, r.quota])) as Partial<
      Record<RegionName, number>
    >,
  }
}

/**
 * @param role 담당자 시점으로 볼 때의 역할(`city` | `province`). 없으면 서버가
 *   배점을 아예 빼고 내려준다.
 */
export async function loadDataset(role: string | null): Promise<Dataset> {
  if (INITIAL.data === 'mock') return loadMock(role)
  try {
    const body = await fetchLive(role)
    if (body.total === 0 && INITIAL.data !== 'live') return loadMock(role)
    return toDataset(body)
  } catch (error) {
    if (INITIAL.data === 'live') throw error
    return loadMock(role)
  }
}

/** 지금 목업을 보고 있는 이유. 배지 툴팁에 그대로 띄운다. */
export function sourceReason(source: Dataset['source']): string {
  if (source === 'live') return '접수된 신청 건에서 집계한 값입니다.'
  if (INITIAL.data === 'mock') return '?data=mock 으로 목업을 강제했습니다.'
  return '접수된 신청 건이 없거나 백엔드를 불러오지 못해 목업으로 전환했습니다.'
}
