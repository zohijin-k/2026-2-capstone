/**
 * 신청자 플로우.
 *
 *   [0] 사업 선택 → 본인인증(데모) → 자가진단 → 신청서 → 동의 → (취업패키지: 지원 항목)
 *   → 서류 업로드(즉시 판정) → 제출 전 최종 확인 → 제출 → 마이페이지
 *
 * 본인인증이 맨 앞에 오는 이유: 업로드 서류가 '이 신청자의 것인지' 대조할 기준이
 * 필요하다. 신청서의 성명·생년월일은 인증 값으로 채워지고 잠긴다.
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

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  createApplication,
  fetchApplication,
  fetchApplicationConsents,
  fetchPrograms,
  fetchStatus,
  fetchSubsidyItems,
  patchApplication,
  postConsents,
  postSelfCheck,
  type ConsentPayload,
  type Identity,
  type Program,
  type SelfCheckResult,
  type SubmitResult,
  type SubsidyState,
} from '../../api.ts'
import DocumentUpload from './DocumentUpload.tsx'
import FinalCheck from './FinalCheck.tsx'
import IdentityCheck from './IdentityCheck.tsx'
import MyPage from './MyPage.tsx'
import ProgramPicker from './ProgramPicker.tsx'
import SubsidyItems from './SubsidyItems.tsx'
import PdfFormsWorkspace, { ApplicantFormsBulkMenu } from '../../forms/PdfFormsWorkspace.tsx'
import { EMPTY_CONSENT, type ConsentValue } from '../../forms/consent-model.ts'
import { CONSENT_OPTIONS } from '../../forms/consent-model.ts'
import { EMPTY_FORM1, type Form1Value } from '../../forms/form1-model.ts'
import { EMPTY_FORM5, SIGN_MODES, type Form5Value, type SignMode } from '../../forms/form5-model.ts'
import type { SelfCheckAnswers } from '../../forms/form2-model.ts'
import './apply-flow.css'

type Stage =
  | 'program'
  | 'identity'
  | 'forms'
  | 'subsidy'
  | 'upload'
  | 'final'
  | 'complete'
  | 'mypage'

export const APPLICANT_SESSION_KEY = 'demo-applicant-page'

function savedPage(): { appId: number; stage: Stage; previous: Stage } | null {
  try {
    const value = JSON.parse(window.sessionStorage.getItem(APPLICANT_SESSION_KEY) ?? 'null') as
      { appId?: unknown; stage?: unknown; previous?: unknown } | null
    const stages: Stage[] = ['identity', 'forms', 'subsidy', 'upload', 'final', 'complete', 'mypage']
    if (!value || !Number.isSafeInteger(value.appId) || Number(value.appId) <= 0 || !stages.includes(value.stage as Stage)) return null
    return {
      appId: Number(value.appId),
      stage: value.stage as Stage,
      previous: stages.includes(value.previous as Stage) ? value.previous as Stage : 'identity',
    }
  } catch {
    return null
  }
}

type Step = { key: 'identity' | 'forms' | 'upload' | 'final'; label: string }
type StepperProgress = { completed: number; total: number }
const APPLY_STEPS: Step[] = [
  { key: 'identity', label: '본인인증' },
  { key: 'forms', label: '서식 작성' },
  { key: 'upload', label: '서류 업로드' },
  { key: 'final', label: '확인 및 제출' },
]

type ConsentType = ConsentPayload['consent_type']

/** 신청서의 성명·생년월일을 본인인증 값으로 덮는다 (서버도 같은 규칙으로 잠근다). */
function lockIdentity(form: Form1Value, identity: Identity | null): Form1Value {
  if (!identity) return form
  const [y, m, d] = identity.birth.split('-')
  return { ...form, name: identity.name, birth: { y, m: String(Number(m)), d: String(Number(d)) } }
}

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
  const [initialPage] = useState(savedPage)
  const [restoring, setRestoring] = useState(initialPage !== null)
  const [program, setProgram] = useState<Program | null>(null)
  const [appId, setAppId] = useState<number | null>(null)
  const [appNo, setAppNo] = useState('')
  const [stage, setStage] = useState<Stage>('program')
  const [stageBeforeMypage, setStageBeforeMypage] = useState<Stage>('identity')
  const [error, setError] = useState('')
  const [identity, setIdentity] = useState<Identity | null>(null)

  const [answers, setAnswers] = useState<SelfCheckAnswers>({})
  const [checkResult, setCheckResult] = useState<SelfCheckResult | null>(null)

  const [form1, setForm1] = useState<Form1Value>(EMPTY_FORM1)

  const [consent, setConsent] = useState<ConsentValue>(EMPTY_CONSENT)
  const [form5, setForm5] = useState<Form5Value>(EMPTY_FORM5)
  const [signMode, setSignMode] = useState<SignMode>('화면에 서명')
  const [paperForms, setPaperForms] = useState<Record<string, boolean>>({})

  const [submitted, setSubmitted] = useState<SubmitResult | null>(null)
  /** 지원 항목이 바뀌면 업로드 화면의 체크리스트를 다시 읽게 하는 키. */
  const [checklistKey, setChecklistKey] = useState(0)
  const [selectedSubsidyTypes, setSelectedSubsidyTypes] = useState(0)
  const [formContinuing, setFormContinuing] = useState(false)
  const [formError, setFormError] = useState('')
  const [formProgress, setFormProgress] = useState<StepperProgress>({ completed: 0, total: 0 })
  const [uploadProgress, setUploadProgress] = useState<StepperProgress>({ completed: 0, total: 0 })
  const saveQueue = useRef<Promise<void>>(Promise.resolve())

  useEffect(() => {
    if (!initialPage) return
    let active = true
    const restore = async () => {
      try {
        const [application, programs, consents, status] = await Promise.all([
          fetchApplication(initialPage.appId),
          fetchPrograms(),
          fetchApplicationConsents(initialPage.appId),
          fetchStatus(initialPage.appId),
        ])
        const picked = programs.find((item) => item.code === application.program_code)
        if (!picked) throw new Error('Program unavailable')
        const subsidy = picked.has_subsidy_items ? await fetchSubsidyItems(initialPage.appId) : null
        if (!active) return
        setProgram(picked)
        setAppId(application.id)
        setAppNo(application.application_no)
        const savedIdentity = application.identity_json
        setIdentity(savedIdentity?.name && savedIdentity.birth ? savedIdentity as Identity : null)
        setForm1({ ...EMPTY_FORM1, ...application.form1_json } as Form1Value)
        setAnswers(application.self_check_json as SelfCheckAnswers)
        setForm5({ ...EMPTY_FORM5, ...application.form5_json } as Form5Value)
        setSignMode(application.form5_json.signatureScanUploaded ? SIGN_MODES[1] : SIGN_MODES[0])
        setSelectedSubsidyTypes(subsidy?.selections.length ?? 0)
        const consentValue = (type: string) => {
          const item = consents.find((row) => row.consent_type === type)
          return item ? CONSENT_OPTIONS[item.agreed ? 0 : 1] : ''
        }
        setConsent({
          privacy: consentValue('privacy'),
          uniqueId: consentValue('unique_id'),
          thirdParty: consentValue('third_party'),
        })
        if (status.status !== 'draft') {
          setSubmitted({
            application_no: status.application_no,
            submitted_at: status.submitted_at,
            status: status.status,
            message: '신청이 완료되었습니다.',
            next_steps: [],
            first_come: status.first_come,
            supplement: status.supplement,
            subsidy: status.subsidy,
            notice: status.result_notice,
          })
        }
        setStage(initialPage.stage === 'complete' && status.status === 'draft' ? 'final' : initialPage.stage)
        setStageBeforeMypage(initialPage.previous)
      } catch {
        if (!active) return
        window.sessionStorage.removeItem(APPLICANT_SESSION_KEY)
      } finally {
        if (active) setRestoring(false)
      }
    }
    void restore()
    return () => { active = false }
  }, [initialPage])

  useEffect(() => {
    if (restoring) return
    if (appId === null || stage === 'program') {
      window.sessionStorage.removeItem(APPLICANT_SESSION_KEY)
    } else {
      window.sessionStorage.setItem(APPLICANT_SESSION_KEY, JSON.stringify({ appId, stage, previous: stageBeforeMypage }))
    }
  }, [appId, stage, stageBeforeMypage, restoring])

  const reportFormProgress = useCallback((completed: number, total: number) => {
    setFormProgress({ completed, total })
  }, [])
  const reportUploadProgress = useCallback((completed: number, total: number) => {
    setUploadProgress({ completed, total })
  }, [])

  /** 사업을 고른 시점에 신청 건을 만든다. 이후 단계마다 부분 저장한다. */
  const pickProgram = (picked: Program) => {
    setProgram(picked)
    setAnswers({})
    setCheckResult(null)
    setIdentity(null)
    setSelectedSubsidyTypes(0)
    setForm1(EMPTY_FORM1)
    setFormProgress({ completed: 0, total: 0 })
    setUploadProgress({ completed: 0, total: 0 })
    setSubmitted(null)
    createApplication(picked.code)
      .then((a) => {
        setAppId(a.id)
        setAppNo(a.application_no)
        setStage('identity')
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }

  const save = (body: { form1?: unknown; self_check?: unknown; form5?: unknown }): Promise<void> => {
    if (appId === null) return Promise.resolve()
    const next = saveQueue.current.catch(() => undefined).then(() => patchApplication(appId, body)).then(() => undefined)
    saveQueue.current = next.catch(() => undefined)
    return saveQueue.current
  }

  const continueFromForms = async () => {
    if (appId === null || program === null) return
    setFormContinuing(true)
    setFormError('')
    try {
      const payload = Object.fromEntries(Object.entries(answers).filter(([, v]) => v)) as Record<string, string>
      const result = await postSelfCheck(appId, payload)
      setCheckResult(result)
      if (!result.eligible) return
      if (!consentReady) {
        setFormError('필수 동의와 서명을 모두 마쳐 주세요.')
        return
      }
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
        signature_data_url: signMode === '화면에 서명' ? form5.signature : undefined,
        signature_kind: signMode === '화면에 서명' ? 'electronic' : 'handwritten',
      },
    }
    // 어느 동의를 받아야 하는지는 사업이 정한다. 취업패키지에는 서식5가 없다.
      await postConsents(
      appId,
      types.filter((t) => !(t === 'admin_info' && paperForms['서식5'])).map((t) => values[t]),
    )
    if (types.includes('admin_info')) save({ form5 })
    setStage(program.has_subsidy_items ? 'subsidy' : 'upload')
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : String(e))
    } finally {
      setFormContinuing(false)
    }
  }

  /** 최종 확인의 수정 링크는 이미 도달한 단계로만 돌아가게 한다. */
  const jumpTo = (next: Stage) => {
    if (next === stage) return
    if (next === 'identity' && identity !== null) return
    setStage(next)
    window.scrollTo({ top: 0 })
  }

  if (restoring) return <p className="flow">신청 화면을 불러오는 중입니다...</p>
  if (error) return <p className="flow-error">{error}</p>

  if (program === null || stage === 'program') {
    return (
      <div className="flow">
        <header className="flow__head flow__head--solo">
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

  const consentTypes = consentTypesOf(program)
  const needsAdminConsent = consentTypes.includes('admin_info')
  const needsUniqueId = consentTypes.includes('unique_id')

  const consentReady =
    consent.privacy === '동의함' &&
    (!needsUniqueId || consent.uniqueId === '동의함') &&
    consent.thirdParty === '동의함' &&
    (!needsAdminConsent || paperForms['서식5'] ||
      (form5.agree === '동의함' &&
        (signMode === '화면에 서명' ? !!form5.signature : form5.signatureScanUploaded)))

  const submittedDone = submitted !== null
  const uploadComplete = uploadProgress.total > 0 && uploadProgress.completed >= uploadProgress.total
  const viewedStage = stage === 'mypage' && !submittedDone ? stageBeforeMypage : stage
  const currentIndex = viewedStage === 'identity' ? 0
    : viewedStage === 'forms' || viewedStage === 'subsidy' ? 1
      : viewedStage === 'upload' ? 2 : 3

  const openMyPage = () => {
    if (stage !== 'mypage') setStageBeforeMypage(stage)
    setStage('mypage')
    window.scrollTo({ top: 0 })
  }

  const stepProgress = (index: number): number => {
    if (submittedDone) return 1
    if (index === 2) {
      if (uploadProgress.total === 0) return 0
      return Math.max(0, Math.min(1, uploadProgress.completed / uploadProgress.total))
    }
    if (index < currentIndex) return 1
    if (index > currentIndex) return 0
    const current = index === 1 ? formProgress : index === 2 ? uploadProgress : null
    return current && current.total > 0 ? Math.max(0, Math.min(1, current.completed / current.total)) : 0
  }

  const stepStatus = (index: number): string => {
    if (submittedDone) return index === 3 ? '접수 완료' : '완료'
    if (index === 2) {
      return uploadProgress.total > 0 ? `${uploadProgress.completed} / ${uploadProgress.total}` : '대기'
    }
    if (index < currentIndex) return '완료'
    if (index > currentIndex) return '대기'
    if (index === 1 && formProgress.total > 0) return `${formProgress.completed} / ${formProgress.total} 작성`
    return ''
  }

  const stepperNavigate = (index: number) => {
    const previouslyReachedUpload = index === 2 && uploadProgress.total > 0
    if (submittedDone || stage === 'mypage' || index === 0) return
    if (index >= currentIndex && !previouslyReachedUpload) return
    setStage(index === 1 ? 'forms' : 'upload')
    window.scrollTo({ top: 0 })
  }

  /** 신청서 저장. 본인인증을 마쳤으면 성명·생년월일은 인증 값으로 고정된다. */
  const onForm1 = (next: Form1Value) => {
    const locked = lockIdentity(next, identity)
    setForm1(locked)
    save({ form1: locked })
  }

  return (
    <div className={stage === 'upload' ? 'flow flow--fluid' : 'flow'}>
      <header className="flow__head">
        <div>
          <h1>{program.name} 신청</h1>
          <p className="flow__sub">작성 내용은 단계마다 자동 저장됩니다</p>
        </div>
        <div className="flow__head-meta">
          <dl className="flow__meta">
            <div>
              <dt>신청번호</dt>
              <dd>{appNo || '발급 중…'}</dd>
            </div>
            {program.is_first_come && (
              <div>
                <dt>접수 방식</dt>
                <dd>선착순</dd>
              </div>
            )}
          </dl>
          <button type="button" className="flow__mypage" onClick={openMyPage} disabled={stage === 'mypage'}>마이페이지</button>
        </div>
      </header>
      <ol className="flow__stages" aria-label="신청 단계">
        {APPLY_STEPS.map(({ key, label }, i) => {
          const complete = submittedDone || (i === 2 ? uploadComplete : i < currentIndex)
          const current = i === currentIndex
          const canNavigate = !submittedDone && stage !== 'mypage' && i !== 0 &&
            (i < currentIndex || (i === 2 && uploadProgress.total > 0))
          const status = stepStatus(i)
          return (
          <li
            key={key}
            className={complete ? 'is-complete' : current ? 'is-current' : 'is-waiting'}
          >
            <button
              type="button"
              aria-current={current ? 'step' : undefined}
              aria-disabled={!canNavigate}
              title={i === 0 && identity ? '본인인증은 완료되었습니다' : undefined}
              onClick={() => stepperNavigate(i)}
            >
              <span className="flow__stage-no" aria-hidden="true">
                {complete ? <span className="flow__stage-check" aria-hidden="true">✓</span> : i + 1}
              </span>
              <span className="flow__stage-label">{label}</span>
              <span className="flow__stage-status">{status}</span>
            </button>
            {i < APPLY_STEPS.length - 1 && (
              <span className="flow__stage-connector" aria-hidden="true">
                <span style={{ width: `${stepProgress(i) * 100}%` }} />
              </span>
            )}
          </li>
          )
        })}
      </ol>

      {/* ── 본인인증 (데모) ── */}
      {stage === 'identity' && appId !== null && (
        <IdentityCheck
          appId={appId}
          identity={identity}
          onVerified={(verified, mobile) => {
            setIdentity(verified)
            const locked = lockIdentity({ ...form1, mobile }, verified)
            setForm1(locked)
            save({ form1: locked })
            setStage('forms')
            window.scrollTo({ top: 0 })
          }}
          onNext={() => setStage('forms')}
        />
      )}

      {/* ── [1] 자가진단 ── */}
      {stage === 'forms' && appId !== null && (
        <PdfFormsWorkspace
          applicationId={appId}
          program={program}
          identity={identity}
          form1={form1}
          answers={answers}
          consent={consent}
          form5={form5}
          signMode={signMode}
          checkResult={checkResult}
          onForm1={onForm1}
          onAnswers={(next) => { setAnswers(next); setCheckResult(null); save({ self_check: next }) }}
          onConsent={setConsent}
          onForm5={(next) => { setForm5(next); save({ form5: next }) }}
          onSignMode={setSignMode}
          onFlush={async () => {
            if (appId === null) return
            await saveQueue.current
            await patchApplication(appId, { form1, self_check: answers, form5 })
            const values: Record<ConsentType, ConsentPayload> = {
              privacy: { consent_type: 'privacy', agreed: consent.privacy === '동의함' },
              unique_id: { consent_type: 'unique_id', agreed: consent.uniqueId === '동의함' },
              third_party: { consent_type: 'third_party', agreed: consent.thirdParty === '동의함' },
              admin_info: {
                consent_type: 'admin_info',
                agreed: form5.agree === '동의함',
                signature_data_url: signMode === '화면에 서명' ? form5.signature : undefined,
                signature_kind: signMode === '화면에 서명' ? 'electronic' : 'handwritten',
              },
            }
            const selectedConsent: Record<ConsentType, string> = {
              privacy: consent.privacy,
              unique_id: consent.uniqueId,
              third_party: consent.thirdParty,
              admin_info: form5.agree,
            }
            await postConsents(appId, consentTypesOf(program)
              .filter((type) => !(type === 'admin_info' && paperForms['서식5']))
              .filter((type) => selectedConsent[type] === '동의함' || selectedConsent[type] === '동의하지 않음')
              .map((type) => values[type]))
          }}
          onChangedSubsidy={(state) => { setSelectedSubsidyTypes(state.selections.length); setChecklistKey((key) => key + 1) }}
          onPaperFormsChange={setPaperForms}
          onContinue={() => void continueFromForms()}
          continuing={formContinuing}
          error={formError}
          readOnly={!!submitted}
          onProgress={reportFormProgress}
        />
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
            onChanged={(state: SubsidyState) => {
              setSelectedSubsidyTypes(state.selections.length)
              setChecklistKey((k) => k + 1)
            }}
          />
          <div className="flow__actions">
            <button type="button" className="btn" onClick={() => setStage('forms')}>
              이전
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={selectedSubsidyTypes === 0}
              onClick={() => setStage('upload')}
            >
              서류 업로드로
            </button>
          </div>
          {selectedSubsidyTypes === 0 && (
            <p className="flow__validation" role="alert">지원받을 항목을 하나 이상 고르세요.</p>
          )}
        </>
      )}

      {/* ── [5] 서류 업로드 ── */}
      {stage === 'upload' && appId !== null && (
        <>
          {identity === null && (
            <div className="flow-block flow-block--warn">
              <strong>본인인증 전입니다.</strong>
              <p>
                지금 올리는 서류는 본인 명의인지 대조하지 않습니다.{' '}
                <button type="button" className="btn btn--small" onClick={() => jumpTo('identity')}>
                  본인인증 하러 가기
                </button>
              </p>
            </div>
          )}
          <DocumentUpload key={checklistKey} applicationId={appId} onProgress={reportUploadProgress} />
          <div className="flow__actions">
            <button
              type="button"
              className="btn"
              onClick={() => setStage(program.has_subsidy_items ? 'subsidy' : 'forms')}
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
              setStage('complete')
              window.scrollTo({ top: 0 })
            }}
            onBack={() => jumpTo('upload')}
            onGoto={jumpTo}
          />
        </>
      )}

      {/* ── 제출 완료 ── */}
      {stage === 'complete' && submitted && appId !== null && (
        <>
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
                <strong>{submitted.subsidy.total_granted.toLocaleString('ko-KR')}원</strong>
              </p>
            )}
            <ol className="flow-steps-list">
              {submitted.next_steps.map((s) => <li key={s}>{s}</li>)}
            </ol>
            <p className="flow-alt">{submitted.notice}</p>
            <ApplicantFormsBulkMenu applicationId={appId} refreshKey={1} />
            <button type="button" className="btn btn--primary" onClick={openMyPage}>마이페이지</button>
          </div>
        </>
      )}

      {stage === 'mypage' && appId !== null && (
        <>
          <div className="flow__mypage-return">
            <button type="button" className="btn" onClick={() => setStage(stageBeforeMypage)}>신청 화면으로 돌아가기</button>
          </div>
          <MyPage applicationId={appId} />
        </>
      )}
    </div>
  )
}
