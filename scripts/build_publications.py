#!/usr/bin/env python3
"""Generate the Academic Pages publication list from one BibTeX file."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import bibtexparser

ROOT = Path(__file__).resolve().parents[1]
BIB_FILE = ROOT / "_bibliography" / "publications.bib"
OUTPUT_FILE = ROOT / "_includes" / "publications-generated.html"

OWN_NAME = "Alexander Steinmaurer"

STATUS_ORDER = ["published", "accepted", "preprint", "submitted", "manuscript"]
STATUS_TITLES = {
    "published": "Peer-reviewed publications",
    "accepted": "Accepted / in press",
    "preprint": "Preprints",
    "submitted": "Under review",
    "manuscript": "Work in progress",
}
TYPE_LABELS = {
    "journal": "Journal",
    "conference": "Conference",
    "chapter": "Book chapter",
    "thesis": "Thesis",
    "other": "Other",
}


def clean(value: str | None) -> str:
    """Remove common BibTeX braces while keeping ordinary punctuation."""
    if not value:
        return ""
    value = value.replace("{", "").replace("}", "")
    value = value.replace(r"\&", "&")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def keywords(entry: dict) -> set[str]:
    raw = clean(entry.get("keywords", ""))
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def publication_status(entry: dict) -> str:
    keys = keywords(entry)
    for status in STATUS_ORDER:
        if status in keys:
            return status
    # Sensible fallback for entries that have not yet been tagged.
    if clean(entry.get("pubstate")).lower() in {"inpress", "in press", "forthcoming"}:
        return "accepted"
    return "published"


def publication_type(entry: dict) -> str:
    keys = keywords(entry)
    for key in TYPE_LABELS:
        if key in keys:
            return key
    entry_type = clean(entry.get("ENTRYTYPE")).lower()
    if entry_type == "article":
        return "journal"
    if entry_type in {"inproceedings", "conference"}:
        return "conference"
    if entry_type in {"incollection", "inbook"}:
        return "chapter"
    if entry_type in {"phdthesis", "mastersthesis"}:
        return "thesis"
    return "other"


def author_display(author: str) -> str:
    parts = [p.strip() for p in author.split(" and ") if p.strip()]
    rendered = []
    for person in parts:
        person = clean(person)
        if "," in person:
            last, first = [x.strip() for x in person.split(",", 1)]
            display = f"{first} {last}"
        else:
            display = person

        escaped = html.escape(display)
        if OWN_NAME.lower() in display.lower():
            escaped = f"<strong>{escaped}</strong>"
        rendered.append(escaped)

    if not rendered:
        return ""
    if len(rendered) == 1:
        return rendered[0]
    if len(rendered) == 2:
        return f"{rendered[0]} &amp; {rendered[1]}"
    return ", ".join(rendered[:-1]) + f", &amp; {rendered[-1]}"


def venue(entry: dict) -> str:
    name = (
        clean(entry.get("journal"))
        or clean(entry.get("booktitle"))
        or clean(entry.get("publisher"))
        or clean(entry.get("institution"))
        or clean(entry.get("school"))
    )
    pieces = []
    if name:
        pieces.append(html.escape(name))

    volume = clean(entry.get("volume"))
    number = clean(entry.get("number"))
    pages = clean(entry.get("pages"))

    if volume:
        vol = html.escape(volume)
        if number:
            vol += f"({html.escape(number)})"
        pieces.append(vol)
    if pages:
        pieces.append(f"pp. {html.escape(pages.replace('--', '–'))}")

    return ", ".join(pieces)


def links(entry: dict) -> str:
    items = []
    emitted_urls = set()

    doi = clean(entry.get("doi"))
    if doi:
        doi_url = "https://doi.org/" + quote(doi, safe="/:._-()")
        items.append(f'<a class="pub-link" href="{doi_url}">DOI</a>')
        emitted_urls.add(doi_url.rstrip("/").lower())

    eprint = clean(entry.get("eprint"))
    archive = clean(entry.get("archiveprefix")).lower()
    if eprint and archive == "arxiv":
        arxiv_url = "https://arxiv.org/abs/" + quote(eprint, safe="/._-")
        items.append(f'<a class="pub-link" href="{arxiv_url}">arXiv</a>')
        emitted_urls.add(arxiv_url.rstrip("/").lower())

    url = clean(entry.get("url"))
    if url and url.rstrip("/").lower() not in emitted_urls:
        items.append(f'<a class="pub-link" href="{html.escape(url, quote=True)}">Link</a>')

    pdf = clean(entry.get("pdf"))
    if pdf:
        items.append(f'<a class="pub-link" href="{html.escape(pdf, quote=True)}">PDF</a>')

    code = clean(entry.get("code"))
    if code:
        items.append(f'<a class="pub-link" href="{html.escape(code, quote=True)}">Code</a>')

    return " ".join(items)


def render_entry(entry: dict) -> str:
    title = html.escape(clean(entry.get("title")) or "Untitled")
    authors = author_display(entry.get("author", ""))
    pubvenue = venue(entry)
    note = html.escape(clean(entry.get("note")))
    year = html.escape(clean(entry.get("year")) or "n.d.")
    ptype = TYPE_LABELS[publication_type(entry)]
    link_html = links(entry)

    meta_parts = [x for x in [pubvenue, note] if x]
    meta = " · ".join(meta_parts)

    lines = [
        '<article class="publication-item">',
        f'  <div class="publication-title">{title}</div>',
    ]
    if authors:
        lines.append(f'  <div class="publication-authors">{authors}</div>')
    if meta:
        lines.append(f'  <div class="publication-venue">{meta}</div>')
    lines.append('  <div class="publication-footer">')
    lines.append(f'    <span class="publication-type">{html.escape(ptype)}</span>')
    lines.append(f'    <span class="publication-year-inline">{year}</span>')
    if link_html:
        lines.append(f'    <span class="publication-links">{link_html}</span>')
    lines.append("  </div>")
    lines.append("</article>")
    return "\n".join(lines)


def main() -> None:
    with BIB_FILE.open(encoding="utf-8") as fh:
        database = bibtexparser.load(fh)

    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

    for entry in database.entries:
        if "private" in keywords(entry):
            continue
        status = publication_status(entry)
        year = clean(entry.get("year")) or "n.d."
        grouped[status][year].append(entry)

    output = [
        "<!-- AUTO-GENERATED by scripts/build_publications.py. DO NOT EDIT. -->",
        '<div class="publications-list">',
    ]

    for status in STATUS_ORDER:
        if status not in grouped:
            continue
        output.append(f'<section class="publication-section" id="{status}">')
        output.append(f"  <h2>{html.escape(STATUS_TITLES[status])}</h2>")

        years = sorted(
            grouped[status].keys(),
            key=lambda y: (y != "n.d.", int(y) if y.isdigit() else -1),
            reverse=True,
        )
        for year in years:
            output.append(f'  <h3 class="publication-year">{html.escape(year)}</h3>')
            entries = sorted(
                grouped[status][year],
                key=lambda e: clean(e.get("title")).lower(),
            )
            for entry in entries:
                output.append(render_entry(entry))
        output.append("</section>")

    output.append("</div>")
    OUTPUT_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(f"Generated {OUTPUT_FILE.relative_to(ROOT)} from {BIB_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
