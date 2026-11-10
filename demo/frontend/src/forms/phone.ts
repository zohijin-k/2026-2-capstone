/** 입력 중 휴대폰 번호를 숫자 3-4-4 형식으로 보여준다. */
export function formatPhone(raw: string): string {
  let digits = raw.replace(/\D/g, '')
  if (raw.trimStart().startsWith('+82') && digits.startsWith('82')) {
    digits = `0${digits.slice(2)}`
  }
  digits = digits.slice(0, 11)

  if (digits.length <= 3) return digits
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`
}

/** 본인인증에서 받는 010 휴대폰 번호인지 확인한다. */
export function isValidPhone(raw: string): boolean {
  const digits = raw.replace(/\D/g, '')
  return digits.length === 11 && digits.startsWith('010')
}

/** 포맷된 값에서 앞에 있는 숫자 개수를 기준으로 커서 위치를 구한다. */
export function phoneCursorPosition(formatted: string, digitCount: number): number {
  if (digitCount <= 0) return 0
  let seen = 0
  for (let i = 0; i < formatted.length; i += 1) {
    if (/\d/.test(formatted[i])) seen += 1
    if (seen === digitCount) return i + 1
  }
  return formatted.length
}
