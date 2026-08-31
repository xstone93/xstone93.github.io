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

SECTION_ORDER = ["peer_reviewed", "book_other", "preprints_manuscripts"]
SECTION_TITLES = {
    "peer_reviewed": "Peer-reviewed Publications",
    "book_other": "Book Chapters & Other Publications",
    "preprints_manuscripts": "Preprints & Manuscripts",
}

TYPE_LABELS = {
    "journal": "Journal",
    "conference": "Conference",
    "workshop": "Workshop",
    "book-chapter": "Book chapter",
    "chapter": "Book chapter",
    "thesis": "Thesis",
    "preprint": "Preprint",
    "manuscript": "Manuscript",
    "other": "Other",
}

PUBSTATE_LABELS = {
    "submitted": "Submitted",
    "underreview": "Under review",
    "under review": "Under review",
    "underrevision": "Under revision",
    "under revision": "Under revision",
    "inpress": "Accepted / in press",
    "in press": "Accepted / in press",
    "forthcoming": "Accepted / in press",
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


def publication_section(entry: dict) -> str:
    """Map detailed BibTeX metadata to the three public website sections."""
    keys = keywords(entry)
    pubstate = clean(entry.get("pubstate")).lower()

    # Preprints and manuscripts always belong together.
    if "preprint" in keys or "manuscript" in keys:
        return "preprints_manuscripts"
    if pubstate in {"submitted", "underreview", "under review", "underrevision", "under revision"}:
        return "preprints_manuscripts"

    # Explicit peer-review marker takes precedence.
    if "peer-reviewed" in keys or "peer reviewed" in keys:
        return "peer_reviewed"

    # Accepted/in-press work has already passed peer review.
    if pubstate in {"inpress", "in press", "forthcoming"}:
        return "peer_reviewed"

    # Book chapters and explicitly non-peer-reviewed/other outputs.
    if "book-chapter" in keys or "chapter" in keys or "other" in keys:
        return "book_other"

    # Backward compatibility for older entries.
    if "published" in keys and ({"journal", "conference", "workshop"} & keys):
        return "peer_reviewed"

    entry_type = clean(entry.get("ENTRYTYPE")).lower()
    if entry_type in {"incollection", "inbook"}:
        return "book_other"

    # Conservative fallback: published articles/conference papers are treated
    # as peer-reviewed only when their type strongly indicates that.
    if entry_type in {"article", "inproceedings", "conference"}:
        return "peer_reviewed"

    return "book_other"


def publication_type(entry: dict) -> str:
    keys = keywords(entry)
    for key in TYPE_LABELS:
        if key in keys:
            return key

    entry_type = clean(entry.get("ENTRYTYPE")).lower()
    if "preprint" in keys:
        return "preprint"
    if "manuscript" in keys or entry_type == "unpublished":
        return "manuscript"
    if entry_type == "article":
        return "journal"
    if entry_type in {"inproceedings", "conference"}:
        return "conference"
    if entry_type in {"incollection", "inbook"}:
        return "book-chapter"
    if entry_type in {"phdthesis", "mastersthesis"}:
        return "thesis"
    return "other"


def status_label(entry: dict) -> str:
    keys = keywords(entry)
    pubstate = clean(entry.get("pubstate")).lower()

    if pubstate in PUBSTATE_LABELS:
        return PUBSTATE_LABELS[pubstate]
    if "preprint" in keys:
        return "Preprint"
    if "manuscript" in keys:
        return "Manuscript"
    return ""


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
            escaped = f'<span class="publication-own-name">{escaped}</span>'
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
    eid = clean(entry.get("eid"))

    if volume:
        vol = html.escape(volume)
        if number:
            vol += f"({html.escape(number)})"
        pieces.append(vol)
    elif number:
        pieces.append(html.escape(number))

    if pages:
        pieces.append(f"pp. {html.escape(pages.replace('--', '–'))}")
    elif eid:
        pieces.append(f"Article {html.escape(eid)}")

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
    ptype = TYPE_LABELS[publication_type(entry)]
    status = status_label(entry)
    link_html = links(entry)

    lines = [
        '<article class="publication-item">',
        f'  <div class="publication-title">{title}</div>',
    ]

    if authors:
        lines.append(f'  <div class="publication-authors">{authors}</div>')
    if pubvenue:
        lines.append(f'  <div class="publication-venue">{pubvenue}</div>')
    if note:
        lines.append(f'  <div class="publication-note">{note}</div>')

    lines.append('  <div class="publication-footer">')
    lines.append(f'    <span class="publication-type">{html.escape(ptype)}</span>')
    if status:
        lines.append(f'    <span class="publication-status">{html.escape(status)}</span>')
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

        section = publication_section(entry)
        year = clean(entry.get("year")) or "n.d."
        grouped[section][year].append(entry)

    output = [
        "<!-- AUTO-GENERATED by scripts/build_publications.py. DO NOT EDIT. -->",
        '<div class="publications-list">',
    ]

    for section in SECTION_ORDER:
        if section not in grouped:
            continue

        output.append(f'<section class="publication-section" id="{section}">')
        output.append(f"  <h2>{html.escape(SECTION_TITLES[section])}</h2>")

        years = sorted(
            grouped[section].keys(),
            key=lambda y: (y != "n.d.", int(y) if y.isdigit() else -1),
            reverse=True,
        )

        for year in years:
            output.append(f'  <h3 class="publication-year">{html.escape(year)}</h3>')

            entries = sorted(
                grouped[section][year],
                key=lambda e: clean(e.get("title")).lower(),
            )

            for entry in entries:
                output.append(render_entry(entry))

        output.append("</section>")

    output.append("</div>")
    OUTPUT_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")

    total = sum(len(entries) for section in grouped.values() for entries in section.values())
    print(f"Generated {OUTPUT_FILE.relative_to(ROOT)} from {BIB_FILE.relative_to(ROOT)} ({total} entries)")


if __name__ == "__main__":
    main()
