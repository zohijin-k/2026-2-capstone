/**
 * 올린 파일 크게 보기 — 업로드한 서류나 서명 파일을 눌렀을 때 뜨는 팝업.
 *
 * PDF는 쪽을 세로로 이어 그리고(pdf.js), 이미지는 그대로 띄운다.
 * 확대·축소만 둔다. 저장 버튼은 두지 않는다 (원본 저장 경로를 만들지 않는 원칙).
 */

import { useState } from 'react'

import Modal from './Modal.tsx'
import PdfPages from './PdfPages.tsx'
import './file-preview.css'

/** 쪽 폭(px). 팝업 본문 폭에 맞춘 기본값에서 한 단계씩 키우고 줄인다. */
const WIDTHS = [480, 600, 720, 860, 1040, 1240]
const DEFAULT_STEP = 2

export type PreviewKind = 'pdf' | 'image'

interface Props {
  url: string
  name: string
  kind: PreviewKind
  onClose: () => void
}

export default function FilePreview({ url, name, kind, onClose }: Props) {
  const [step, setStep] = useState(DEFAULT_STEP)
  const [pages, setPages] = useState(0)
  const width = WIDTHS[step]
  const percent = Math.round((width / WIDTHS[DEFAULT_STEP]) * 100)

  return (
    <Modal title={name} onClose={onClose} variant="viewer">
      <div className="fpreview">
        <div className="fpreview__bar">
          <span className="fpreview__meta">
            {kind === 'pdf' ? 'PDF' : '이미지'}
            {kind === 'pdf' && pages > 0 && ` · ${pages}쪽`}
          </span>
          <div className="fpreview__zoom" role="group" aria-label="확대·축소">
            <button
              type="button"
              onClick={() => setStep((s) => s - 1)}
              disabled={step === 0}
              aria-label="축소"
            >
              −
            </button>
            <button
              type="button"
              className="fpreview__percent"
              onClick={() => setStep(DEFAULT_STEP)}
              title="원래 크기로"
            >
              {percent}%
            </button>
            <button
              type="button"
              onClick={() => setStep((s) => s + 1)}
              disabled={step === WIDTHS.length - 1}
              aria-label="확대"
            >
              +
            </button>
          </div>
        </div>
        <div className="fpreview__stage">
          {kind === 'pdf' ? (
            <PdfPages url={url} width={width} onPageCount={setPages} />
          ) : (
            <img className="fpreview__img" src={url} alt={name} style={{ width }} />
          )}
        </div>
      </div>
    </Modal>
  )
}
