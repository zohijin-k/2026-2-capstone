/**
 * 서식3 개인정보 수집 및 이용 동의서 / 서식4 개인(신용)정보 제3자 제공 동의서.
 *
 * 고지문은 시행지침 p.25~26 원문 그대로다. 법정 고지문이라 한 글자도 줄이지
 * 않는다. 바뀌는 것은 마지막 "□ 동의함 / □ 동의하지 않음" 뿐이다.
 */

import type { ReactNode } from 'react'

import { Cell, FormSheet, FormTable, Radio } from './FormSheet.tsx'
import { CONSENT_OPTIONS, type ConsentValue } from './consent-model.ts'

const COLS = [100]

function AgreeRow({
  name,
  question,
  value,
  onChange,
}: {
  name: string
  question: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <tr>
      <Cell>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-around',
            gap: 16,
          }}
        >
          <span>{question}</span>
          <span style={{ display: 'flex', gap: 28 }}>
            {CONSENT_OPTIONS.map((opt) => (
              <label key={opt} className="form-check">
                <Radio
                  name={name}
                  checked={value === opt}
                  onPick={(next) => onChange(next ? opt : '')}
                />
                <span>{opt}</span>
              </label>
            ))}
          </span>
        </div>
      </Cell>
    </tr>
  )
}

function Body({ children }: { children: ReactNode }) {
  return (
    <tr>
      <Cell>{children}</Cell>
    </tr>
  )
}

/* ────────────────────────── 서식3 ────────────────────────── */

export function Form3PrivacyConsent({
  value,
  onChange,
}: {
  value: ConsentValue
  onChange: (v: ConsentValue) => void
}) {
  return (
    <FormSheet formNo="서식3" title="개인정보 수집 및 이용 동의서">
      <FormTable cols={COLS}>
        <tr>
          <Cell center>
            <strong>【 개인정보 수집 및 이용 동의서 】</strong>
          </Cell>
        </tr>
        <Body>
          「개인정보보호법」제15조(개인정보의 수집·이용)에 의거하여 개인정보를 수집합니다.
        </Body>
        <Body>
          <p style={{ margin: '4px 0' }}>
            ❑ 전북청년 함께 두배적금 사업의 대상자 선정 및 지급을 목적으로 개인정보를 수집하기
            위하여 개인정보 보호법에 따라 귀하의 동의를 받고자 합니다.
          </p>
          <p style={{ margin: '10px 0 4px' }}>❑ 수집·이용하는 개인정보의 항목</p>
          <p style={{ margin: '0 0 4px', paddingLeft: 14 }}>
            ○ 성명, 주민등록번호, 주소(이력포함), 직업, 전화번호, 계좌번호, 병역사항,
            근로사항(근무처, 고용기간, 근로형태, 급여 등), 건강보험료, 건강보험자격 및
            자격득실(이력포함), 4대보험 가입내역, 원천징수 내역, 사업자등록, 농어업인등록,
            차상위·기초생활수급자 여부, 가구원 수, 가구원 성명, 신청인과의 관계, 가구원
            주민등록번호, 건강보험료 고지내역, 신용정보 조회
          </p>
          <p style={{ margin: '10px 0 4px' }}>
            ❑ 수집이용 기관 : 전북특별자치도, 시군, 읍면동 행정복지센터, 청년허브센터, 유사
            자산형성사업 수행기관
          </p>
          <p style={{ margin: '10px 0 4px' }}>❑ 개인정보 수집·이용 목적</p>
          <p style={{ margin: '0 0 4px', paddingLeft: 14 }}>
            ○ 전북청년 함께 두배적금 사업의 대상자 선정 및 지급 업무처리를 위하여 개인정보를
            수집합니다.
          </p>
          <p style={{ margin: '10px 0 4px' }}>❑ 개인정보 보유 기간</p>
          <p style={{ margin: '0 0 4px', paddingLeft: 14 }}>
            ○ 상기 개인정보는 해당 사업의 지원 종료 후 중복지급 및 분쟁 발생 시 증빙 목적을
            위해 5년 동안 보유됩니다.
          </p>
          <p style={{ margin: '10px 0 4px' }}>❑ 개인정보 수집·이용 동의 거부의 권리</p>
          <p style={{ margin: 0 }}>
            전북청년 함께 두배적금 사업의 대상자 선정 및 지급 업무처리를 위하여 기본정보 이외의
            추가정보를 수집하지 않으며, 미 동의시 전북청년 함께 두배적금 사업의 서비스가 일부
            제한될 수 있습니다.
          </p>
        </Body>
        <AgreeRow
          name="consent-privacy"
          question="개인정보의 수집 및 이용에 동의하십니까?"
          value={value.privacy}
          onChange={(v) => onChange({ ...value, privacy: v })}
        />
        <Body>
          <u>개인정보 수집 및 이용 동의서(고유식별정보)</u>
        </Body>
        <Body>
          <p style={{ margin: '4px 0' }}>
            ❑ 전북청년 함께 두배적금 사업의 대상자 선정 및 지급 등의 업무처리를 위하여 다음과
            같은 목적으로 고유식별정보(주민등록번호)를 수집하고 있습니다.
          </p>
          <p style={{ margin: '0 0 4px', paddingLeft: 14 }}>
            ○ 대상자 선정 및 지급업무 처리(신청–접수–조사–결정–지급 등)
          </p>
        </Body>
        <AgreeRow
          name="consent-unique-id"
          question="고유식별정보 수집 이용에 동의하십니까?"
          value={value.uniqueId}
          onChange={(v) => onChange({ ...value, uniqueId: v })}
        />
        <Body>
          <p style={{ margin: 0, lineHeight: 1.7 }}>
            개인정보 보호법에 명기된 법률상의 개인정보처리자가 준수하여야 할 개인정보보호 규정을
            준수하고, 관련법령에 의거하여 대상자의 권익보호에 최선을 다하고 있으며 허가된 이용
            목적 외에는 사용하지 않을 것을 약속드리며, 인적사항 및 가족관계 확인에 관한 정보,
            소득·재산·노동능력·취업상태에 관한 정보, 사회보장급여의 수혜이력에 관한 정보, 그
            밖에 지원 대상자를 선정하기 위하여 필요한 정보 등 전북청년 함께 두배적금 사업
            대상자를 선정하기 위하여 필요한 정보를 관계기관에 요청하거나 관련 정보통신망을 통해
            조회함에 동의합니다.
          </p>
          <div className="form-sheet__closing" style={{ paddingBottom: 0 }}>
            <p>2026 년　　　월　　　일</p>
            <p>
              <strong>전북특별자치도지사 · ○○ 시장 · 군수 귀하</strong>
            </p>
          </div>
        </Body>
      </FormTable>
    </FormSheet>
  )
}

