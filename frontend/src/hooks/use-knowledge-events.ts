import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { applyKnowledgeEvent } from '@/api/knowledge'
import { KnowledgeEventsSocket } from '@/lib/knowledge-events'

/**
 * Follows the library live while a screen that shows it is open: documents change state,
 * the queue and the machine's load move. After a reconnection everything is read again,
 * because events were missed meanwhile.
 */
export function useKnowledgeEvents() {
  const queryClient = useQueryClient()
  useEffect(() => {
    let first = true
    const socket = new KnowledgeEventsSocket(
      (event) => applyKnowledgeEvent(queryClient, event),
      (connected) => {
        if (!connected) return
        if (!first) void queryClient.invalidateQueries({ queryKey: ['knowledge'] })
        first = false
      },
    )
    void socket.connect()
    return () => socket.close()
  }, [queryClient])
}
