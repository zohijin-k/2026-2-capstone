/**
 * 범용 모달. 서류 업로드 화면의 ⓘ 요건 안내에서 처음 쓰였지만 다른 화면에서도
 * 재사용할 수 있도록 내용은 children으로 완전히 위임한다.
 */

import { useEffect, type ReactNode } from 'react'

import './modal.css'

export default function Modal({
  title,
  onClose,
  children,
  footer,
  variant = 'default',
}: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  /** viewer: 파일 크게 보기용 넓은 팝업 */
  variant?: 'default' | 'viewer' | 'printable-viewer'
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    // 팝업이 떠 있는 동안 뒤 화면이 같이 스크롤되지 않게 한다.
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  return (
    <div className={variant === 'printable-viewer' ? 'modal-overlay modal-overlay--printable' : 'modal-overlay'} onClick={onClose}>
      <div
        className={variant === 'default' ? 'modal' : 'modal modal--viewer'}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__head">
          <h3>{title}</h3>
          <button type="button" className="modal__close" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__foot">{footer}</div>}
      </div>
    </div>
  )
}
