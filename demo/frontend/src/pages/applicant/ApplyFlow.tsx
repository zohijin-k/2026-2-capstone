/**
 * 신청자 플로우.
 *
 *   [1] 자가진단(서식2) → [2] 신청서(서식1, 절 단위 스텝) → [3] 동의(서식3·4·5)
 *   → [4] 서류 업로드(즉시 판정) → [5] 제출 전 최종 확인 → [6] 제출 → [7] 마이페이지
 *
 * 위저드 스텝 경계를 서식1의 절(Ⅰ~Ⅳ) 경계와 일치시킨다. 스텝은 서식을 재구성한
 * 것이 아니라 스크롤 위치를 나눈 것에 가깝고, "서식 전체 보기"를 켜면 한 장으로
 * 펼쳐진다.
 *
 * [5]의 "해당 위치로 이동"이 이 컴포넌트에서 처리된다. 사유만 보여주고 신청자가
 * 직접 찾아가게 하면 결국 처음부터 다시 훑게 된다.
 */

import { useEffect, useState } from 'react'

import {
  createApplication,
  patchApplication,
  postConsents,
  postSelfCheck,
  type Blocker,
  type ConsentPayload,
  type SelfCheckResult,
  type SubmitResult,
} from '../../api.ts'
import DocumentUpload from './DocumentUpload.tsx'
import FinalCheck from './FinalCheck.tsx'
import MyPage from './MyPage.tsx'
import Form1Application from '../../forms/Form1Application.tsx'
import Form2SelfCheck from '../../forms/Form2SelfCheck.tsx'
import { Form3PrivacyConsent, Form4ThirdPartyConsent } from '../../forms/Form34Consent.tsx'
import Form5AdminInfoConsent from '../../forms/Form5AdminInfoConsent.tsx'
import { EMPTY_CONSENT, type ConsentValue } from '../../forms/consent-model.ts'
import { EMPTY_FORM1, type Form1Value } from '../../forms/form1-model.ts'
import { EMPTY_FORM5, type Form5Value, type SignMode } from '../../forms/form5-model.ts'
import { allAnswered, type SelfCheckAnswers } from '../../forms/form2-model.ts'
import './apply-flow.css'

type Stage = 'selfCheck' | 'form1' | 'consent' | 'upload' | 'final' | 'mypage'

/** 서식1의 절 구조를 그대로 스텝 경계로 쓴다. */
const FORM1_STEPS = [
  { key: 'top' as const, label: '저축목적·유사사업' },
  { key: 'basic' as const, label: 'Ⅰ. 기본정보' },
  { key: 'tail' as const, label: 'Ⅱ~Ⅳ. 납입·계좌·기타' },
]

/** 최종 확인에서 되돌아갈 때, 그 항목이 들어 있는 서식1 스텝. */
const FIELD_STEP: Record<string, number> = {
  savingPurpose: 0,
  priorJoined: 0,
  name: 1,
  birth: 1,
  gender: 1,
  address: 1,
  mobile: 1,
  transferIn: 1,
  householdType: 1,
  householdSize: 1,
  workType: 1,
  employedAt: 1,
  workplaceName: 1,
  bankName: 2,
  accountNo: 2,
  accountHolder: 2,
}

