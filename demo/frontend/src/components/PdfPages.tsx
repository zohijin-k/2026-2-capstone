/**
 * PDF 쪽들을 주어진 폭에 맞춰 캔버스로 그린다 (pdf.js).
 *
 * 브라우저 내장 PDF 뷰어(<object>·<iframe>)는 저장·인쇄 도구 막대가 붙고 브라우저마다
 * 모양이 달라서, 신청자 화면에서도 담당자 뷰어와 같은 pdf.js로 그린다.
 * 원본을 저장하는 경로는 만들지 않는다 — 캔버스에 그리기만 한다.
 */

import { useEffect, useRef, useState } from 'react'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

interface Props {
  url: string
  /** 한 쪽의 화면 폭(px) */
  width: number
  /** 주면 쪽 전체가 이 높이 안에 들어오게 줄인다 (썸네일용) */
  maxHeight?: number
  /** 앞에서부터 이 쪽 수까지만 그린다 (미리보기 썸네일용) */
  maxPages?: number
  /** 총 쪽 수를 알게 되면 알려준다 */
  onPageCount?: (count: number) => void
  onReady?: () => void
  onError?: () => void
  className?: string
}

export default function PdfPages({
  url,
  width,
  maxHeight,
  maxPages,
  onPageCount,
  onReady,
  onError,
  className,
}: Props) {
  const [loaded, setLoaded] = useState<{
    url: string
    pdf: pdfjs.PDFDocumentProxy | null
    error: string
  } | null>(null)
  const countRef = useRef(onPageCount)
  const errorRef = useRef(onError)
  useEffect(() => {
    countRef.current = onPageCount
    errorRef.current = onError
  }, [onPageCount, onError])

  useEffect(() => {
    let cancelled = false
    const task = pdfjs.getDocument({ url })
    task.promise
      .then((doc) => {
        if (cancelled) return
        setLoaded({ url, pdf: doc, error: '' })
        countRef.current?.(doc.numPages)
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setLoaded({ url, pdf: null, error: e instanceof Error ? e.message : String(e) })
          errorRef.current?.()
        }
      })
    return () => {
      cancelled = true
      void task.destroy()
    }
  }, [url])

  const pdf = loaded?.url === url ? loaded.pdf : null
  const error = loaded?.url === url ? loaded.error : ''
  if (error) return <p className="pdfpages__error">PDF를 열 수 없습니다.</p>
  if (!pdf) return <p className="pdfpages__loading">불러오는 중…</p>

  const count = Math.min(pdf.numPages, maxPages ?? pdf.numPages)
  return (
    <div className={className ? `pdfpages ${className}` : 'pdfpages'}>
      {Array.from({ length: count }, (_, i) => (
        <PdfPage
          key={i}
          pdf={pdf}
          pageNo={i + 1}
          width={width}
          maxHeight={maxHeight}
          onReady={onReady}
          onError={onError}
        />
      ))}
    </div>
  )
}

function PdfPage({
  pdf,
  pageNo,
  width,
  maxHeight,
  onReady,
  onError,
}: {
  pdf: pdfjs.PDFDocumentProxy
  pageNo: number
  width: number
  maxHeight?: number
  onReady?: () => void
  onError?: () => void
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  const readyRef = useRef(onReady)
  const errorRef = useRef(onError)
  const [size, setSize] = useState({ width, height: Math.round(width * 1.414) })

  useEffect(() => {
    readyRef.current = onReady
    errorRef.current = onError
  }, [onReady, onError])

  useEffect(() => {
    let cancelled = false
    let task: pdfjs.RenderTask | null = null
    void pdf.getPage(pageNo).then((page) => {
      const canvas = ref.current
      if (cancelled || !canvas) return
      const base = page.getViewport({ scale: 1 })
      const dpr = Math.max(1, window.devicePixelRatio || 1)
      let fit = width / base.width
      if (maxHeight) fit = Math.min(fit, maxHeight / base.height)
      const viewport = page.getViewport({ scale: fit * dpr })
      canvas.width = Math.floor(viewport.width)
      canvas.height = Math.floor(viewport.height)
      setSize({
        width: Math.round(viewport.width / dpr),
        height: Math.round(viewport.height / dpr),
      })
      task = page.render({ canvas, viewport })
      task.promise.then(() => readyRef.current?.()).catch(() => errorRef.current?.())
    })
    .catch(() => errorRef.current?.())
    return () => {
      cancelled = true
      task?.cancel()
    }
  }, [pdf, pageNo, width, maxHeight])

  return (
    <canvas
      ref={ref}
      className="pdfpages__page"
      style={size}
      aria-label={`${pageNo}쪽`}
    />
  )
}
