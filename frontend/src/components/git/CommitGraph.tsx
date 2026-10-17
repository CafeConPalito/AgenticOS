import type { GraphRow } from './graph'

const COLUMN = 14 // px per lane
export const ROW_HEIGHT = 30
const DOT = 4.5

const color = (lane: number) => `var(--graph-${lane % 8})`
const x = (lane: number) => lane * COLUMN + COLUMN / 2

/** A line between two columns that bends in the middle of the row. */
function bend(from: number, to: number, top: number, bottom: number): string {
  if (from === to) return `M${x(from)} ${top} L${x(to)} ${bottom}`
  const middle = (top + bottom) / 2
  return `M${x(from)} ${top} C${x(from)} ${middle}, ${x(to)} ${middle}, ${x(to)} ${bottom}`
}

/** The lines and the dot of one commit of the history, drawn with the lanes `layoutGraph` gave. */
export function CommitGraph({ row, columns }: { row: GraphRow; columns: number }) {
  const middle = ROW_HEIGHT / 2
  return (
    <svg
      aria-hidden
      width={columns * COLUMN}
      height={ROW_HEIGHT}
      className="shrink-0"
      fill="none"
      strokeWidth={2}
      strokeLinecap="round"
    >
      {row.through.map((lane) => (
        <path key={`t${lane}`} d={bend(lane, lane, 0, ROW_HEIGHT)} stroke={color(lane)} />
      ))}
      {row.incoming.map((lane) => (
        <path key={`i${lane}`} d={bend(lane, row.lane, 0, middle)} stroke={color(lane)} />
      ))}
      {/* The line above the dot: the one that was waiting for this commit in its own lane. */}
      {row.fromAbove && <path d={bend(row.lane, row.lane, 0, middle)} stroke={color(row.lane)} />}
      {row.outgoing.map((lane, index) => (
        <path
          key={`o${index}-${lane}`}
          d={bend(row.lane, lane, middle, ROW_HEIGHT)}
          stroke={color(lane)}
        />
      ))}
      <circle cx={x(row.lane)} cy={middle} r={DOT} fill={color(row.lane)} stroke="var(--card)" />
    </svg>
  )
}