/* ────────────────────────── 서식4 ────────────────────────── */

export function Form4ThirdPartyConsent({
  value,
  onChange,
}: {
  value: ConsentValue
  onChange: (v: ConsentValue) => void
}) {
  return (
    <FormSheet formNo="서식4" title="개인(신용)정보 제3자 제공 동의서">
      <FormTable cols={COLS}>
        <tr>
          <Cell center>
            <strong>개인(신용)정보 제3자 제공 동의서【전북청년 함께 두배적금】</strong>
          </Cell>
        </tr>
        <Body>
          전북특별자치도청과 농협은행의 적금상품 가입 및 계좌 관리를 위하여 본인의 개인(신용)
          정보를 제3자(농협은행)에 제공하고자 하는 경우「신용정보의 이용 및 보호에 관한 법률」,
          「개인정보보호법」등 관계 법령에 따라 본인의 동의가 필요합니다.
        </Body>
        <Body>
          <p style={{ margin: '4px 0' }}>❑ 제공받는 자 : NH농협은행</p>
          <p style={{ margin: '4px 0' }}>
            ❑ 제공받는 자의 이용 목적 : 전북청년 함께 두배적금 상품 가입 및 계좌 관리
          </p>
          <p style={{ margin: '10px 0 4px' }}>
            ❑ 개인정보 보유 및 이용기간 : 거래 종료일로부터 5년까지 보유·이용
          </p>
          <p style={{ margin: '0 0 4px', paddingLeft: 14 }}>
            ○ 위 보유 기간에서의 거래 종료일이란 ‘계약상 일련의 과정 및 서비스가 종료한 날 중
            가장 나중에 도래한 사유를 기준으로 판단한 날’을 말합니다.
          </p>
          <p style={{ margin: '0 0 4px', paddingLeft: 14 }}>
            ○ 거래 종료일 후에는 제공받는 자의 금융사고, 조사, 분쟁 해결, 민원 처리, 법령상
            의무이행을 위한 목적으로만 보유·이용됩니다.
          </p>
          <p style={{ margin: '10px 0 4px' }}>❑ 개인(신용)정보 제공 동의 거부의 권리 및 불이익</p>
          <p style={{ margin: '0 0 4px', paddingLeft: 14 }}>
            ○ 귀하는 동의를 거부하실 수 있습니다. 다만, 위 개인(신용)정보 제공에 관한 동의는
            “거래 계약의 체결 및 이행을 위한” 필수적 사항이므로, 위 사항에 동의하셔야만 거래관계의
            설정 및 유지가 가능합니다.
          </p>
          <p style={{ margin: '10px 0 4px' }}>
            ❑ 개인(신용)정보 제공 항목 : 성명, 생년월일, 연락처, 월 납입금액
          </p>
        </Body>
        <AgreeRow
          name="consent-third-party"
          question="위 개인(신용) 정보 제공에 동의하십니까?"
          value={value.thirdParty}
          onChange={(v) => onChange({ ...value, thirdParty: v })}
        />
        <Body>
          <div className="form-sheet__closing" style={{ padding: '10px 0 0' }}>
            <p>2026 년　　　월　　　일</p>
            <p>
              <strong>전북특별자치도지사 · ○○ 시장 · 군수 귀하</strong>
            </p>
          </div>
        </Body>
      </FormTable>
    </FormSheet>
  )
}