export default function ApplyFlow() {
  const [appId, setAppId] = useState<number | null>(null)
  const [appNo, setAppNo] = useState('')
  const [stage, setStage] = useState<Stage>('selfCheck')
  const [error, setError] = useState('')

  const [answers, setAnswers] = useState<SelfCheckAnswers>({})
  const [checkResult, setCheckResult] = useState<SelfCheckResult | null>(null)

  const [form1, setForm1] = useState<Form1Value>(EMPTY_FORM1)
  const [step, setStep] = useState(0)
  const [wholeSheet, setWholeSheet] = useState(false)

  const [consent, setConsent] = useState<ConsentValue>(EMPTY_CONSENT)
  const [form5, setForm5] = useState<Form5Value>(EMPTY_FORM5)
  const [signMode, setSignMode] = useState<SignMode>('전자서명')

  const [submitted, setSubmitted] = useState<SubmitResult | null>(null)
  /** 업로드 화면에서 스크롤해 보여줄 슬롯. 최종 확인의 "이동"이 채운다. */
  const [focusSlot, setFocusSlot] = useState('')

  // 신청 건을 먼저 만들어 두고 단계마다 부분 저장한다(임시저장/이어서 작성).
  useEffect(() => {
    createApplication('double_savings')
      .then((a) => {
        setAppId(a.id)
        setAppNo(a.application_no)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const save = (body: { form1?: unknown; self_check?: unknown; form5?: unknown }) => {
    if (appId === null) return
    patchApplication(appId, body).catch(() => {
      /* 데모에서는 임시저장 실패를 조용히 넘긴다 */
    })
  }

  const runSelfCheck = async () => {
    if (appId === null) return
    const payload = Object.fromEntries(
      Object.entries(answers).filter(([, v]) => v),
    ) as Record<string, string>
    const result = await postSelfCheck(appId, payload)
    setCheckResult(result)
    if (result.eligible) setStage('form1')
  }

  const submitConsents = async () => {
    if (appId === null) return
    const payload: ConsentPayload[] = [
      { consent_type: 'privacy', agreed: consent.privacy === '동의함' },
      { consent_type: 'unique_id', agreed: consent.uniqueId === '동의함' },
      { consent_type: 'third_party', agreed: consent.thirdParty === '동의함' },
      {
        consent_type: 'admin_info',
        agreed: form5.agree === '동의함',
        signature_data_url: signMode === '전자서명' ? form5.signature : undefined,
        signature_kind: signMode === '전자서명' ? 'electronic' : 'handwritten',
      },
    ]
    await postConsents(appId, payload)
    save({ form5 })
    setStage('upload')
  }

  /** 최종 확인의 "해당 위치로 이동". 스텝·슬롯까지 정확히 되돌려 놓는다. */
  const goto = (b: Blocker) => {
    if (b.goto === 'form1') {
      setWholeSheet(false)
      setStep(FIELD_STEP[b.target] ?? 1)
      setStage('form1')
    } else if (b.goto === 'upload') {
      setFocusSlot(b.kind === 'document' ? b.target : '')
      setStage('upload')
    } else {
      setStage('consent')
    }
    window.scrollTo({ top: 0 })
  }

  const consentReady =
    consent.privacy === '동의함' &&
    consent.uniqueId === '동의함' &&
    consent.thirdParty === '동의함' &&
    form5.agree === '동의함' &&
    (signMode === '전자서명' ? !!form5.signature : !!form5.handwrittenFileName)

  if (error) return <p className="flow-error">{error}</p>

  return (
    <div className="flow">
      <header className="flow__head">
        <div>
          <h1>전북청년 함께 두배적금 참여 신청</h1>
          <p className="flow__sub">
            신청번호 {appNo || '발급 중…'} · 작성 내용은 단계마다 자동 저장됩니다
          </p>
        </div>
        <ol className="flow__stages">
          {(
            [
              ['selfCheck', '1. 자가진단'],
              ['form1', '2. 신청서 작성'],
              ['consent', '3. 동의'],
              ['upload', '4. 서류 업로드'],
              ['final', '5. 최종 확인'],
              ['mypage', '6. 마이페이지'],
            ] as const
          ).map(([key, label]) => (
            <li key={key} className={stage === key ? 'is-current' : undefined}>
              {label}
            </li>
          ))}
        </ol>
      </header>

      {/* ── [1] 자가진단 ── */}
      {stage === 'selfCheck' && (
        <>
          <Form2SelfCheck
            answers={answers}
            onChange={(next) => {
              setAnswers(next)
              setCheckResult(null)
              save({ self_check: next })
            }}
          />
          {checkResult && !checkResult.eligible && checkResult.failed_item && (
            <div className="flow-block flow-block--stop">
              <strong>{checkResult.failed_item}번 문항 — 신청 자격을 충족하지 않습니다.</strong>
              <p>{checkResult.reason}</p>
              {checkResult.alternative && <p className="flow-alt">{checkResult.alternative}</p>}
            </div>
          )}
          <div className="flow__actions">
            <button
              type="button"
              className="btn btn--primary"
              disabled={!allAnswered(answers)}
              onClick={runSelfCheck}
            >
              {allAnswered(answers) ? '자가진단 결과 확인' : '8문항에 모두 답해 주세요'}
            </button>
          </div>
        </>
      )}

      {/* ── [2] 신청서 (서식1) ── */}
      {stage === 'form1' && (
        <>
          <div className="flow__steps">
            {FORM1_STEPS.map((s, i) => (
              <button
                key={s.key}
                type="button"
                className={i === step && !wholeSheet ? 'step is-current' : 'step'}
                onClick={() => {
                  setStep(i)
                  setWholeSheet(false)
                }}
              >
                {s.label}
              </button>
            ))}
            <label className="flow__whole">
              <input
                type="checkbox"
                checked={wholeSheet}
                onChange={(e) => setWholeSheet(e.target.checked)}
              />
              서식1 전체 보기
            </label>
          </div>

          <Form1Application
            value={form1}
            onChange={(next) => {
              setForm1(next)
              save({ form1: next })
            }}
            only={wholeSheet ? undefined : FORM1_STEPS[step].key}
          />

          <div className="flow__actions">
            <button
              type="button"
              className="btn"
              onClick={() => (step === 0 ? setStage('selfCheck') : setStep(step - 1))}
            >
              이전
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() =>
                step === FORM1_STEPS.length - 1 || wholeSheet
                  ? setStage('consent')
                  : setStep(step + 1)
              }
            >
              {step === FORM1_STEPS.length - 1 || wholeSheet ? '동의 단계로' : '다음'}
            </button>
          </div>
        </>
      )}

      {/* ── [3] 동의 (서식3·4·5) ── */}
      {stage === 'consent' && (
        <>
          <Form3PrivacyConsent value={consent} onChange={setConsent} />
          <div className="flow__gap" />
          <Form4ThirdPartyConsent value={consent} onChange={setConsent} />
          <div className="flow__gap" />
          <Form5AdminInfoConsent
            value={form5}
            onChange={(v) => {
              setForm5(v)
              save({ form5: v })
            }}
            signMode={signMode}
            onSignModeChange={setSignMode}
          />
          <div className="flow__actions">
            <button type="button" className="btn" onClick={() => setStage('form1')}>
              이전
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={!consentReady}
              onClick={submitConsents}
            >
              {consentReady ? '동의 완료' : '모든 동의 항목과 서명이 필요합니다'}
            </button>
          </div>
        </>
      )}

      {/* ── [4] 서류 업로드 ── */}
      {stage === 'upload' && appId !== null && (
        <>
          <div className="flow-block flow-block--ok">
            <strong>서식1~5 작성이 끝났습니다. 종이·자필서명 0건.</strong>
            <p>신청번호 {appNo}</p>
            <p>
              이제 발급받아야만 하는 서류만 올리면 됩니다. 두배적금은 보완 요청이 없는 사업이라,
              올리는 즉시 적합 여부를 알려 드립니다.
            </p>
          </div>
          <div className="flow__gap" />
          <DocumentUpload applicationId={appId} focusSlot={focusSlot} />
          <div className="flow__actions">
            <button type="button" className="btn" onClick={() => setStage('consent')}>
              이전
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => {
                setFocusSlot('')
                setStage('final')
              }}
            >
              제출 전 최종 확인
            </button>
          </div>
        </>
      )}

      {/* ── [5] 제출 전 최종 확인 ── */}
      {stage === 'final' && appId !== null && (
        <>
          <FinalCheck
            applicationId={appId}
            onGoto={goto}
            onSubmitted={(result) => {
              setSubmitted(result)
              setStage('mypage')
              window.scrollTo({ top: 0 })
            }}
          />
          <div className="flow__actions">
            <button type="button" className="btn" onClick={() => setStage('upload')}>
              이전
            </button>
          </div>
        </>
      )}

      {/* ── [6][7] 제출 완료 · 마이페이지 ── */}
      {stage === 'mypage' && appId !== null && (
        <>
          {submitted && (
            <div className="flow-block flow-block--ok">
              <strong>{submitted.message}</strong>
              <p>신청번호 {submitted.application_no}</p>
              <ol className="flow-steps-list">
                {submitted.next_steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
              <p className="flow-alt">{submitted.notice}</p>
            </div>
          )}
          <div className="flow__gap" />
          <MyPage applicationId={appId} />
        </>
      )}
    </div>
  )
}
