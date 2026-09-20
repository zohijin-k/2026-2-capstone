/**
 * 캔버스 전자서명.
 *
 * 서식5는 원문상 "(서명 또는 인)" 자필서명을 요구한다. 데모는 이를 전자서명으로
 * 대체해 "수기 0건"을 보여주되, 현행 지침과 다르다는 점을 화면에 드러낸다.
 * 전자서명 대체 가능 여부는 TF 확인사항이다.
 */

import { useEffect, useRef, useState } from 'react'

interface Props {
  /** data:image/png;base64,... 또는 빈 문자열 */
  value: string
  onChange: (dataUrl: string) => void
  width?: number
  height?: number
}

export default function SignaturePad({ value, onChange, width = 260, height = 90 }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const drawing = useRef(false)
  const [empty, setEmpty] = useState(!value)

  // 저장된 서명이 있으면 되살린다 (임시저장 후 복귀 등).
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!value) {
      setEmpty(true)
      return
    }
    const img = new Image()
    img.onload = () => ctx.drawImage(img, 0, 0)
    img.src = value
    setEmpty(false)
    // value 는 최초 복원에만 쓴다. 그리는 중에 다시 그리면 획이 끊긴다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const pos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  const start = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx) return
    e.currentTarget.setPointerCapture(e.pointerId)
    drawing.current = true
    const { x, y } = pos(e)
    ctx.lineWidth = 1.8
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = '#111'
    ctx.beginPath()
    ctx.moveTo(x, y)
  }

  const move = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return
    const ctx = ref.current?.getContext('2d')
    if (!ctx) return
    const { x, y } = pos(e)
    ctx.lineTo(x, y)
    ctx.stroke()
    setEmpty(false)
  }

  const end = () => {
    if (!drawing.current) return
    drawing.current = false
    const canvas = ref.current
    if (canvas) onChange(canvas.toDataURL('image/png'))
  }

  const clear = () => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setEmpty(true)
    onChange('')
  }

  return (
    <span className="signature-box">
      <canvas
        ref={ref}
        className="signature-pad"
        width={width}
        height={height}
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={end}
        onPointerLeave={end}
        aria-label="전자서명 입력란"
      />
      <span className="signature-actions">
        <button type="button" onClick={clear}>
          지우기
        </button>
        <span style={{ color: empty ? '#c00' : '#177245' }}>
          {empty ? '서명해 주세요' : '서명 완료'}
        </span>
      </span>
    </span>
  )
}
