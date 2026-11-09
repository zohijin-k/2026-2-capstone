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

import { useEffect, useState } from 'react'

import { verifyIdentity, type Identity } from '../../api.ts'
import FilePreview from '../../components/FilePreview.tsx'
import PdfPages from '../../components/PdfPages.tsx'
import SignaturePad from '../../components/SignaturePad.tsx'
import { DateTriple } from '../../forms/FormSheet.tsx'
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
  onVerified: (identity: Identity) => void
  onNext: () => void
}

export default function IdentityCheck({ appId, identity, onVerified, onNext }: Props) {
  const [name, setName] = useState('')
  const [birth, setBirth] = useState<YMD>(EMPTY_YMD)
  const [phone, setPhone] = useState('')
  const [pledge, setPledge] = useState(false)
  const [signMode, setSignMode] = useState<SignMode>('직접 서명')
  const [drawn, setDrawn] = useState('')
  const [file, setFile] = useState<SignFile | null>(null)
  const [fileKey, setFileKey] = useState(0)
  const [viewing, setViewing] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // 미리보기 URL은 파일을 바꾸거나 화면을 떠날 때 해제한다.
  useEffect(() => {
    if (!file) return undefined
    return () => URL.revokeObjectURL(file.previewUrl)
  }, [file])

  if (identity) {
    return (
      <section className="idcheck">
        <h2 className="idcheck__title">본인인증</h2>
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
  const ready = name.trim() && birthISO && phone.replace(/\D/g, '').length >= 10 && pledge && signature

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
      onVerified(result)
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
            placeholder="010-0000-0000"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            aria-label="휴대폰 번호"
          />
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
                  <span>{m}</span>
                </label>
              ))}
            </div>
            {signMode === '직접 서명' ? (
              <SignaturePad value={drawn} onChange={setDrawn} width={320} height={120} />
            ) : (
              <div className="idcheck__file">
                {!file && (
                  <>
                    <input
                      key={fileKey}
                      type="file"
                      accept={SIGN_FILE_ACCEPT}
                      aria-label="서명 파일"
                      onChange={(e) => pickFile(e.target.files?.[0])}
                    />
                    <p className="idcheck__hint">PNG·JPG·PDF, 5MB 이하</p>
                  </>
                )}
                {file && (
                  <figure className="idcheck__previewbox">
                    <button
                      type="button"
                      className="idcheck__preview"
                      onClick={() => setViewing(true)}
                      aria-label="올린 서명 크게 보기"
                    >
                      {file.type === 'application/pdf' ? (
                        <PdfPages url={file.previewUrl} width={318} maxHeight={138} maxPages={1} />
                      ) : (
                        <img src={file.previewUrl} alt="올린 서명 미리보기" />
                      )}
                      <span className="idcheck__zoomhint" aria-hidden="true">
                        크게 보기
                      </span>
                    </button>
                    <figcaption>
                      <span className="idcheck__filename">{file.name}</span>
                      <button type="button" className="btn btn--small" onClick={clearFile}>
                        다시 선택
                      </button>
                    </figcaption>
                    {viewing && (
                      <FilePreview
                        url={file.previewUrl}
                        name={file.name}
                        kind={file.type === 'application/pdf' ? 'pdf' : 'image'}
                        onClose={() => setViewing(false)}
                      />
                    )}
                  </figure>
                )}
              </div>
            )}
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
