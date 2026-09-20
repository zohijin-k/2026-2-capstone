import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App.tsx'
import { INITIAL } from './app/initial-params.ts'
// 전역 리셋 → 화면별 토큰 → 공용 규칙 순. 토큰 두 벌은 body[data-view] 로
// 스코프가 갈려 서로 침범하지 않는다(styles/tokens-form.css 머리말 참고).
import './styles/base.css'
import './styles/tokens-form.css'
import './styles/tokens-status.css'
import './index.css'

// 첫 페인트 전에 화면 토큰이 붙도록 미리 심는다. App이 뒤이어 전환을 맡는다.
// 여기서 안 하면 첫 프레임만 폰트·배경이 맨몸으로 그려진다.
document.body.dataset.view = INITIAL.view

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
