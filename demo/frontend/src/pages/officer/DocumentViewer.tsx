/**
 * 원본 뷰어 — 분할 심사 뷰의 좌측 55% (R4.1/R4.2/R4.3).
 *
 * 이 컴포넌트의 금칙은 하나다: **원본을 로컬에 저장하는 경로를 만들지 않는다.**
 * pdf.js가 `/api/files/{id}`(항상 `inline`)를 그대로 읽어 캔버스에 그린다. 저장
 * 버튼도, blob 링크도 없다. 담당자가 심사 1건을 처리하는 동안 파일이 개인 PC로
 * 내려가는 일이 없어야 보관·파기 책임이 옮겨가지 않는다.
 *
 * bbox 하이라이트는 판독값 좌표를 화면 좌표로 옮겨 얹는다. 좌표계는 PyMuPDF와
 * 같은 **좌상단 원점 PDF 포인트**이므로 y를 뒤집지 않는다. 회전은 오버레이에서
 * 같이 돌린다 — 원본을 돌려놓고 근거를 클릭해도 자리가 맞아야 한다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

import type { BBox, OfficerDocument } from '../../api.ts'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

type Rotation = 0 | 90 | 180 | 270

const ZOOM_STEPS = [0.6, 0.8, 1, 1.25, 1.5, 2, 2.5, 3]

interface Props {
  doc: OfficerDocument
  /** 심사표 항목 클릭이 채우는 하이라이트 위치. */
  highlight: BBox | null
  /** 하이라이트 옆에 띄울 설명 (어느 항목의 근거인지). */
  highlightLabel?: string
}

interface Box {
  left: number
  top: number
  width: number
  height: number
}

/** 좌상단 원점 좌표 → 회전·배율이 적용된 화면 좌표. */
function place(
  bbox: BBox,
  pageWidth: number,
  pageHeight: number,
  scale: number,
  rotation: Rotation,
): Box {
  const w = (bbox.x1 - bbox.x0) * scale
  const h = (bbox.y1 - bbox.y0) * scale
  switch (rotation) {
    case 90:
      return { left: (pageHeight - bbox.y1) * scale, top: bbox.x0 * scale, width: h, height: w }
    case 180:
      return {
        left: (pageWidth - bbox.x1) * scale,
        top: (pageHeight - bbox.y1) * scale,
        width: w,
        height: h,
      }
    case 270:
      return { left: bbox.y0 * scale, top: (pageWidth - bbox.x1) * scale, width: h, height: w }
    default:
      return { left: bbox.x0 * scale, top: bbox.y0 * scale, width: w, height: h }
  }
}

