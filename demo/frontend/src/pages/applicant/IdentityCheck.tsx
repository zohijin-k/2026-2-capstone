/**
 * 본인인증 (데모).
 *
 * 업로드 서류가 '이 신청자의 것인지' 대조하려면 기준 신원이 먼저 있어야 한다.
 * 신청서에 손으로 적은 성명·생년월일은 기준이 될 수 없으므로 신청 맨 앞에서 정한다.
 *
 * 실서비스는 로그인할 때 PASS·간편인증으로 받는다. 데모는 그 단계를 흉내 내어
 * 입력값을 그대로 인증 결과로 쓴다. 서약 서명은 신원 증명이 아니라
 * "본인 서류만 제출한다"는 책임 확인이다.
 *
 * 서명은 화면에 직접 하거나, 서명 파일(PNG·JPG·PDF, 5MB 이하)을 올린다.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { fetchApplication, verifyIdentity, type Identity, type Blocker } from '../../api.ts'
import FilePreview from '../../components/FilePreview.tsx'
import PdfPages from '../../components/PdfPages.tsx'
import SignaturePad from '../../components/SignaturePad.tsx'
import { DateTriple } from '../../forms/FormSheet.tsx'
import { formatPhone, isValidPhone, phoneCursorPosition } from '../../forms/phone.ts'
import { EMPTY_YMD, ymdToISO, type YMD } from '../../forms/ymd.ts'
import './identity-check.css'

const SIGN_MODES = ['직접 서명', '서명 파일 올리기'] as const
type SignMode = (typeof SIGN_MODES)[number]

const SIGN_FILE_ACCEPT = '.png,.jpg,.jpeg,.pdf'
const SIGN_FILE_MAX = 5 * 1024 * 1024
/** 확장자 → 형식. 브라우저가 형식을 비워 보내는 경우가 있어 확장자로도 판별한다. */
const SIGN_FILE_EXT: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  pdf: 'application/pdf',
}

function signFileType(file: File): string | null {
  if (Object.values(SIGN_FILE_EXT).includes(file.type)) return file.type
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return SIGN_FILE_EXT[ext] ?? null
}

interface SignFile {
  name: string
  type: string
  /** 서버로 보낼 값 */
  dataUrl: string
  /** 화면 미리보기용 (blob URL) */
  previewUrl: string
}

const PLEDGE =
  '본인은 위 정보의 당사자이며, 신청에 제출하는 서류는 모두 본인 명의임을 확인합니다. ' +
  '타인의 서류를 제출하거나 사실과 다른 내용을 제출한 경우 선정 취소 등 불이익을 받는 데 동의합니다.'

interface Props {
  appId: number
  /** 이미 인증을 마쳤으면 결과만 보여준다 */
  identity: Identity | null
  onVerified: (identity: Identity, mobile: string) => void
  onNext: () => void
}

