import { useEffect, useState } from 'react'

/** Keep brief loading states invisible to avoid a flash before a fast response. */
export default function useDelayedFlag(active: boolean, delay = 150): boolean {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!active) {
      setVisible(false)
      return
    }
    const timer = window.setTimeout(() => setVisible(true), delay)
    return () => window.clearTimeout(timer)
  }, [active, delay])

  return active && visible
}
