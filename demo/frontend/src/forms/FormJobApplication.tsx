/**
 * 청년 취업지원패키지 신청서.
 *
 * ⚠️ 사업계획서에는 이 신청서의 **서식 원본이 없다.** 신청서류 표에 "① 청년
 * 취업지원패키지 신청서(개인정보 수집이용제공 동의서)"라고만 적혀 있다. 그래서
 * 항목 구성은 데모가 정한 것이고, 화면에 `(데모 추정치)` 라벨을 단다. TF에서
 * 실제 서식을 받으면 서식1처럼 원본 표 구조로 교체한다.
 *
 * 묻지 않는 것이 이 서식의 핵심이다. 두배적금 서식1과 달리 거주기간·가구원수·
 * 근로사항·저축목적이 없다 — 자격요건이 나이와 거주지뿐이고 소득요건이 없기
 * 때문이다. 통장 사본은 계좌번호 입력으로 갈음한다(R1.4).
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

/** 열 너비(%). 원본 서식이 없으므로 라벨열 / 입력열 2분할의 단순 구조다. */
const COLS = [18, 32, 18, 32]

interface Props {
  value: Form1Value
  onChange: (next: Form1Value) => void
}

export default function FormJobApplication({ value: v, onChange }: Props) {
  const set =
    <K extends keyof Form1Value>(key: K) =>
    (next: Form1Value[K]) =>
      onChange({ ...v, [key]: next })

  return (
    <FormSheet
      formNo="신청서"
      title="2026년 전북청년 취업지원패키지 신청서"
      notices={[
        '○ 빈칸에 기입하거나, □에 ✓(체크)표 하세요',
        '○ 지원금은 신청자 월별 취합 후 본인 명의 계좌로 지급됩니다.',
        '※ 사업계획서에 서식 원본이 없어 데모가 구성한 양식입니다. (데모 추정치)',
      ]}
    >
      <FormTable cols={COLS}>
        <FormBand span={4}>Ⅰ. 신청인</FormBand>

        <tr>
          <LabelCell>성명</LabelCell>
          <Cell>
            <Text ariaLabel="신청자 이름" value={v.name} onChange={set('name')} />
          </Cell>
          <LabelCell>생년월일</LabelCell>
          <Cell>
            <DateTriple value={v.birth} onChange={set('birth')} ariaPrefix="생년월일" />
          </Cell>
        </tr>

        <tr>
          <LabelCell>성별</LabelCell>
          <Cell>
            <Checks
              name="gender"
              cols="flow"
              options={['남', '여']}
              value={v.gender}
              onChange={set('gender')}
            />
          </Cell>
          <LabelCell>연락처(휴대전화)</LabelCell>
          <Cell>
            <Text ariaLabel="연락처" value={v.mobile} onChange={set('mobile')} />
          </Cell>
        </tr>

        <tr>
          <LabelCell>주소</LabelCell>
          <Cell span={3}>
            <Text ariaLabel="주소" value={v.address} onChange={set('address')} />
            <FormNote>
              ※ 주민등록상 주소 기준. 전북특별자치도 내 거주 청년만 신청할 수 있습니다.
            </FormNote>
          </Cell>
        </tr>

        <tr>
          <LabelCell>전자우편</LabelCell>
          <Cell span={3}>
            <Text ariaLabel="전자우편" value={v.email} onChange={set('email')} />
          </Cell>
        </tr>

        <FormBand span={4}>Ⅱ. 지원금을 받을 계좌</FormBand>

        <tr>
          <LabelCell>은행명</LabelCell>
          <Cell>
            <Text ariaLabel="은행명" value={v.bankName} onChange={set('bankName')} />
          </Cell>
          <LabelCell>예금주</LabelCell>
          <Cell>
            <Text
              ariaLabel="예금주"
              value={v.accountHolder}
              onChange={set('accountHolder')}
            />
          </Cell>
        </tr>

        <tr>
          <LabelCell>계좌번호</LabelCell>
          <Cell span={3}>
            <Text ariaLabel="계좌번호" value={v.accountNo} onChange={set('accountNo')} />
            <FormNote>
              ※ 반드시 <strong>본인 명의</strong> 계좌여야 합니다. 계좌번호를 입력하면
              통장 사본을 따로 올리지 않아도 됩니다.
            </FormNote>
          </Cell>
        </tr>
      </FormTable>
    </FormSheet>
  )
}
