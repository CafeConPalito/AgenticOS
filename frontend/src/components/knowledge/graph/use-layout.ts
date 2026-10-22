import { useEffect, useMemo, useState } from 'react'
import { layoutGraph, type LayoutLink, type LayoutNode, type Positions } from './layout'
import type { LayoutReply, LayoutRequest } from './layout.worker'

export interface Layout {
  positions: Positions
  /** The layout is still settling (the positions are partial or from the previous graph). */
  working: boolean
}

const NOTHING: Positions = {}

/**
 * Positions for the documents of a graph, computed in a Web Worker so the screen stays free
 * (spike S3: 330 ms for 300 documents and 1 000 links). Where there is no Worker (tests, very
 * old WebViews) it runs in place. While it settles, positions arrive several times.
 */
export function useGraphLayout(nodes: LayoutNode[], links: LayoutLink[]): Layout {
  // The layout depends on who is linked to whom, not on the labels: filters that hide nodes
  // recompute, a refreshed object with the same content does not.
  const key = useMemo(
    () =>
      JSON.stringify([
        nodes.map((n) => [n.id, n.topic, Math.round(n.radius)]),
        links.map((l) => [l.source, l.target, Math.round(l.weight * 100)]),
      ]),
    [nodes, links],
  )
  const inPlace = typeof Worker === 'undefined'
  const here = useMemo(
    () => (inPlace && nodes.length > 0 ? layoutGraph(nodes, links) : null),
    // `key` stands for the content of `nodes` and `links`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [inPlace, key],
  )
  const [reply, setReply] = useState<{ key: string; positions: Positions; done: boolean }>({
    key: '',
    positions: NOTHING,
    done: true,
  })

  useEffect(() => {
    if (inPlace || nodes.length === 0) return
    const worker = new Worker(new URL('./layout.worker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = (event: MessageEvent<LayoutReply>) => {
      setReply({ key, positions: event.data.positions, done: event.data.done })
      if (event.data.done) worker.terminate()
    }
    worker.postMessage({ id: 1, nodes, links } satisfies LayoutRequest)
    return () => worker.terminate()
    // `key` stands for the content of `nodes` and `links`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inPlace, key])

  if (nodes.length === 0) return { positions: NOTHING, working: false }
  if (here) return { positions: here, working: false }
  return { positions: reply.positions, working: reply.key !== key || !reply.done }
}