export default function IdentityCheck({ appId, identity, onVerified, onNext }: Props) {
  const [name, setName] = useState('')
  const [birth, setBirth] = useState<YMD>(EMPTY_YMD)
  const [phone, setPhone] = useState('')
  const phoneInput = useRef<HTMLInputElement>(null)
  const pendingPhoneCaret = useRef<number | null>(null)
  const [pledge, setPledge] = useState(false)
  const [signMode, setSignMode] = useState<SignMode>('직접 서명')
  const [drawn, setDrawn] = useState('')
  const signBody = useRef<HTMLDivElement>(null)
  const [signWidth, setSignWidth] = useState(320)
  const [file, setFile] = useState<SignFile | null>(null)
  const [fileKey, setFileKey] = useState(0)
  const [viewing, setViewing] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [eligibilityResult, setEligibilityResult] = useState<{
    appId: number; birth: string; blockers: Blocker[]
  } | null>(null)
  const eligibilityBlockers = eligibilityResult?.appId === appId && eligibilityResult.birth === identity?.birth
    ? eligibilityResult.blockers : []

  useEffect(() => {
    if (!identity) return
    let active = true
    fetchApplication(appId).then((data) => {
      if (active) setEligibilityResult({ appId, birth: identity.birth, blockers: data.eligibility_blockers ?? [] })
    }).catch(() => {
      if (active) setError('신청 자격 안내를 불러오지 못했습니다. 다시 확인해 주세요.')
    })
    return () => { active = false }
  }, [appId, identity])

  useLayoutEffect(() => {
    const input = phoneInput.current
    const digits = pendingPhoneCaret.current
    if (!input || digits === null) return
    const position = phoneCursorPosition(phone, digits)
    input.setSelectionRange(position, position)
    pendingPhoneCaret.current = null
  }, [phone])

  // 미리보기 URL은 파일을 바꾸거나 화면을 떠날 때 해제한다.
  useEffect(() => {
    if (!file) return undefined
    return () => URL.revokeObjectURL(file.previewUrl)
  }, [file])

  useLayoutEffect(() => {
    const body = signBody.current
    if (!body) return undefined
    const updateWidth = () => setSignWidth(Math.min(420, Math.max(1, body.clientWidth - 32)))
    updateWidth()
    const observer = new ResizeObserver(updateWidth)
    observer.observe(body)
    return () => observer.disconnect()
  }, [identity])

  if (identity) {
    return (
      <section className="idcheck">
        <h2 className="idcheck__title">본인인증</h2>
        {eligibilityBlockers.map((blocker) => (
          <p key={blocker.target} className="idcheck__error" role="alert">{blocker.message}</p>
        ))}
        {error && <p className="idcheck__error" role="alert">{error}</p>}
        <div className="idcheck__done">
          <strong>본인인증을 마쳤습니다.</strong>
          <dl>
            <div>
              <dt>성명</dt>
              <dd>{identity.name}</dd>
            </div>
            <div>
              <dt>생년월일</dt>
              <dd>{identity.birth}</dd>
            </div>
            <div>
              <dt>휴대폰</dt>
              <dd>{identity.phone}</dd>
            </div>
          </dl>
          <p>
            신청서의 성명·생년월일은 이 정보로 채워지며 고칠 수 없습니다. 올리시는 서류도 이
            정보와 같은 사람의 것인지 확인합니다.
          </p>
        </div>
        <div className="flow__actions">
          <button type="button" className="btn btn--primary" onClick={onNext}>
            자가진단으로
          </button>
        </div>
      </section>
    )
  }

  const birthISO = ymdToISO(birth)
  const signature = signMode === '직접 서명' ? drawn : (file?.dataUrl ?? '')
  const phoneDigits = phone.replace(/\D/g, '')
  const phoneValid = isValidPhone(phone)
  const phoneInvalid = phoneDigits.length === 11 && !phoneValid
  const ready = Boolean(name.trim() && birthISO && phoneValid && pledge && signature)

  /** 서명 파일을 data URL로 읽는다. 형식·크기는 서버도 다시 확인한다. */
  const pickFile = (picked: File | undefined) => {
    setError('')
    if (!picked) {
      setFile(null)
      return
    }
    const type = signFileType(picked)
    if (!type) {
      setFile(null)
      setError('서명 파일은 PNG·JPG·PDF만 올릴 수 있습니다.')
      return
    }
    if (picked.size > SIGN_FILE_MAX) {
      setFile(null)
      setError('서명 파일은 5MB 이하로 올려 주세요.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      // 형식을 비워 보낸 파일도 서버가 읽을 수 있게 data URL 머리를 판별한 형식으로 맞춘다.
      const raw = String(reader.result)
      const dataUrl = `data:${type};base64,${raw.slice(raw.indexOf(',') + 1)}`
      setFile({ name: picked.name, type, dataUrl, previewUrl: URL.createObjectURL(picked) })
    }
    reader.readAsDataURL(picked)
  }

  const clearFile = () => {
    setFile(null)
    setFileKey((k) => k + 1) // 같은 파일을 다시 고를 수 있게 입력칸을 새로 만든다
  }

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await verifyIdentity(appId, {
        name,
        birth: birthISO,
        phone,
        pledge,
        signature_data_url: signature,
        signature_kind: signMode === '직접 서명' ? 'electronic' : 'uploaded',
      })
      onVerified(result, phone)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="idcheck">
      <h2 className="idcheck__title">본인인증</h2>
      <p className="idcheck__demo">
        데모 화면입니다. 실제 서비스에서는 로그인할 때 휴대폰·간편인증으로 대신합니다.
      </p>

      <div className="idcheck__form">
        <label>
          <span>성명</span>
          <input
            className="form-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="성명"
            autoComplete="name"
          />
        </label>
        <label>
          <span>생년월일</span>
          <DateTriple value={birth} onChange={setBirth} ariaPrefix="생년월일" />
        </label>
        <label>
          <span>휴대폰</span>
          <input
            className="form-input"
            type="tel"
            inputMode="numeric"
            autoComplete="tel"
            maxLength={13}
            placeholder="010-0000-0000"
            value={phone}
            ref={phoneInput}
            onChange={(e) => {
              const input = e.currentTarget
              const beforeCursor = input.value.slice(0, input.selectionStart ?? input.value.length)
              let digitCount = beforeCursor.replace(/\D/g, '').length
              if (beforeCursor.trimStart().startsWith('+82') && digitCount >= 2) digitCount -= 1
              pendingPhoneCaret.current = digitCount
              setPhone(formatPhone(input.value))
            }}
            onPaste={(e) => {
              const pasted = e.clipboardData.getData('text')
              if (!pasted) return
              e.preventDefault()
              const formatted = formatPhone(pasted)
              pendingPhoneCaret.current = formatted.replace(/\D/g, '').length
              setPhone(formatted)
            }}
            onKeyDown={(e) => {
              const input = e.currentTarget
              const cursor = input.selectionStart
              if (
                e.key !== 'Backspace' ||
                cursor === null ||
                cursor !== input.selectionEnd ||
                cursor === 0 ||
                input.value[cursor - 1] !== '-'
              ) return
              e.preventDefault()
              const digitCount = input.value.slice(0, cursor).replace(/\D/g, '').length
              const digits = phone.replace(/\D/g, '')
              if (digitCount === 0) return
              pendingPhoneCaret.current = digitCount - 1
              setPhone(formatPhone(`${digits.slice(0, digitCount - 1)}${digits.slice(digitCount)}`))
            }}
            aria-label="휴대폰 번호"
          />
          {phoneInvalid && (
            <small className="idcheck__phone-error">
              010으로 시작하는 휴대폰 번호를 입력해 주세요.
            </small>
          )}
        </label>
      </div>

      <div className="idcheck__pledge">
        <h3>본인 확인 서약</h3>
        <p>{PLEDGE}</p>
        <label className="idcheck__agree">
          <input type="checkbox" checked={pledge} onChange={(e) => setPledge(e.target.checked)} />
          위 내용을 확인했으며 동의합니다.
        </label>
        <div className="idcheck__sign">
          <span className="idcheck__sign-label">서명</span>
          <div>
            <div className="idcheck__modes" role="radiogroup" aria-label="서명 방식">
              {SIGN_MODES.map((m) => (
                <label key={m} className="idcheck__mode">
                  <input
                    type="radio"
                    name="identity-sign-mode"
                    checked={signMode === m}
                    onChange={() => {
                      setSignMode(m)
                      setError('')
                    }}
                  />
                  <span>{m === '직접 서명' ? '그리기' : '서명 파일 업로드'}</span>
                </label>
              ))}
            </div>
            <div className="idcheck__signature-body" ref={signBody}>
              {signMode === '직접 서명' ? (
                <SignaturePad key={drawn ? `signed-${signWidth}` : `empty-${signWidth}`} value={drawn} onChange={setDrawn} width={signWidth} height={210} />
              ) : (
                <div className="idcheck__file">
                  {file && (
                    <button type="button" className="idcheck__preview" onClick={() => setViewing(true)} aria-label="올린 서명 크게 보기">
                      {file.type === 'application/pdf' ? (
                        <PdfPages url={file.previewUrl} width={Math.min(signWidth, 318)} maxHeight={138} maxPages={1} />
                      ) : (
                        <img src={file.previewUrl} alt="올린 서명 미리보기" />
                      )}
                      <span className="idcheck__zoomhint" aria-hidden="true">크게 보기</span>
                    </button>
                  )}
                  {!file && <span>PNG·JPG·PDF 서명 파일을 올려 주세요. (5MB 이하)</span>}
                  <label className="btn" htmlFor="identity-sign-file">{file ? '다른 파일 선택' : '파일 선택'}</label>
                  <input
                    key={fileKey}
                    id="identity-sign-file"
                    type="file"
                    accept={SIGN_FILE_ACCEPT}
                    aria-label="서명 파일"
                    onChange={(e) => pickFile(e.target.files?.[0])}
                  />
                </div>
              )}
            </div>
            {file && viewing && (
              <FilePreview
                url={file.previewUrl}
                name={file.name}
                kind={file.type === 'application/pdf' ? 'pdf' : 'image'}
                onClose={() => setViewing(false)}
              />
            )}
            <div className="idcheck__signature-foot">
              {signMode === '서명 파일 올리기' && file && <span className="idcheck__filename">{file.name}</span>}
              <button type="button" className="btn idcheck__clear" disabled={signMode === '직접 서명' ? !drawn : !file} onClick={() => signMode === '직접 서명' ? setDrawn('') : clearFile()}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v6m4-6v6" /></svg>
                지우기
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && <p className="idcheck__error">{error}</p>}

      <div className="flow__actions">
        <button
          type="button"
          className="btn btn--primary"
          disabled={!ready || busy}
          onClick={submit}
        >
          {busy ? '확인 중…' : '본인인증'}
        </button>
      </div>
    </section>
  )
}