export default function DocumentViewer({ doc, highlight, highlightLabel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const markRef = useRef<HTMLDivElement>(null)
  const pdfRef = useRef<pdfjs.PDFDocumentProxy | null>(null)

  const [pageCount, setPageCount] = useState(1)
  // 원본이 아직 안 열렸을 때 클릭한 근거가 몇 쪽인지 잃지 않도록 **자르지 않은**
  // 희망 쪽수를 들고 있다가, 실제 표시 쪽수는 렌더 때 총 쪽수로 자른다.
  const [desiredPage, setDesiredPage] = useState(1)
  const [zoomIndex, setZoomIndex] = useState(2)
  const [rotation, setRotation] = useState<Rotation>(0)
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 })
  const [error, setError] = useState('')

  const scale = ZOOM_STEPS[zoomIndex]
  const isPdf = doc.file_format === 'pdf'
  const pageNo = Math.min(desiredPage, pageCount)

  // 서류 탭이 바뀌면 배율·회전은 유지하고 페이지만 1쪽으로 되돌린다. 심사표 근거를
  // 클릭해 넘어온 경우엔 그 근거가 있는 쪽을 연다 (R4.3).
  //
  // 이 조정을 effect가 아니라 렌더 중에 하는 이유: effect로 하면 "이전 서류의 1쪽"을
  // 한 번 그린 뒤 다시 그리게 되어 화면이 깜빡인다. 아래는 리액트가 권장하는
  // '프롭이 바뀔 때 상태 조정' 패턴으로, 커밋 없이 곧바로 다시 렌더된다.
  const [prevDocId, setPrevDocId] = useState(doc.document_id)
  const [prevHighlight, setPrevHighlight] = useState<BBox | null>(highlight)
  const docChanged = prevDocId !== doc.document_id
  if (docChanged || prevHighlight !== highlight) {
    setPrevDocId(doc.document_id)
    setPrevHighlight(highlight)
    if (highlight) setDesiredPage(highlight.page + 1)
    else if (docChanged) setDesiredPage(1)
    if (docChanged) setError('')
  }

  // --- PDF 열기. 탭이 바뀔 때마다 이전 문서를 닫아 워커 메모리를 정리한다.
  useEffect(() => {
    if (!isPdf) return
    let cancelled = false
    const task = pdfjs.getDocument({ url: doc.file_url })
    task.promise
      .then((pdf) => {
        if (cancelled) {
          void pdf.destroy()
          return
        }
        pdfRef.current = pdf
        setPageCount(pdf.numPages)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
      void task.destroy()
      pdfRef.current = null
    }
  }, [doc.file_url, isPdf])

  // --- 페이지 렌더
  const render = useCallback(async () => {
    const pdf = pdfRef.current
    const canvas = canvasRef.current
    if (!pdf || !canvas) return
    const page = await pdf.getPage(Math.min(pageNo, pdf.numPages))
    const base = page.getViewport({ scale: 1, rotation: 0 })
    setPageSize({ width: base.width, height: base.height })
    const viewport = page.getViewport({ scale, rotation })
    canvas.width = Math.floor(viewport.width)
    canvas.height = Math.floor(viewport.height)
    await page.render({ canvas, viewport }).promise
  }, [pageNo, scale, rotation])

  useEffect(() => {
    void render().catch((e: unknown) =>
      setError(e instanceof Error ? e.message : String(e)),
    )
  }, [render, pageCount])

  // --- 하이라이트: 위 렌더 중 조정이 쪽을 옮겨두면 여기서 그 자리로 스크롤한다 (R4.3)
  useEffect(() => {
    if (!highlight) return
    markRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [highlight, pageSize, scale, rotation])

  const box =
    highlight && pageSize.width
      ? place(highlight, pageSize.width, pageSize.height, scale, rotation)
      : null

  return (
    <div className="viewer">
      <div className="viewer__bar">
        <span className="viewer__name">{doc.file_name}</span>
        {isPdf && pageCount > 1 && (
          <span className="viewer__pages">
            <button type="button" onClick={() => setDesiredPage(Math.max(1, pageNo - 1))}>
              ‹
            </button>
            {pageNo} / {pageCount}
            <button
              type="button"
              onClick={() => setDesiredPage(Math.min(pageCount, pageNo + 1))}
            >
              ›
            </button>
          </span>
        )}
        <span className="viewer__spacer" />
        <button
          type="button"
          onClick={() => setZoomIndex((i) => Math.max(0, i - 1))}
          aria-label="축소"
        >
          −
        </button>
        <span className="viewer__zoom">{Math.round(scale * 100)}%</span>
        <button
          type="button"
          onClick={() => setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1))}
          aria-label="확대"
        >
          ＋
        </button>
        <button
          type="button"
          onClick={() => setRotation((r) => (((r + 90) % 360) as Rotation))}
          aria-label="회전"
        >
          ↻
        </button>
        {/* 저장 버튼을 두지 않는 것이 이 화면의 요구사항이다 (R4.1). */}
        <span className="viewer__inline-badge" title="원본은 브라우저 안에서만 열립니다">
          브라우저 인라인 열람
        </span>
      </div>

      {error && <p className="viewer__error">원본을 열지 못했습니다: {error}</p>}

      <div className="viewer__stage">
        <div className="viewer__paper">
          {isPdf ? (
            <canvas ref={canvasRef} className="viewer__canvas" />
          ) : (
            <ImagePage doc={doc} scale={scale} rotation={rotation} onSize={setPageSize} />
          )}
          {box && (
            <div
              ref={markRef}
              className="viewer__mark"
              style={{
                left: `${box.left}px`,
                top: `${box.top}px`,
                width: `${box.width}px`,
                height: `${box.height}px`,
              }}
            >
              {highlightLabel && <span className="viewer__mark-tag">{highlightLabel}</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** 스캔 이미지(jpg/png)는 픽셀 좌표를 그대로 쓴다. */
function ImagePage({
  doc,
  scale,
  rotation,
  onSize,
}: {
  doc: OfficerDocument
  scale: number
  rotation: Rotation
  onSize: (size: { width: number; height: number }) => void
}) {
  return (
    <img
      className="viewer__image"
      src={doc.file_url}
      alt={`${doc.label} 원본`}
      style={{ transform: `rotate(${rotation}deg) scale(${scale})` }}
      onLoad={(e) =>
        onSize({
          width: e.currentTarget.naturalWidth,
          height: e.currentTarget.naturalHeight,
        })
      }
    />
  )
}
