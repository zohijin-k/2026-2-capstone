/**
 * 신청자 플로우.
 *
 *   [0] 사업 선택 → [1] 자가진단 → [2] 신청서 → [3] 동의 → (취업패키지: 지원 항목)
 *   → [4] 서류 업로드(즉시 판정) → [5] 제출 전 최종 확인 → [6] 제출 → [7] 마이페이지
 *
 * 두배적금은 서식1의 절(Ⅰ~Ⅳ) 경계를 그대로 스텝 경계로 쓴다. 스텝은 서식을
 * 재구성한 것이 아니라 스크롤 위치를 나눈 것에 가깝고, "서식 전체 보기"를 켜면
 * 한 장으로 펼쳐진다.
 *
 * **사업 분기는 전부 `Program` 값으로 한다.** 이 파일 어디에도 `code === '...'`
 * 비교를 두지 않는다. 자가진단 문항 수, 신청서 서식, 동의 항목, 지원 항목 단계의
 * 유무가 전부 서버의 사업 설정에서 나온다.
 *
 */

import { useState } from 'react'

import {
  createApplication,
  patchApplication,
  postConsents,
  postSelfCheck,
  type ConsentPayload,
  type Program,
  type SelfCheckResult,
  type SubmitResult,
} from '../../api.ts'
import DocumentUpload from './DocumentUpload.tsx'
import FinalCheck from './FinalCheck.tsx'
import MyPage from './MyPage.tsx'
import ProgramPicker from './ProgramPicker.tsx'
import SubsidyItems from './SubsidyItems.tsx'
import Form1Application from '../../forms/Form1Application.tsx'
import Form2SelfCheck from '../../forms/Form2SelfCheck.tsx'
import FormJobApplication from '../../forms/FormJobApplication.tsx'
import { Form3PrivacyConsent, Form4ThirdPartyConsent } from '../../forms/Form34Consent.tsx'
import Form5AdminInfoConsent from '../../forms/Form5AdminInfoConsent.tsx'
import { EMPTY_CONSENT, type ConsentValue } from '../../forms/consent-model.ts'
import { EMPTY_FORM1, type Form1Value } from '../../forms/form1-model.ts'
import { EMPTY_FORM5, type Form5Value, type SignMode } from '../../forms/form5-model.ts'
import {
  JOB_PACKAGE_SELF_CHECK_FOOTER,
  JOB_PACKAGE_SELF_CHECK_ITEMS,
  SELF_CHECK_ITEMS,
  allAnswered,
  type SelfCheckAnswers,
} from '../../forms/form2-model.ts'
import './apply-flow.css'

type Stage =
  | 'program'
  | 'selfCheck'
  | 'form1'
  | 'consent'
  | 'subsidy'
  | 'upload'
  | 'final'
  | 'mypage'

/** 서식1의 절 구조를 그대로 스텝 경계로 쓴다. */
const FORM1_STEPS = [
  { key: 'top' as const, label: '저축목적·유사사업' },
  { key: 'basic' as const, label: 'Ⅰ. 기본정보' },
  { key: 'tail' as const, label: 'Ⅱ~Ⅳ. 납입·계좌·기타' },
]

type ConsentType = ConsentPayload['consent_type']

/**
 * 받아야 하는 동의 종류.
 *
 * 두배적금은 서식3(수집·이용 + 고유식별정보) · 서식4(제3자 제공) · 서식5(행정정보
 * 공동이용)까지 4건이다. 취업패키지 사업계획서의 공통서류는 "① 신청서(개인정보
 * 수집이용제공 동의서)" 한 줄뿐이라 수집·이용과 제공 2건이다. 서버의
 * `ProgramConfig.consent_types`와 같은 값을 써야 제출이 막히지 않는다.
 */
function consentTypesOf(program: Program): ConsentType[] {
  return program.has_subsidy_items
    ? ['privacy', 'third_party']
    : ['privacy', 'unique_id', 'third_party', 'admin_info']
}

