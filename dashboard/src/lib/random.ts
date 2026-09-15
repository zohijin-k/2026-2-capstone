/** 시드 고정 난수 (mulberry32) — 새로고침해도 같은 목업 데이터가 나오도록 */
export function createRandom(seed: number) {
  let state = seed >>> 0

  const next = (): number => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }

  const weightedIndex = (weights: readonly number[]): number => {
    const total = weights.reduce((sum, weight) => sum + weight, 0)
    let remaining = next() * total
    for (let i = 0; i < weights.length; i++) {
      remaining -= weights[i]
      if (remaining < 0) return i
    }
    return weights.length - 1
  }

  return {
    next,
    weightedIndex,
    int: (min: number, max: number): number => min + Math.floor(next() * (max - min + 1)),
    chance: (probability: number): boolean => next() < probability,
    weighted: <T>(items: readonly T[], weights: readonly number[]): T => items[weightedIndex(weights)],
  }
}

export type Random = ReturnType<typeof createRandom>
