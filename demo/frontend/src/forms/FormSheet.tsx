/**
 * 서식 원형 재현용 기본 컴포넌트 (PC 전용 고정 레이아웃).
 *
 * 맞추는 것 셋:
 *   1. 표 구조   — 열 경계를 원본 PDF의 실제 선 좌표에서 가져온다
 *   2. 항목 순서 — 서식에 적힌 순서 그대로 (재배열 금지)
 *   3. 문구      — 항목명과 각주(※)를 원문 그대로
 *
 * 설계 근거: .trellis/tasks/09-16-demo-site/design.md 6-A절
 */

import type { ReactNode } from 'react'

import type { YMD } from './ymd.ts'

import './form-sheet.css'

interface FormSheetProps {
  formNo: string
  title: string
  /** 표제 아래 안내문. 서식 원문의 "○ …" 줄을 그대로 넣는다. */
  notices?: ReactNode[]
  children: ReactNode
}

export function FormSheet({ formNo, title, notices, children }: FormSheetProps) {
  return (
    <div className="form-sheet-scroll">
      <div className="form-sheet">
        <div className="form-sheet__head">
          <div className="form-sheet__no">{formNo}</div>
          <h2 className="form-sheet__title">{title}</h2>
        </div>
        {notices && notices.length > 0 && (
          <div className="form-sheet__notices">
            {notices.map((n, i) => (
              <p key={i}>{n}</p>
            ))}
          </div>
        )}
        {children}
      </div>
    </div>
  )
}

/**
 * 본표. `cols`는 각 열의 너비 비율(%)이며 원본 PDF 선 좌표에서 뽑은 값이다.
 * 행마다 분할이 다르므로 각 셀이 colSpan으로 묶어 쓴다.
 */
export function FormTable({ cols, children }: { cols: number[]; children: ReactNode }) {
  return (
    <table className="form-table">
      <colgroup>
        {cols.map((w, i) => (
          <col key={i} style={{ width: `${w}%` }} />
        ))}
      </colgroup>
      <tbody>{children}</tbody>
    </table>
  )
}

/** 절 제목 띠 (Ⅰ. 기본정보). */
export function FormBand({ span, children }: { span: number; children: ReactNode }) {
  return (
    <tr>
      <td className="fc-band" colSpan={span}>
        {children}
      </td>
    </tr>
  )
}

interface CellProps {
  span?: number
  rowSpan?: number
  center?: boolean
  children?: ReactNode
}

/** 라벨 셀 (항목명). */
export function LabelCell({ span = 1, rowSpan, children }: CellProps) {
  return (
    <td className="fc-label" colSpan={span} rowSpan={rowSpan}>
      {children}
    </td>
  )
}

/** 입력·내용 셀. */
export function Cell({ span = 1, rowSpan, center, children }: CellProps) {
  return (
    <td className={center ? 'fc-center' : undefined} colSpan={span} rowSpan={rowSpan}>
      {children}
    </td>
  )
}

/** 서식 원문의 ※ 각주. 요약하지 말고 그대로 넣을 것. 원본처럼 옅은 형광 배경. */
export function FormNote({ children }: { children: ReactNode }) {
  return (
    <p className="form-note">
      <span>{children}</span>
    </p>
  )
}

interface FileAttachProps {
  /** 첨부해야 할 서류 이름. 셀 안에서 무엇을 올리는 칸인지 바로 읽히게 한다. */
  label: string
  fileName: string
  onChange: (fileName: string) => void
  /** 기본값은 관공서 제출 서류에서 실제로 받는 형식이다. */
  accept?: string
}

/**
 * 서식 안에서 서류 한 건을 첨부하는 칸.
 *
 * 데모는 파일을 서버로 올리지 않고 **파일명만** 들고 있는다 — 첨부 여부와 어떤
 * 파일을 골랐는지가 보이면 시연에 필요한 것은 다 보인다. 서식5의 자필서명 스캔
 * 업로드와 같은 방식이다.
 */
export function FileAttach({
  label,
  fileName,
  onChange,
  accept = '.pdf,.jpg,.jpeg,.png',
}: FileAttachProps) {
  return (
    <div className="form-file">
      <span className="form-file__label">{label}</span>
      <input
        type="file"
        accept={accept}
        aria-label={`${label} 첨부`}
        onChange={(e) => onChange(e.target.files?.[0]?.name ?? '')}
      />
      {fileName && (
        <>
          <span className="form-file__name">{fileName}</span>
          <button
            type="button"
            className="form-file__clear"
            onClick={() => onChange('')}
          >
            지우기
          </button>
        </>
      )}
    </div>
  )
}

interface TextProps {
  value: string
  onChange: (v: string) => void
  ariaLabel: string
  placeholder?: string
  type?: 'text' | 'tel' | 'email'
}