export default function ApplyFlow() {
  const [program, setProgram] = useState<Program | null>(null)
  const [appId, setAppId] = useState<number | null>(null)
  const [appNo, setAppNo] = useState('')
  const [stage, setStage] = useState<Stage>('program')
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
  /** 지원 항목이 바뀌면 업로드 화면의 체크리스트를 다시 읽게 하는 키. */
  const [checklistKey, setChecklistKey] = useState(0)

  /** 사업을 고른 시점에 신청 건을 만든다. 이후 단계마다 부분 저장한다. */
  const pickProgram = (picked: Program) => {
    setProgram(picked)
    setAnswers({})
    setCheckResult(null)
    createApplication(picked.code)
      .then((a) => {
        setAppId(a.id)
        setAppNo(a.application_no)
        setStage('selfCheck')
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }

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
    if (appId === null || program === null) return
    const types = consentTypesOf(program)
    const values: Record<ConsentType, ConsentPayload> = {
      privacy: { consent_type: 'privacy', agreed: consent.privacy === '동의함' },
      unique_id: { consent_type: 'unique_id', agreed: consent.uniqueId === '동의함' },
      third_party: {
        consent_type: 'third_party',
        agreed: consent.thirdParty === '동의함',
      },
      admin_info: {
        consent_type: 'admin_info',
        agreed: form5.agree === '동의함',
        signature_data_url: signMode === '전자서명' ? form5.signature : undefined,
        signature_kind: signMode === '전자서명' ? 'electronic' : 'handwritten',
      },
    }
    // 어느 동의를 받아야 하는지는 사업이 정한다. 취업패키지에는 서식5가 없다.
    await postConsents(
      appId,
      types.map((t) => values[t]),
    )
    if (types.includes('admin_info')) save({ form5 })
    setStage(program.has_subsidy_items ? 'subsidy' : 'upload')
  }

  /**
   * 상단 단계 표시를 눌러 바로 그 단계로 간다.
   *
   * 시연에서는 앞 단계를 다 통과해야만 다음 화면을 볼 수 있으면 곤란하다.
   * 신청 건은 사업을 고른 시점에 이미 만들어져 있으므로, 어느 단계로 건너뛰든
   * 그 화면이 필요로 하는 `appId`는 준비돼 있다. 각 화면의 저장·판정은 그대로
   * 동작하고, 최종 제출 시점의 검증(최종 확인)이 미비를 잡아 준다.
   */
  const jumpTo = (next: Stage) => {
    if (next === stage) return
    setStage(next)
    window.scrollTo({ top: 0 })
  }

  if (error) return <p className="flow-error">{error}</p>

  if (program === null || stage === 'program') {
    return (
      <div className="flow">
        <header className="flow__head">
          <div>
            <h1>사업 선택</h1>
            <p className="flow__sub">
              전북특별자치도 청년 지원사업 2종 — 고른 사업의 기준으로 이후 화면이 구성됩니다
            </p>
          </div>
        </header>
        <ProgramPicker onPick={pickProgram} />
      </div>
    )
  }

  const selfCheckItems = program.has_subsidy_items
    ? JOB_PACKAGE_SELF_CHECK_ITEMS
    : SELF_CHECK_ITEMS
  const consentTypes = consentTypesOf(program)
  const needsAdminConsent = consentTypes.includes('admin_info')
  const needsUniqueId = consentTypes.includes('unique_id')

  const consentReady =
    consent.privacy === '동의함' &&
    (!needsUniqueId || consent.uniqueId === '동의함') &&
    consent.thirdParty === '동의함' &&
    (!needsAdminConsent ||
      (form5.agree === '동의함' &&
        (signMode === '전자서명' ? !!form5.signature : !!form5.handwrittenFileName)))

  const stages: [Stage, string][] = [
    ['selfCheck', '1. 자가진단'],
    ['form1', '2. 신청서 작성'],
    ['consent', '3. 동의'],
    ...(program.has_subsidy_items
      ? ([['subsidy', '4. 지원 항목']] as [Stage, string][])
      : []),
    ['upload', `${program.has_subsidy_items ? 5 : 4}. 서류 업로드`],
    ['final', `${program.has_subsidy_items ? 6 : 5}. 최종 확인`],
    ['mypage', `${program.has_subsidy_items ? 7 : 6}. 마이페이지`],
  ]

  return (
    <div className={stage === 'upload' ? 'flow flow--fluid' : 'flow'}>
      <header className="flow__head">
        <div>
          <h1>{program.name} 신청</h1>
          <p className="flow__sub">
            신청번호 {appNo || '발급 중…'} · 작성 내용은 단계마다 자동 저장됩니다
            {program.is_first_come && ' · 선착순 접수'}
          </p>
        </div>
        <ol className="flow__stages">
          {stages.map(([key, label]) => (
            <li key={key} className={stage === key ? 'is-current' : undefined}>
              <button
                type="button"
                aria-current={stage === key ? 'step' : undefined}
                onClick={() => jumpTo(key)}
              >
                {label}
              </button>
            </li>
          ))}
        </ol>
      </header>

      {/* ── [1] 자가진단 ── */}
      {stage === 'selfCheck' && (
        <>
          <Form2SelfCheck
            answers={answers}
            items={selfCheckItems}
            formNo={program.has_subsidy_items ? '자가진단' : '서식1'}
            title={
              program.has_subsidy_items
                ? '신청자격 자가진단 (나이·거주지)'
                : '신청자격 자가진단 및 필수사항 확인·동의서'
            }
            notices={
              program.has_subsidy_items
                ? [
                    `아래 2개 항목을 확인해 주세요. 『${program.name}』의 자격요건은 나이와 거주지입니다.`,
                    '소득 요건은 없으며, 근로 여부와 무관하게 신청할 수 있습니다.',
                  ]
                : undefined
            }
            footer={program.has_subsidy_items ? JOB_PACKAGE_SELF_CHECK_FOOTER : undefined}
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
            <button type="button" className="btn" onClick={() => setStage('program')}>
              사업 다시 고르기
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={!allAnswered(answers, selfCheckItems)}
              onClick={runSelfCheck}
            >
              {allAnswered(answers, selfCheckItems)
                ? '자가진단 결과 확인'
                : `${selfCheckItems.length}문항에 모두 답해 주세요`}
            </button>
          </div>
        </>
      )}

      {/* ── [2] 신청서 ── */}
      {stage === 'form1' && (
        <>
          {program.has_subsidy_items ? (
            <FormJobApplication
              value={form1}
              onChange={(next) => {
                setForm1(next)
                save({ form1: next })
              }}
            />
          ) : (
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
                  서식2 전체 보기
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
            </>
          )}

          <div className="flow__actions">
            <button
              type="button"
              className="btn"
              onClick={() =>
                program.has_subsidy_items || step === 0
                  ? setStage('selfCheck')
                  : setStep(step - 1)
              }
            >
              이전
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() =>
                program.has_subsidy_items || step === FORM1_STEPS.length - 1 || wholeSheet
                  ? setStage('consent')
                  : setStep(step + 1)
              }
            >
              {program.has_subsidy_items ||
              step === FORM1_STEPS.length - 1 ||
              wholeSheet
                ? '동의 단계로'
                : '다음'}
            </button>
          </div>
        </>
      )}

      {/* ── [3] 동의 ── */}
      {stage === 'consent' && (
        <>
          <Form3PrivacyConsent value={consent} onChange={setConsent} />
          <div className="flow__gap" />
          <Form4ThirdPartyConsent value={consent} onChange={setConsent} />
          {needsAdminConsent && (
            <>
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
            </>
          )}
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
              {consentReady ? '동의 완료' : '모든 동의 항목이 필요합니다'}
            </button>
          </div>
        </>
      )}

      {/* ── [4] 지원 항목 (취업지원패키지) ── */}
      {stage === 'subsidy' && appId !== null && (
        <>
          <div className="flow-block flow-block--ok">
            <strong>신청서와 동의서 작성이 끝났습니다. 종이·자필서명 0건.</strong>
            <p>신청번호 {appNo}</p>
            <p>
              이제 지원받을 항목을 고르세요. 항목은 여러 개를 함께 신청할 수 있고,
              고른 항목에 따라 올려야 할 서류가 정해집니다.
            </p>
          </div>
          <div className="flow__gap" />
          <SubsidyItems
            applicationId={appId}
            onChanged={() => setChecklistKey((k) => k + 1)}
          />
          <div className="flow__actions">
            <button type="button" className="btn" onClick={() => setStage('consent')}>
              이전
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setStage('upload')}
            >
              서류 업로드로
            </button>
          </div>
        </>
      )}

      {/* ── [5] 서류 업로드 ── */}
      {stage === 'upload' && appId !== null && (
        <>
          <DocumentUpload key={checklistKey} applicationId={appId} />
          <div className="flow__actions">
            <button
              type="button"
              className="btn"
              onClick={() => setStage(program.has_subsidy_items ? 'subsidy' : 'consent')}
            >
              이전
            </button>
            <button type="button" className="btn btn--primary" onClick={() => setStage('final')}>
              제출 전 최종 확인
            </button>
          </div>
        </>
      )}

      {/* ── [6] 제출 전 최종 확인 ── */}
      {stage === 'final' && appId !== null && (
        <>
          <FinalCheck
            applicationId={appId}
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

      {/* ── [7] 제출 완료 · 마이페이지 ── */}
      {stage === 'mypage' && appId !== null && (
        <>
          {submitted && (
            <div className="flow-block flow-block--ok">
              <strong>{submitted.message}</strong>
              <p>신청번호 {submitted.application_no}</p>
              {submitted.first_come && (
                <p className="flow-queue">
                  접수 순번 <strong>{submitted.first_come.position}번</strong>
                  {submitted.first_come.quota !== null &&
                    ` / 총 지원규모 ${submitted.first_come.quota.toLocaleString('ko-KR')}건`}
                </p>
              )}
              {submitted.subsidy && submitted.subsidy.lines.length > 0 && (
                <p className="flow-queue">
                  신청하신 항목의 지급 예정액{' '}
                  <strong>
                    {submitted.subsidy.total_granted.toLocaleString('ko-KR')}원
                  </strong>
                </p>
              )}
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
