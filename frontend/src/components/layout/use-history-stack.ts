import { useEffect, useRef, useState } from 'react'
import { type Location, NavigationType, useLocation, useNavigationType } from 'react-router'

interface Stack {
  keys: string[]
  pos: number
}

/** Pure step: where the session history stands after a navigation (phase 20). */
export function step(stack: Stack, type: NavigationType, key: string): Stack {
  if (stack.keys[stack.pos] === key) return stack
  if (type === NavigationType.Push)
    return { keys: [...stack.keys.slice(0, stack.pos + 1), key], pos: stack.pos + 1 }
  if (type === NavigationType.Replace) {
    const keys = [...stack.keys]
    keys[stack.pos] = key
    return { keys, pos: stack.pos }
  }
  const found = stack.keys.indexOf(key)
  // A POP to an entry we never saw (e.g. after a reload): start again from it.
  return found >= 0 ? { keys: stack.keys, pos: found } : { keys: [key], pos: 0 }
}

/**
 * Whether there is somewhere to go forward. React Router keeps no such flag, and
 * `history.state.idx` exists only with the browser history (not in tests), so the stack is
 * followed from the navigations themselves. Alt+←/→ and the mouse's side buttons are left to
 * the webview (spike S3): they arrive here as POPs.
 */
export function useHistoryStack(): { canForward: boolean } {
  const location: Location = useLocation()
  const type = useNavigationType()
  const stack = useRef<Stack>({ keys: [location.key], pos: 0 })
  const [canForward, setCanForward] = useState(false)

  useEffect(() => {
    stack.current = step(stack.current, type, location.key)
    setCanForward(stack.current.pos < stack.current.keys.length - 1)
  }, [type, location.key])

  return { canForward }
}
