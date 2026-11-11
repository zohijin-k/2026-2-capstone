const EMAIL_PATTERN = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/

export function normalizeEmail(value: string): string {
  return value.normalize('NFKC').trim()
}

export function isValidEmail(value: string): boolean {
  const asciiOnly = [...value].every(character => character.charCodeAt(0) <= 0x7f)
  return value.length > 0 && asciiOnly && EMAIL_PATTERN.test(value)
}
