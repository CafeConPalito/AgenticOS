import { useEffect, useState } from 'react'

/** Current time, refreshed every `intervalMs` (null: frozen) for live durations. */
export function useNow(intervalMs: number | null): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    if (intervalMs === null) return
    const id = setInterval(() => setNow(new Date()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}
