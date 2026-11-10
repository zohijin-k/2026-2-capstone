import { formatPhone, isValidPhone } from './phone.ts'

const cases: Array<[string, string]> = [
  ['010', '010'],
  ['0101', '010-1'],
  ['0101234', '010-1234'],
  ['01012345678', '010-1234-5678'],
  ['0111234567', '011-1234-567'],
  ['0101234567', '010-1234-567'],
  ['010 1234 5678', '010-1234-5678'],
  ['+82 10-1234-5678', '010-1234-5678'],
  ['phone 0101234567899', '010-1234-5678'],
]

for (const [input, expected] of cases) {
  const actual = formatPhone(input)
  if (actual !== expected) throw new Error(`formatPhone(${input}) returned ${actual}, expected ${expected}`)
}

const validCases: Array<[string, boolean]> = [
  ['010-1234-5678', true],
  ['011-1234-5678', false],
  ['011-123-4567', false],
  ['0101234567', false],
]

for (const [input, expected] of validCases) {
  const actual = isValidPhone(input)
  if (actual !== expected) throw new Error(`isValidPhone(${input}) returned ${actual}, expected ${expected}`)
}
