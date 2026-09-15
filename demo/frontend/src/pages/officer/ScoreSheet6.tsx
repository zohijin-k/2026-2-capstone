/**
 * 서식6 심사표 — 담당자 화면 (R8.7).
 *
 * 담당자가 쓰던 **종이 심사표와 시각적으로 같게** 그린다. 배점표 전체를 원본
 * 순서대로 펼쳐 놓고, 자동 계산된 구간에만 배경색을 얹고 그 아래에 근거 문장을
 * 붙인다. 학습 비용이 0이 되고, "자동 채점을 믿어도 되나"라는 저항도 줄어든다.
 *
 * 항목을 클릭하면 좌측 원본이 그 근거 위치로 스크롤된다 (R4.3).
 *
 * 배점 출처: `docs/demo-site-dev-plan.md` 2.4절 (시행지침 서식6 원문 대조 확정본).
 * 신청자 화면과 같은 `FormSheet` 계열 컴포넌트를 쓴다 — 서식은 한 가지 방식으로만
 * 그린다.
 */

import { Cell, FormNote, FormSheet, FormTable, LabelCell } from '../../forms/FormSheet.tsx'
import type { ScoreItemRow, ScoreSheetData } from '../../api.ts'

/** 원본 배점표. 문구와 순서를 시행지침 서식6 그대로 유지한다. */
const SHEET_ROWS: { key: string; label: string; max: number; bands: [string, number][] }[] = [
  {
    key: 'income',
    label: '1. 중위소득(가구소득)',
    max: 40,
    bands: [
      ['130% 이상', 28],
      ['120% 이상 ~ 130% 미만', 31],
      ['110% 이상 ~ 120% 미만', 34],
      ['100% 이상 ~ 110% 미만', 37],
      ['100% 미만', 40],
    ],
  },
  {
    key: 'residence',
    label: '2. 도 거주기간',
    max: 25,
    bands: [
      ['1년 미만', 15],
      ['1년 이상 ~ 2년 미만', 17],
      ['2년 이상 ~ 3년 미만', 19],
      ['3년 이상 ~ 4년 미만', 21],
      ['4년 이상 ~ 5년 미만', 23],
      ['5년 이상', 25],
    ],
  },
  {
    key: 'work',
    label: '3. 근로기간(현 직장)',
    max: 25,
    bands: [
      ['1년 미만', 16],
      ['1년 이상 ~ 2년 미만', 19],
      ['2년 이상 ~ 3년 미만', 22],
      ['3년 이상', 25],
    ],
  },
  {
    key: 'age',
    label: '4. 신청자 연령',
    max: 10,
    bands: [
      ['35세 이상', 7],
      ['30~34세', 8],
      ['25~29세', 9],
      ['24세 이하', 10],
    ],
  },
]

const COLS = [23, 9, 48, 20]

interface Props {
  sheet: ScoreSheetData
  /** 지금 좌측에서 보고 있는 근거 항목. */
  activeKey: string | null
  onSelect: (item: ScoreItemRow) => void
}

export default function ScoreSheet6({ sheet, activeKey, onSelect }: Props) {
  const scored = new Map(sheet.items.map((i) => [i.key, i]))

  return (
    <div className="sheet6">
      <FormSheet
        formNo="서식6"
        title="「전북청년 함께 두배적금」 심사표"
        notices={[
          '○ 거주기간·근로기간은 공고일(‘26. 3. 3.) 기준으로 역산정합니다.',
          '○ 음영 처리된 구간이 제출 서류에서 자동 판정된 결과이며, 아래 줄에 산출 근거를 함께 표기합니다.',
        ]}
      >
        <FormTable cols={COLS}>
          <tr>
            <LabelCell>평가항목</LabelCell>
            <LabelCell>배점</LabelCell>
            <LabelCell>평가기준</LabelCell>
            <LabelCell>점수</LabelCell>
          </tr>

          {SHEET_ROWS.map((row) => {
            const item = scored.get(row.key)
            const active = activeKey === row.key
            return (
              <SheetItem
                key={row.key}
                row={row}
                item={item}
                active={active}
                onSelect={onSelect}
              />
            )
          })}

          <tr className="sheet6__total">
            <LabelCell span={2}>합 계</LabelCell>
            <Cell center>{sheet.max_total}점 만점</Cell>
            <Cell center>
              <strong>{sheet.total}</strong> 점
            </Cell>
          </tr>
        </FormTable>

        <FormNote>
          ※ 동점자 우선순위 ① 가구소득이 적은 자 ② 도 거주기간이 긴 자 ③ 근로기간이 긴 자 ④ 연령이
          낮은 자
        </FormNote>
        {sheet.income_over_limit && (
          <p className="sheet6__over">
            ⚠ 가구 기준 중위소득 {sheet.income_percent}% — 신청 상한 140%를 초과했습니다. 점수와
            무관하게 자격 부적합입니다.
          </p>
        )}
        {sheet.notes.map((note, i) => (
          <FormNote key={i}>{note}</FormNote>
        ))}
      </FormSheet>
    </div>
  )
}

function SheetItem({
  row,
  item,
  active,
  onSelect,
}: {
  row: (typeof SHEET_ROWS)[number]
  item: ScoreItemRow | undefined
  active: boolean
  onSelect: (item: ScoreItemRow) => void
}) {
  const clickable = Boolean(item?.source_document_id)
  const open = () => {
    if (item && clickable) onSelect(item)
  }

  return (
    <>
      {row.bands.map((band, index) => {
        const selected = item?.band === band[0]
        return (
          <tr
            key={band[0]}
            className={[
              'sheet6__band',
              selected ? 'sheet6__band--on' : '',
              active ? 'sheet6__band--active' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            {index === 0 && (
              <>
                <LabelCell rowSpan={row.bands.length}>{row.label}</LabelCell>
                <LabelCell rowSpan={row.bands.length}>{row.max}</LabelCell>
              </>
            )}
            <Cell>{band[0]}</Cell>
            <Cell center>{selected ? <strong>{band[1]}</strong> : band[1]}</Cell>
          </tr>
        )
      })}
      <tr className={active ? 'sheet6__basis sheet6__basis--active' : 'sheet6__basis'}>
        <Cell span={4}>
          {item ? (
            <button
              type="button"
              className="sheet6__basis-btn"
              onClick={open}
              disabled={!clickable}
              title={clickable ? '원본에서 이 근거 위치를 봅니다' : '연결된 원본 서류가 없습니다'}
            >
              <span className="sheet6__basis-text">
                {item.incomplete ? '⚠ ' : '근거 '}
                {item.basis}
              </span>
              <span className="sheet6__basis-meta">
                {item.source_doc ?? '신청서 입력값'}
                {clickable && <span className="sheet6__basis-go">원본 보기 →</span>}
              </span>
            </button>
          ) : (
            <span className="sheet6__basis-text">채점 결과가 없습니다.</span>
          )}
        </Cell>
      </tr>
    </>
  )
}
