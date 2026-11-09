import { formatPhone } from './phone.ts'

const cases: Array<[string, string]> = [
  ['010', '010'],
  ['0101', '010-1'],
  ['0101234', '010-1234'],
  ['01012345678', '010-1234-5678'],
  ['0111234567', '011-123-4567'],
  ['010 1234 5678', '010-1234-5678'],
  ['+82 10-1234-5678', '010-1234-5678'],
  ['phone 0101234567899', '010-1234-5678'],
]

for (const [input, expected] of cases) {
  const actual = formatPhone(input)
  if (actual !== expected) throw new Error(`formatPhone(${input}) returned ${actual}, expected ${expected}`)
}
