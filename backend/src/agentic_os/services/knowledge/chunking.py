"""Splitting a document's Markdown into the pieces it is searched by (phase 14, block 5).

A chunk is a span of the document (`start`..`end`, offsets in its Markdown: the text is never
copied) of about 400 tokens that follows the document's structure: it does not cut a code block
or a table in two when they fit, a heading of level 1-3 opens a new chunk once the current one
has some body, and consecutive chunks overlap by about 50 tokens so that a sentence on the
border is whole in one of them. Each chunk knows its heading path ("Manual › Instalación") and
where in the document it is ("p. 12", "diapositiva 3", "hoja Ventas").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TARGET_TOKENS = 400  # a chunk is closed when the next block would take it past this
MAX_TOKENS = 520  # a single block above this is cut into pieces
OVERLAP_TOKENS = 50
MIN_BODY_BEFORE_HEADING = 100  # a heading opens a new chunk only if this much body came before

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_MARKER = re.compile(r"^<!--\s*(?P<kind>page|Slide number|sheet):\s*(?P<where>[^>]*?)\s*-->\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_SENTENCE_END = re.compile(r"(?<=[.!?:;])\s+|\n")
_WHERE = {"page": "p. {}", "Slide number": "diapositiva {}", "sheet": "hoja {}"}


def tokens_of(text: str) -> int:
    """About four characters per token, as everywhere else in the library."""
    return (len(text) + 3) // 4


@dataclass
class Chunk:
    ord: int
    heading: str  # "Manual › Instalación", or ""
    location: str  # "p. 12", "p. 12-13", "diapositiva 3", "hoja Ventas", or ""
    start: int
    end: int
    text: str = field(repr=False)

    @property
    def tokens(self) -> int:
        return tokens_of(self.text)

    def clean_text(self) -> str:
        """The text without the page markers and with the picture references left as words."""
        return re.sub(r"\n{3,}", "\n\n", _COMMENT.sub("", self.text)).strip()

    def for_embedding(self, title: str) -> str:
        """What the model reads: where the chunk is, then its text."""
        place = f"{title} › {self.heading}" if self.heading else title
        return f"{place}\n{self.clean_text()}"

    def for_words(self) -> str:
        """What the full-text index holds: the heading (a good place for the words people look
        for) and the text."""
        return f"{self.heading}\n{self.clean_text()}" if self.heading else self.clean_text()


@dataclass
class _Block:
    start: int
    end: int
    kind: str  # heading | text | code | table | quote
    level: int  # of a heading
    path: tuple[str, ...]  # heading path at the block (a heading's own path includes itself)
    location: str

    @property
    def length(self) -> int:
        return self.end - self.start


# --------------------------------------------------------------------------- parsing
def _blocks(markdown: str) -> list[_Block]:
    """The document as blocks with their position, heading path and location."""
    blocks: list[_Block] = []
    path: list[tuple[int, str]] = []
    location = ""
    fence: str | None = None
    open_kind: str | None = None
    open_start = 0
    position = 0

    def current_path() -> tuple[str, ...]:
        return tuple(title for _, title in path)

    def close(end: int) -> None:
        nonlocal open_kind
        if open_kind is not None:
            blocks.append(_Block(open_start, end, open_kind, 0, current_path(), where_open))
            open_kind = None

    where_open = ""
    for line in markdown.splitlines(keepends=True):
        start, end = position, position + len(line)
        position = end
        stripped = line.strip()
        if fence is not None:  # inside a code block: nothing else counts
            if (
                (m := _FENCE.match(line))
                and m.group(1)[0] == fence[0]
                and len(m.group(1)) >= len(fence)
            ):
                fence = None
                close(end)
            continue
        if m := _FENCE.match(line):
            close(start)
            fence, open_kind, open_start, where_open = m.group(1), "code", start, location
            continue
        if not stripped:
            close(start)
            continue
        if marker := _MARKER.match(stripped):
            close(start)
            location = _WHERE[marker.group("kind")].format(marker.group("where"))
            continue
        if heading := _HEADING.match(stripped):
            close(start)
            level = len(heading.group(1))
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, heading.group(2)))
            blocks.append(_Block(start, end, "heading", level, current_path(), location))
            continue
        kind = (
            "table" if stripped.startswith("|") else "quote" if stripped.startswith(">") else "text"
        )
        if open_kind != kind:
            close(start)
            open_kind, open_start, where_open = kind, start, location
    close(position)
    return blocks


def _pieces(markdown: str, block: _Block) -> list[_Block]:
    """A block above MAX_TOKENS in pieces of about TARGET_TOKENS, cut at the end of a sentence or
    a line."""
    if tokens_of(markdown[block.start : block.end]) <= MAX_TOKENS:
        return [block]
    pieces: list[_Block] = []
    piece_start = block.start
    for match in _SENTENCE_END.finditer(markdown, block.start, block.end):
        cut = match.end()
        if tokens_of(markdown[piece_start:cut]) >= TARGET_TOKENS:
            pieces.append(_replace(block, piece_start, cut))
            piece_start = cut
    if piece_start < block.end:
        pieces.append(_replace(block, piece_start, block.end))
    # A «sentence» that is itself huge (a minified line…): cut by size.
    sized: list[_Block] = []
    limit = MAX_TOKENS * 4
    for piece in pieces:
        for offset in range(piece.start, piece.end, limit):
            sized.append(_replace(piece, offset, min(offset + limit, piece.end)))
    return sized


def _tail_of(markdown: str, block: _Block, budget: int) -> _Block | None:
    """The last sentences of a text block that fit in `budget` tokens (None if there are none)."""
    if block.kind not in ("text", "quote") or budget <= 0:
        return None
    for match in _SENTENCE_END.finditer(markdown, block.start, block.end):
        if match.end() < block.end and tokens_of(markdown[match.end() : block.end]) <= budget:
            return _replace(block, match.end(), block.end)
    # A paragraph without a sentence break: the last words, cut at a space.
    space = markdown.find(" ", max(block.start, block.end - budget * 4), block.end)
    if space != -1 and space + 1 < block.end:
        return _replace(block, space + 1, block.end)
    return None


def _replace(block: _Block, start: int, end: int) -> _Block:
    return _Block(start, end, block.kind, block.level, block.path, block.location)


# ---------------------------------------------------------------------------- packing
def _place(blocks: list[_Block]) -> str:
    first, last = blocks[0].location, blocks[-1].location
    if first and last and first != last and first.startswith("p. ") and last.startswith("p. "):
        return f"{first}-{last.removeprefix('p. ')}"
    return first


def chunk(markdown: str) -> list[Chunk]:
    """The chunks of a document (none for an empty one)."""
    chunks: list[Chunk] = []
    current: list[_Block] = []
    size = body = added = 0  # `added`: blocks that are new since the last chunk was closed

    def flush(carry_overlap: bool) -> None:
        nonlocal current, size, body, added
        if not current:
            return
        start, end = current[0].start, current[-1].end
        text = markdown[start:end]
        if text.strip() and added:  # only the overlap left over is not a chunk
            body_blocks = [b for b in current if b.kind != "heading"] or current
            chunks.append(
                Chunk(
                    ord=len(chunks),
                    heading=" › ".join(body_blocks[0].path),
                    location=_place(current),
                    start=start,
                    end=end,
                    text=text,
                )
            )
        tail: list[_Block] = []
        if carry_overlap:
            carried = 0
            for block in reversed(current):
                length = tokens_of(markdown[block.start : block.end])
                if block.kind == "heading":
                    break
                if carried + length <= OVERLAP_TOKENS:
                    tail.insert(0, block)
                    carried += length
                    continue
                # It does not fit whole: take its last sentences instead.
                part = _tail_of(markdown, block, OVERLAP_TOKENS - carried)
                if part is not None:
                    tail.insert(0, part)
                break
        current = tail
        size = sum(tokens_of(markdown[b.start : b.end]) for b in tail)
        body = size
        added = 0

    for original in _blocks(markdown):
        for block in _pieces(markdown, original):
            length = tokens_of(markdown[block.start : block.end])
            if block.kind == "heading" and block.level <= 3 and body >= MIN_BODY_BEFORE_HEADING:
                flush(carry_overlap=False)
            elif current and size + length > TARGET_TOKENS and body > 0:
                flush(carry_overlap=True)
            current.append(block)
            added += 1
            size += length
            if block.kind != "heading":
                body += length
    flush(carry_overlap=False)
    return chunks
