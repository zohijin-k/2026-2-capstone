/**
 * 표 안의 파일 이름 — 누르면 크게 보기 팝업이 뜬다.
 * 최종 확인·마이페이지처럼 올린 서류를 목록으로 보여주는 곳에서 쓴다.
 */

import { useState } from 'react'

import FilePreview from './FilePreview.tsx'

interface Props {
  url: string
  name: string
  format: string
}

export default function FileLink({ url, name, format }: Props) {
  const [open, setOpen] = useState(false)
  const kind = (format || name).toLowerCase().endsWith('pdf') ? 'pdf' : 'image'
  return (
    <>
      <button type="button" className="file-link" onClick={() => setOpen(true)}>
        {name}
      </button>
      {open && <FilePreview url={url} name={name} kind={kind} onClose={() => setOpen(false)} />}
    </>
  )
}
