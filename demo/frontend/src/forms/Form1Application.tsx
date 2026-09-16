/**
 * 서식1 「전북청년 함께 두배적금」참여 신청서.
 *
 * 항목 순서·문구·각주·체크박스 줄바꿈 위치는 시행지침 p.23~24 원문 그대로다.
 * 열 너비(COLS)는 원본 PDF의 실제 표 선 좌표에서 뽑았다. 임의로 다듬거나
 * 재배열하지 말 것 — 담당자가 종이 서식과 1:1로 대조한다.
 *
 * ※ 서식 번호가 두 문서에서 다르다. 화면 표기는 공고문 번호('서식2')를 쓰고,
 *   코드·PDF 내보내기 식별자는 시행지침 번호('서식1')를 그대로 유지한다.
 */

import {
  Cell,
  Checks,
  DateTriple,
  FormBand,
  FormNote,
  FormSheet,
  FormTable,
  LabelCell,
  Text,
} from './FormSheet.tsx'
import type { Form1Value } from './form1-model.ts'
import {
  ADMIN_WORK_FORMS,
  FORM1_AGREEMENTS,
  HOUSEHOLD_SIZES,
  HOUSEHOLD_TYPES,
  REFERRAL_PATHS,
  SAVING_PURPOSES,
  WORKPLACE_REGIONS,
  WORK_TYPES,
} from './form1-model.ts'
import { RESIDENCE_BUCKETS, WORK_BUCKETS, deriveResidence, deriveWork } from '../lib/period.ts'
import { ymdToISO } from './ymd.ts'

/** 표 열 너비(%) — 시행지침 서식1의 실제 선 좌표(표 폭 340.2pt) 기준. */
const COLS = [6.34, 4.43, 6.55, 11.08, 3.22, 1.01, 12.69, 4.23, 8.16, 8.86, 1.21, 14.7, 1.21, 1.71, 14.6]

interface Props {
  value: Form1Value
  onChange: (next: Form1Value) => void
  /** 위저드에서 특정 구획만 보여줄 때 사용. 생략하면 전체가 한 장으로 펼쳐진다. */
  only?: 'top' | 'basic' | 'tail'
}

