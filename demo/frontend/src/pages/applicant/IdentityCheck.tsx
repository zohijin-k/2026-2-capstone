/**
 * 본인인증 (데모).
 *
 * 업로드 서류가 '이 신청자의 것인지' 대조하려면 기준 신원이 먼저 있어야 한다.
 * 신청서에 손으로 적은 성명·생년월일은 기준이 될 수 없으므로 신청 맨 앞에서 정한다.
 *
 * 실서비스는 로그인할 때 PASS·간편인증으로 받는다. 데모는 그 단계를 흉내 내어
 * 입력값을 그대로 인증 결과로 쓴다. 서약 서명은 신원 증명이 아니라
 * "본인 서류만 제출한다"는 책임 확인이다.
 */

import { useState } from 'react'

import { verifyIdentity, type Identity } from '../../api.ts'
import SignaturePad from '../../components/SignaturePad.tsx'
import { DateTriple } from '../../forms/FormSheet.tsx'
import { EMPTY_YMD, ymdToISO, type YMD } from '../../forms/ymd.ts'
import './identity-check.css'

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
  const [signature, setSignature] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

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
  const ready = name.trim() && birthISO && phone.replace(/\D/g, '').length >= 10 && pledge && signature

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
          <span>서명</span>
          <SignaturePad value={signature} onChange={setSignature} />
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
