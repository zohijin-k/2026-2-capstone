/**
 * 목업 폴백 스위치.
 *
 * 켜지는 조건은 둘이다.
 *
 *   - `?mock=1` — 강제로 켠다. 백엔드가 떠 있어도 목업을 본다.
 *   - 자동 — 호출이 실패했거나 **접수 건이 0건**일 때. 빈 화면을 띄우고
 *     "데이터가 없습니다"로 시연이 끊기는 것보다, 예시로 채운 화면을 보여주고
 *     목업임을 상단에 밝히는 편이 낫다.
 *
 * `?mock=0`을 붙이면 어떤 경우에도 목업을 쓰지 않는다 — 실제 접수 건이 0건인 것을
 * 확인해야 할 때 쓴다.
 *
 * **화면마다 인스턴스를 따로 만든다.** 스위치 하나를 공유하면 현황 화면이 목업으로
 * 떨어지는 순간 담당자 목록까지 같이 끌려가서, 실제 접수 건이 있는데도 담당자가
 * 가짜 목록을 심사하게 된다. 배너는 뜨지만 시연 중 이유를 설명하기 곤란하다.
 */

import { INITIAL } from '../app/initial-params.ts'

const FORCED = INITIAL.mock === '1' || INITIAL.mock === 'on'
const BLOCKED = INITIAL.mock === '0' || INITIAL.mock === 'off'

export interface MockGate {
  /** 지금 이 화면이 목업을 보고 있는가. 상단 배너가 읽는다. */
  readonly active: boolean
  /** `?mock=0`으로 차단됐는가. 차단이면 실패를 삼키지 말고 그대로 올려야 한다. */
  readonly blocked: boolean
  /** 목업으로 넘어간다. 차단 상태면 넘어가지 않고 `false`를 돌려준다. */
  trip(): boolean
}

export function createMockGate(): MockGate {
  let active = FORCED
  return {
    get active() {
      return active
    },
    get blocked() {
      return BLOCKED
    },
    trip() {
      if (BLOCKED) return false
      active = true
      return true
    },
  }
}

/** 목업 신청 건의 id 시작점. 실제 DB id(1부터)와 절대 겹치지 않게 띄워 둔다. */
export const MOCK_ID_BASE = 900_000

/**
 * 이 id가 목업 건인가.
 *
 * `pages/officer/mock-data.ts`가 아니라 여기 둔 이유: 그 모듈은 106KB라 지연
 * 로드 대상인데, 이 판별은 동기로 필요하다. 상수 비교 한 줄을 위해 106KB를
 * 먼저 받을 수는 없다.
 */
export const isMockId = (applicationId: number) => applicationId >= MOCK_ID_BASE
