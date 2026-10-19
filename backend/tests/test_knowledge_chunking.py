"""Splitting Markdown into the chunks a document is searched by (phase 14, block 5)."""

import re
from itertools import pairwise

import pytest

from agentic_os.services.knowledge import chunking
from agentic_os.services.knowledge.chunking import MAX_TOKENS, chunk, tokens_of


def words(n: int, prefix: str = "palabra") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def paragraphs(count: int, size: int = 60, prefix: str = "p") -> str:
    return "\n\n".join(words(size, f"{prefix}{i}_") + "." for i in range(count))


def test_an_empty_document_has_no_chunks():
    assert chunk("") == [] and chunk("\n\n  \n") == []


def test_a_short_document_is_one_chunk_with_its_text_by_position():
    markdown = "# Guía\n\nPrimera frase. Segunda frase."
    (only,) = chunk(markdown)
    assert (only.ord, only.heading, only.location) == (0, "Guía", "")
    assert markdown[only.start : only.end] == only.text == markdown
    assert only.tokens == tokens_of(markdown)


def test_the_heading_path_follows_the_structure():
    markdown = (
        "# Manual\n\n## Instalación\n\n" + paragraphs(4, 80, "i") + "\n\n## Uso\n\n"
        "### Atajos\n\n" + paragraphs(4, 80, "u")
    )
    chunks = chunk(markdown)
    assert chunks[0].heading == "Manual › Instalación"
    assert any(c.heading == "Manual › Uso › Atajos" for c in chunks)
    assert all(c.heading.startswith("Manual") for c in chunks)


def test_a_new_section_opens_a_new_chunk_once_the_current_one_has_body():
    small = "# A\n\nUna frase breve.\n\n## B\n\nOtra frase breve."
    assert len(chunk(small)) == 1  # tiny sections are not worth separate chunks
    big = "# A\n\n" + paragraphs(3, 70, "a") + "\n\n## B\n\n" + paragraphs(3, 70, "b")
    first, second = chunk(big)[0], chunk(big)[-1]
    assert "p0_" not in first.text and "## B" not in first.text
    assert second.heading == "A › B"


def test_chunks_are_about_the_target_size_and_cover_the_whole_text():
    markdown = "# Libro\n\n" + paragraphs(40, 60)
    chunks = chunk(markdown)
    assert len(chunks) > 3
    assert all(0 < c.tokens <= MAX_TOKENS for c in chunks)
    assert [c.ord for c in chunks] == list(range(len(chunks)))
    covered = set()
    for c in chunks:
        assert markdown[c.start : c.end] == c.text
        covered.update(range(c.start, c.end))
    body = [m.start() for m in re.finditer(r"\S", markdown)]
    assert all(i in covered for i in body)  # nothing is lost between chunks


def test_consecutive_chunks_overlap():
    markdown = "# Libro\n\n" + paragraphs(30, 40)
    chunks = chunk(markdown)
    overlaps = [a.end - b.start for a, b in pairwise(chunks)]
    assert any(o > 0 for o in overlaps)  # a sentence on the border is whole in one of them
    assert all(o <= chunking.OVERLAP_TOKENS * 4 + 4 for o in overlaps)


def test_page_markers_give_the_location_and_stay_out_of_the_words():
    markdown = (
        "<!-- page: 1 -->\n\n"
        + paragraphs(2, 50, "x")
        + "\n\n<!-- page: 2 -->\n\n"
        + paragraphs(2, 50, "y")
    )
    (chunk_,) = chunk(markdown)[:1]
    assert chunk_.location == "p. 1-2"  # it spans two pages
    assert "<!--" not in chunk_.clean_text() and "<!--" not in chunk_.for_words()
    other = chunk("<!-- Slide number: 3 -->\n# Título\n\nTexto.")
    assert other[0].location == "diapositiva 3"
    sheet = chunk("<!-- sheet: Ventas -->\n## Ventas\n\n| a | b |\n| --- | --- |\n| 1 | 2 |")
    assert sheet[0].location == "hoja Ventas"


def test_code_blocks_and_tables_are_not_cut_when_they_fit():
    code = (
        "```python\n"
        + "\n".join(f"x{i} = {i}  # comentario largo {i}" for i in range(40))
        + "\n```"
    )
    table = "| col | val |\n| --- | --- |\n" + "\n".join(f"| fila{i} | {i} |" for i in range(40))
    markdown = f"# Doc\n\n{paragraphs(2, 50, 'a')}\n\n{code}\n\n{paragraphs(2, 50, 'b')}\n\n{table}"
    chunks = chunk(markdown)
    for block in (code, table):
        holders = [c for c in chunks if block in c.text]
        assert holders, "a block that fits is whole in some chunk"
    # A comment in code is never a heading.
    only_code = chunk("```\n# no soy un título\nprint(1)\n```")
    assert only_code[0].heading == ""


def test_a_block_bigger_than_the_maximum_is_cut_into_pieces():
    giant = "# Doc\n\n" + " ".join(f"Frase número {i} del texto." for i in range(900))
    chunks = chunk(giant)
    assert len(chunks) > 3
    assert max(c.tokens for c in chunks) <= MAX_TOKENS
    minified = "x" * 20_000  # one «sentence» without any break
    cut = chunk(minified)
    assert len(cut) > 5 and max(c.tokens for c in cut) <= MAX_TOKENS


def test_no_chunk_is_only_a_repeat_of_the_overlap():
    markdown = "# T\n\n" + paragraphs(9, 55)
    chunks = chunk(markdown)
    for a, b in pairwise(chunks):
        assert b.end > a.end  # each one brings something new


@pytest.mark.parametrize("title", ["Manual", "Guía de estilo"])
def test_what_the_model_reads_names_the_document_and_the_place(title: str):
    (c,) = chunk("# Instalación\n\nPasos para instalar.")
    assert c.for_embedding(title).startswith(f"{title} › Instalación\n")
    assert c.for_words().startswith("Instalación\n")
    no_heading = chunk("Solo texto.")[0]
    assert no_heading.for_embedding(title).startswith(f"{title}\n")