export default function Form1Application({ value: v, onChange, only }: Props) {
  const set =
    <K extends keyof Form1Value>(key: K) =>
    (next: Form1Value[K]) =>
      onChange({ ...v, [key]: next })

  const residence = deriveResidence(ymdToISO(v.transferIn))
  const work = deriveWork(ymdToISO(v.employedAt))

  const toggleReferral = (opt: string) =>
    onChange({
      ...v,
      referralPaths: v.referralPaths.includes(opt)
        ? v.referralPaths.filter((x) => x !== opt)
        : [...v.referralPaths, opt],
    })

  const show = (part: 'top' | 'basic' | 'tail') => !only || only === part

  return (
    <FormSheet
      formNo="서식2"
      title="「전북청년 함께 두배적금」참여 신청서"
      notices={[
        '○ 빈칸에 기입하거나, □에 ✓(체크)표 하세요',
        '○ 기재사항의 허위·누락·착오로 인한 불이익은 신청자가 부담하므로 정확하게 작성해 주시기 바랍니다.',
        '※ 관련 문의 : 신청자의 주민등록상 주소지 관할 읍면동 행정복지센터 및 콜센터(1660-2040)',
      ]}
    >
      <FormTable cols={COLS}>
        {/* ── 서식 상단 ── */}
        {show('top') && (
          <>
            <tr>
              <LabelCell span={2}>
                저축
                <br />
                목적
              </LabelCell>
              <Cell span={11}>
                <div style={{ marginBottom: 4 }}>다음 중 1항목 선택</div>
                <Checks
                  name="savingPurpose"
                  cols={3}
                  options={SAVING_PURPOSES}
                  value={v.savingPurpose}
                  onChange={set('savingPurpose')}
                />
              </Cell>
              <LabelCell span={2}>
                본인이
                <br />
                선택체크
              </LabelCell>
            </tr>
            <tr>
              <LabelCell span={5}>유사 자산형성사업 참여 여부</LabelCell>
              <Cell span={10}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Checks
                    name="priorJoined"
                    cols="flow"
                    options={['미참여', '참여']}
                    value={v.priorJoined}
                    onChange={set('priorJoined')}
                  />
                  <span style={{ display: 'flex', alignItems: 'baseline', gap: 4, flex: 1 }}>
                    (사업명 :
                    <span style={{ flex: 1 }}>
                      <Text
                        ariaLabel="유사 자산형성사업 사업명"
                        value={v.priorName}
                        onChange={set('priorName')}
                      />
                    </span>
                    , 기간 :
                    <span style={{ flex: 1 }}>
                      <Text
                        ariaLabel="유사 자산형성사업 기간"
                        value={v.priorPeriod}
                        onChange={set('priorPeriod')}
                      />
                    </span>
                    , 수령액 :
                    <span style={{ flex: 1 }}>
                      <Text
                        ariaLabel="유사 자산형성사업 수령액"
                        value={v.priorAmount}
                        onChange={set('priorAmount')}
                      />
                    </span>
                    )
                  </span>
                </div>
              </Cell>
            </tr>
          </>
        )}

        {/* ── Ⅰ. 기본정보 ── */}
        {show('basic') && (
          <>
            <FormBand span={15}>Ⅰ. 기본정보</FormBand>

            <tr>
              <LabelCell rowSpan={5}>
                인적
                <br />
                사항
              </LabelCell>
              <LabelCell span={2}>신청자 이름</LabelCell>
              <Cell span={3}>
                <Text ariaLabel="신청자 이름" value={v.name} onChange={set('name')} />
              </Cell>
              <LabelCell span={2}>생년월일</LabelCell>
              <Cell span={2}>
                <DateTriple ariaPrefix="생년월일" value={v.birth} onChange={set('birth')} />
              </Cell>
              <LabelCell span={4}>성 별</LabelCell>
              <Cell>
                <Checks
                  name="gender"
                  cols="flow"
                  options={['남', '여']}
                  value={v.gender}
                  onChange={set('gender')}
                />
              </Cell>
            </tr>

            <tr>
              <LabelCell span={2}>주 소</LabelCell>
              <Cell span={12}>
                <Text ariaLabel="주소" value={v.address} onChange={set('address')} />
              </Cell>
            </tr>

            <tr>
              <LabelCell span={2}>연 락 처</LabelCell>
              <LabelCell>휴대폰</LabelCell>
              <Cell span={5}>
                <Text ariaLabel="휴대폰" type="tel" value={v.mobile} onChange={set('mobile')} />
              </Cell>
              <LabelCell span={2}>이메일</LabelCell>
              <Cell span={4}>
                <Text ariaLabel="이메일" type="email" value={v.email} onChange={set('email')} />
              </Cell>
            </tr>

            <tr>
              <LabelCell span={2}>
                비상연락망
                <br />
                (본인 외)
              </LabelCell>
              <LabelCell>이 름</LabelCell>
              <Cell span={3}>
                <Text ariaLabel="비상연락망 이름" value={v.ecName} onChange={set('ecName')} />
              </Cell>
              <LabelCell span={2}>관 계</LabelCell>
              <Cell span={2}>
                <Text
                  ariaLabel="비상연락망 관계"
                  value={v.ecRelation}
                  onChange={set('ecRelation')}
                />
              </Cell>
              <LabelCell>연락처</LabelCell>
              <Cell span={3}>
                <Text
                  ariaLabel="비상연락망 연락처"
                  type="tel"
                  value={v.ecContact}
                  onChange={set('ecContact')}
                />
              </Cell>
            </tr>

            <tr>
              <LabelCell span={2}>
                전북특별
                <br />
                자치도
                <br />
                거주기간
              </LabelCell>
              <Cell span={12}>
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}
                >
                  <span>최종 전입일</span>
                  <DateTriple
                    ariaPrefix="전북특별자치도 최종 전입일"
                    value={v.transferIn}
                    onChange={set('transferIn')}
                  />
                </div>
                <Checks
                  name="residencePeriod"
                  cols={3}
                  options={RESIDENCE_BUCKETS}
                  value={residence.bucket ?? ''}
                  derived
                  basis={residence.basis}
                />
                <FormNote>
                  ※ 전북특별자치도 최종전입일로부터 공고일(‘26. 3. 3.)까지 기간
                </FormNote>
              </Cell>
            </tr>

            <tr>
              <LabelCell rowSpan={2}>
                가구
                <br />및
                <br />
                소득
              </LabelCell>
              <LabelCell span={2}>가구 특성</LabelCell>
              <Cell span={12}>
                <Checks
                  name="householdType"
                  cols={2}
                  options={HOUSEHOLD_TYPES}
                  value={v.householdType}
                  onChange={set('householdType')}
                />
                <FormNote>※ 기초생활, 법정차상위계층가구 신청 제외대상</FormNote>
              </Cell>
            </tr>

            <tr>
              <LabelCell span={2}>
                가구원 수
                <br />
                (신청자
                <br />
                포함)
              </LabelCell>
              <Cell span={12}>
                <Checks
                  name="householdSize"
                  cols={5}
                  options={HOUSEHOLD_SIZES}
                  value={v.householdSize}
                  onChange={set('householdSize')}
                />
                <FormNote>※ 건강보험 자격확인서상 가구원수를 기재</FormNote>
              </Cell>
            </tr>

            <tr>
              <LabelCell rowSpan={3}>
                근로
                <br />
                사항
              </LabelCell>
              <LabelCell span={2}>근로유형</LabelCell>
              <Cell span={12}>
                <Checks
                  name="workType"
                  cols={2}
                  options={WORK_TYPES}
                  value={v.workType}
                  onChange={set('workType')}
                />
              </Cell>
            </tr>

            <tr>
              <LabelCell span={2}>
                현직장
                <br />
                근로기간
              </LabelCell>
              <Cell span={12}>
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}
                >
                  <span>현직장 취업일</span>
                  <DateTriple
                    ariaPrefix="현직장 취업일"
                    value={v.employedAt}
                    onChange={set('employedAt')}
                  />
                </div>
                <Checks
                  name="workPeriod"
                  cols={2}
                  options={WORK_BUCKETS}
                  value={work.bucket ?? ''}
                  derived
                  basis={work.basis}
                />
                <FormNote>
                  ※ 현재 재직중인 직장 취업일부터 공고일(‘26. 3. 3.)까지 기간
                </FormNote>
              </Cell>
            </tr>

            <tr>
              <LabelCell span={2}>근 무 처</LabelCell>
              <Cell span={12}>
                <Checks
                  name="workplaceRegion"
                  cols={2}
                  options={WORKPLACE_REGIONS}
                  value={v.workplaceRegion}
                  onChange={set('workplaceRegion')}
                />
                <div style={{ marginTop: 4 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                    <span style={{ whiteSpace: 'nowrap' }}>· 근무처 명 :</span>
                    <Text
                      ariaLabel="근무처 명"
                      value={v.workplaceName}
                      onChange={set('workplaceName')}
                    />
                  </div>
                  <div>· 근로형태(행정기관 노동자인 경우만 기재) :</div>
                  <div style={{ paddingLeft: 12 }}>
                    <Checks
                      name="adminWorkForm"
                      cols={2}
                      options={ADMIN_WORK_FORMS}
                      value={v.adminWorkForm}
                      onChange={set('adminWorkForm')}
                    />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                    <span style={{ whiteSpace: 'nowrap' }}>· 근무처 주소 :</span>
                    <Text
                      ariaLabel="근무처 주소"
                      value={v.workplaceAddress}
                      onChange={set('workplaceAddress')}
                    />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                    <span style={{ whiteSpace: 'nowrap' }}>· 근무처 연락처 :</span>
                    <Text
                      ariaLabel="근무처 연락처"
                      type="tel"
                      value={v.workplaceContact}
                      onChange={set('workplaceContact')}
                    />
                  </div>
                </div>
                <FormNote>※ 공고일 현재 재직 중인 경우에만 해당 직장에 관하여 기재</FormNote>
              </Cell>
            </tr>
          </>
        )}

        {/* ── Ⅱ · Ⅲ · Ⅳ ── */}
        {show('tail') && (
          <>
            <tr>
              <LabelCell span={3}>Ⅱ. 납입금액</LabelCell>
              <Cell span={12}>
                <Checks
                  name="deposit"
                  cols="flow"
                  options={['월 10만원']}
                  value="월 10만원"
                  derived
                />
              </Cell>
            </tr>

            <tr>
              <LabelCell span={3}>
                Ⅲ. 입금 받을
                <br />
                계좌
              </LabelCell>
              <Cell span={12}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  (은행명 :
                  <span style={{ width: 90 }}>
                    <Text ariaLabel="은행명" value={v.bankName} onChange={set('bankName')} />
                  </span>
                  / 계좌번호 :
                  <span style={{ flex: 1 }}>
                    <Text ariaLabel="계좌번호" value={v.accountNo} onChange={set('accountNo')} />
                  </span>
                  / 예금주 :
                  <span style={{ width: 80 }}>
                    <Text
                      ariaLabel="예금주"
                      value={v.accountHolder}
                      onChange={set('accountHolder')}
                    />
                  </span>
                  )
                </div>
                <FormNote>
                  ※ 적립금 중복납입 등으로 인한 환급금 발생시 입금 받을 계좌(본인명의)를 기재
                </FormNote>
                <FormNote>
                  ※ 중도해지사유가 발생했음에도 불구하고 신청 등을 거부하는 경우 지자체 직권으로
                  해지 후 계좌입금 처리
                </FormNote>
              </Cell>
            </tr>

            <tr>
              <LabelCell span={3}>Ⅳ. 기타사항</LabelCell>
              <Cell span={12}>
                <div>
                  「전북청년 함께 두배적금」을 알게 된 경로
                  <span style={{ background: 'var(--note-hl)' }}>(복수 항목 선택 가능)</span>
                </div>
                <Checks
                  name="referralPaths"
                  cols="flow"
                  options={REFERRAL_PATHS}
                  value={v.referralPaths}
                  onChange={toggleReferral}
                  multiple
                />
              </Cell>
            </tr>
          </>
        )}
      </FormTable>

      {show('tail') && (
        <>
          <ol className="form-sheet__agreements">
            {FORM1_AGREEMENTS.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ol>
          <div className="form-sheet__closing">
            <p>위와 같이 전북특별자치도「전북청년 함께 두배적금」참여를 신청합니다.</p>
            <p>2026. . .</p>
            <p>
              <strong>전북특별자치도지사, ○○시장·군수 귀하</strong>
            </p>
          </div>
        </>
      )}
    </FormSheet>
  )
}
