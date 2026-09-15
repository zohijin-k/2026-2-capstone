/**
 * 서식2 신청자격 자가진단 및 필수사항 확인·동의서.
 *
 * 원본은 `점검 내용 | 확인,동의` 2열 표다. 오른쪽 칸의 "예, 아니오"를 라디오로
 * 바꾼 것 외에는 구조·문구가 시행지침 p.25 그대로다.
 *
 * 이 화면이 신청서 작성보다 **앞에** 온다. 부적격자를 진입 전에 걸러내는 것이
 * 콜센터 문의(자격요건 38%)를 줄이는 지점이기 때문이다.
 */

import { Cell, FormSheet, FormTable, LabelCell } from './FormSheet.tsx'
import {
  SELF_CHECK_FOOTER,
  SELF_CHECK_ITEMS,
  type SelfCheckAnswers,
  type SelfCheckItem,
} from './form2-model.ts'

const COLS = [86, 14]

/** `**강조**` 를 <strong> 으로. 원문의 굵은 글씨 위치를 그대로 살린다. */
function emphasize(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      <span key={i}>{part}</span>
    ),
  )
}

interface Props {
  answers: SelfCheckAnswers
  onChange: (next: SelfCheckAnswers) => void
  /** 문항 목록. 사업이 바뀌면 문항 수가 바뀐다 (두배적금 8 / 취업패키지 2). */
  items?: SelfCheckItem[]
  formNo?: string
  title?: string
  notices?: string[]
  footer?: string[]
}

export default function Form2SelfCheck({
  answers,
  onChange,
  items = SELF_CHECK_ITEMS,
  formNo = '서식2',
  title = '신청자격 자가진단 및 필수사항 확인·동의서',
  notices = [
    '신청서 작성 전 아래 내용을 잘 읽으시고, 필수 사항 동의에 모두 체크해 주시기 바랍니다.',
    '모두 확인, 동의하는 경우만 『전북청년 함께 두배적금』가입 신청이 가능합니다.',
  ],
  footer = SELF_CHECK_FOOTER,
}: Props) {
  const pick = (no: number, v: '예' | '아니오') => onChange({ ...answers, [no]: v })

  return (
    <FormSheet formNo={formNo} title={title} notices={notices}>
      <FormTable cols={COLS}>
        <tr>
          <LabelCell>점 검 내 용</LabelCell>
          <LabelCell>확인,동의</LabelCell>
        </tr>

        {items.map((item) => (
          <tr key={item.no}>
            <Cell>
              <div>
                {item.no}. {emphasize(item.question)}
              </div>
              {item.note && (
                <p className="form-note">
                  <span>{item.note}</span>
                </p>
              )}
              {item.sublist && (
                <div className="form-subbox">
                  <ul className={item.sublistTwoCol ? 'form-subbox--2col' : undefined}>
                    {item.sublist.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Cell>
            <Cell center>
              <div className="form-checks form-checks--1" style={{ justifyItems: 'center' }}>
                {(['예', '아니오'] as const).map((opt) => (
                  <label key={opt} className="form-check">
                    <input
                      type="radio"
                      name={`self-check-${item.no}`}
                      checked={answers[item.no] === opt}
                      onChange={() => pick(item.no, opt)}
                    />
                    <span>{opt}</span>
                  </label>
                ))}
              </div>
            </Cell>
          </tr>
        ))}
      </FormTable>

      <div style={{ fontSize: 12.5, marginTop: 10, lineHeight: 1.6 }}>
        {footer.map((line) => (
          <p key={line} style={{ margin: '2px 0' }}>
            {line}
          </p>
        ))}
      </div>
    </FormSheet>
  )
}
