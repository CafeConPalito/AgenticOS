/// <reference lib="webworker" />
import { layoutGraph, type LayoutLink, type LayoutNode, type Positions } from './layout'

export interface LayoutRequest {
  id: number
  nodes: LayoutNode[]
  links: LayoutLink[]
}

export interface LayoutReply {
  id: number
  positions: Positions
  done: boolean
}

// The force layout takes a few hundred milliseconds with 300 documents: off the main thread.
self.onmessage = (event: MessageEvent<LayoutRequest>) => {
  const { id, nodes, links } = event.data
  const positions = layoutGraph(nodes, links, (partial) =>
    self.postMessage({ id, positions: partial, done: false } satisfies LayoutReply),
  )
  self.postMessage({ id, positions, done: true } satisfies LayoutReply)
}