export function Text({ value, onChange, ariaLabel, placeholder, type = 'text' }: TextProps) {
  return (
    <input
      className="form-input"
      type={type}
      value={value}
      placeholder={placeholder}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

/**
 * 년·월·일을 각각 따로 받는다.
 * 서식의 칸이 원래 그렇게 나뉘어 있고, 브라우저 기본 date 피커를 쓰면 칸 안에
 * 이질적인 위젯이 들어가 서식 모양이 깨진다.
 */
export function DateTriple({
  value,
  onChange,
  ariaPrefix,
}: {
  value: YMD
  onChange: (v: YMD) => void
  ariaPrefix: string
}) {
  const set = (k: keyof YMD, max: number) => (raw: string) => {
    const digits = raw.replace(/\D/g, '').slice(0, k === 'y' ? 4 : 2)
    if (digits && Number(digits) > max) return
    onChange({ ...value, [k]: digits })
  }
  return (
    <span className="form-date">
      <input
        className="form-date__y"
        inputMode="numeric"
        aria-label={`${ariaPrefix} 년`}
        value={value.y}
        onChange={(e) => set('y', 9999)(e.target.value)}
      />
      <span className="form-date__unit">년</span>
      <input
        className="form-date__m"
        inputMode="numeric"
        aria-label={`${ariaPrefix} 월`}
        value={value.m}
        onChange={(e) => set('m', 12)(e.target.value)}
      />
      <span className="form-date__unit">월</span>
      <input
        className="form-date__d"
        inputMode="numeric"
        aria-label={`${ariaPrefix} 일`}
        value={value.d}
        onChange={(e) => set('d', 31)(e.target.value)}
      />
      <span className="form-date__unit">일</span>
    </span>
  )
}

/**
 * 라디오 한 칸. **이미 고른 것을 다시 누르면 선택이 풀린다.**
 *
 * 브라우저 기본 라디오는 한 번 고르면 같은 그룹의 다른 값으로 바꿀 수만 있고
 * 비울 수는 없다. 그런데 이 서식들의 문항은 "예/아니오", "동의함/동의하지 않음"
 * 같은 2지선다가 대부분이라 잘못 누르기 쉽고, 되돌릴 방법이 없으면 신청자는
 * 틀린 답을 그대로 둔 채 다음 단계로 떠밀린다. 자가진단은 "아니오" 하나로
 * 자격 없음이 뜨는 화면이라 더 그렇다.
 *
 * 이미 선택된 라디오에는 브라우저가 change 이벤트를 보내지 않으므로 click으로
 * 처리한다. `onChange`는 controlled input 경고를 막기 위한 빈 핸들러다.
 */
export function Radio({
  name,
  checked,
  onPick,
  disabled,
}: {
  name: string
  checked: boolean
  /** 누른 뒤의 선택 상태. 이미 선택돼 있던 칸을 누르면 `false`가 온다. */
  onPick: (next: boolean) => void
  disabled?: boolean
}) {
  return (
    <input
      type="radio"
      name={name}
      checked={checked}
      disabled={disabled}
      onChange={noop}
      onClick={() => onPick(!checked)}
    />
  )
}

function noop() {}

interface ChecksProps {
  name: string
  options: readonly string[]
  value: string | string[]
  onChange?: (next: string) => void
  multiple?: boolean
  /** 한 줄에 몇 개를 놓을지. 원본 PDF의 줄바꿈 위치와 같게 맞춘다. */
  cols?: 1 | 2 | 3 | 5 | 'flow'
  /** 값이 다른 입력에서 자동으로 정해지는 칸. 읽기전용으로 두고 근거를 붙인다. */
  derived?: boolean
  basis?: string
}

export function Checks({
  name,
  options,
  value,
  onChange,
  multiple = false,
  cols = 'flow',
  derived = false,
  basis,
}: ChecksProps) {
  const selected = Array.isArray(value) ? value : [value]
  return (
    <>
      <div className={`form-checks form-checks--${cols}`}>
        {options.map((opt) => (
          <label
            key={opt}
            className={derived ? 'form-check form-check--derived' : 'form-check'}
          >
            {multiple ? (
              <input
                type="checkbox"
                name={name}
                checked={selected.includes(opt)}
                readOnly={derived}
                disabled={derived}
                onChange={derived ? undefined : () => onChange?.(opt)}
              />
            ) : (
              <Radio
                name={name}
                checked={selected.includes(opt)}
                disabled={derived}
                onPick={(next) => onChange?.(next ? opt : '')}
              />
            )}
            <span>{opt}</span>
          </label>
        ))}
        {derived && <span className="form-derived-tag">자동</span>}
      </div>
      {basis && <p className="form-basis">{basis}</p>}
    </>
  )
}
