#!/usr/bin/env python3
"""Generate a CV-ready publication-list PDF from the master BibTeX file."""

from __future__ import annotations

import html
from collections import defaultdict
from datetime import date
from pathlib import Path

import bibtexparser
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
)

from build_publications import (
    OWN_NAME,
    SECTION_ORDER,
    SECTION_TITLES,
    clean,
    keywords,
    publication_section,
    publication_type,
)

ROOT = Path(__file__).resolve().parents[1]
BIB_FILE = ROOT / "_bibliography" / "publications.bib"
OUTPUT_FILE = ROOT / "files" / "publications.pdf"


def initials(given_names: str) -> str:
    """Convert given names to APA-style initials while retaining hyphens."""
    result = []
    for name in given_names.replace(".", "").split():
        parts = [part for part in name.split("-") if part]
        if not parts:
            continue
        result.append("-".join(f"{part[0].upper()}." for part in parts))
    return " ".join(result)


def person_parts(raw_person: str) -> tuple[str, str]:
    person = clean(raw_person)
    if "," in person:
        family, given = (part.strip() for part in person.split(",", 1))
    else:
        pieces = person.split()
        family, given = pieces[-1], " ".join(pieces[:-1])
    return family, given


def apa_authors(author: str) -> str:
    """Format up to 20 authors according to APA 7 reference-list rules."""
    raw_people = [part.strip() for part in author.split(" and ") if part.strip()]
    rendered = []
    for raw_person in raw_people:
        family, given = person_parts(raw_person)
        display = f"{family}, {initials(given)}".strip()
        escaped = html.escape(display)
        normalized = f"{given} {family}".strip()
        if OWN_NAME.lower() in normalized.lower():
            escaped = f"<u>{escaped}</u>"
        rendered.append(escaped)

    if len(rendered) > 20:
        rendered = rendered[:19] + ["...", rendered[-1]]
    if len(rendered) == 1:
        return rendered[0]
    return ", ".join(rendered[:-1]) + f", &amp; {rendered[-1]}"


def apa_editors(editor: str) -> str:
    rendered = []
    for raw_person in (part.strip() for part in editor.split(" and ") if part.strip()):
        family, given = person_parts(raw_person)
        rendered.append(f"{html.escape(initials(given))} {html.escape(family)}")
    if not rendered:
        return ""
    if len(rendered) == 1:
        names = rendered[0]
    else:
        names = ", ".join(rendered[:-1]) + f", &amp; {rendered[-1]}"
    role = "Ed." if len(rendered) == 1 else "Eds."
    return f"{names} ({role}), " if rendered else ""


def page_range(entry: dict, *, parenthetical: bool = False) -> str:
    pages = clean(entry.get("pages")).replace("--", "-")
    if not pages:
        return ""
    return f"(pp. {html.escape(pages)})" if parenthetical else html.escape(pages)


def apa_source(entry: dict) -> str:
    """Return the APA source element appropriate for this BibTeX type."""
    entry_type = clean(entry.get("ENTRYTYPE")).lower()
    ptype = publication_type(entry)
    journal = clean(entry.get("journal"))
    booktitle = clean(entry.get("booktitle"))
    volume = clean(entry.get("volume"))
    number = clean(entry.get("number"))
    eid = clean(entry.get("eid"))
    publisher = clean(entry.get("publisher"))

    if ptype in {"preprint", "manuscript"}:
        descriptor = "Preprint" if ptype == "preprint" else "Unpublished manuscript"
        source_name = journal or clean(entry.get("institution"))
        result = f"[{descriptor}]."
        if source_name:
            result += f" {html.escape(source_name)}."
        return result

    if entry_type == "article" and journal:
        source = f"<i>{html.escape(journal)}</i>"
        if volume:
            source += f", <i>{html.escape(volume)}</i>"
            if number:
                source += f"({html.escape(number)})"
        pages = page_range(entry)
        if pages:
            source += f", {pages}"
        elif eid:
            source += f", Article {html.escape(eid)}"
        return source + "."

    if entry_type in {"inproceedings", "conference", "incollection", "inbook"}:
        editor = apa_editors(entry.get("editor", ""))
        source = f"In {editor}<i>{html.escape(booktitle or publisher)}</i>"
        pages = page_range(entry, parenthetical=True)
        if pages:
            source += f" {pages}"
        source += "."
        if publisher and publisher.lower() != (booktitle or "").lower():
            source += f" {html.escape(publisher)}."
        return source

    return ""


def apa_url(entry: dict) -> str:
    doi = clean(entry.get("doi"))
    if doi:
        url = f"https://doi.org/{doi}"
    else:
        url = clean(entry.get("url"))
    if not url:
        return ""
    escaped_url = html.escape(url, quote=True)
    return f'<link href="{escaped_url}" color="#175CD3">{html.escape(url)}</link>'


def apa_note(entry: dict) -> str:
    """Keep informative notes, but omit status text already expressed by APA."""
    note = clean(entry.get("note"))
    if not note:
        return ""
    status_phrases = (
        "manuscript",
        "submitted",
        "under review",
        "under revision",
        "in preparation",
        "preprint",
        "accepted",
        "in press",
    )
    if publication_type(entry) in {"preprint", "manuscript"} and any(
        phrase in note.lower() for phrase in status_phrases
    ):
        return ""
    return f'<font color="#9A3412"><b>[{html.escape(note)}]</b></font>'


def apa_reference(entry: dict) -> str:
    authors = apa_authors(entry.get("author", ""))
    year = html.escape(clean(entry.get("year")) or "n.d.")
    title = html.escape(clean(entry.get("title")) or "Untitled")
    if publication_type(entry) in {"preprint", "manuscript"}:
        title = f"<i>{title}</i>"
    title_suffix = "" if clean(entry.get("title")).endswith((".", "?", "!")) else "."
    parts = [f"{authors} ({year}).", f"{title}{title_suffix}", apa_source(entry)]
    url = apa_url(entry)
    if url:
        parts.append(url)
    note = apa_note(entry)
    if note:
        parts.append(note)
    return " ".join(part for part in parts if part)


def author_sort_key(entry: dict) -> tuple[str, str]:
    first_author = entry.get("author", "").split(" and ", 1)[0]
    family, given = person_parts(first_author)
    return family.lower(), given.lower()


def page_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D5D9DE"))
    canvas.line(22 * mm, 15 * mm, A4[0] - 22 * mm, 15 * mm)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(22 * mm, 10 * mm, "Alexander Steinmaurer - Publication List")
    canvas.drawRightString(A4[0] - 22 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def main() -> None:
    with BIB_FILE.open(encoding="utf-8") as source:
        database = bibtexparser.load(source)

    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for entry in database.entries:
        if "private" in keywords(entry):
            continue
        grouped[publication_section(entry)][clean(entry.get("year")) or "n.d."].append(entry)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT_FILE),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=19 * mm,
        bottomMargin=22 * mm,
        title="Alexander Steinmaurer - Publications",
        author="Alexander Steinmaurer",
    )

    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PublicationTitlePage",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#182230"),
        spaceAfter=5 * mm,
    )
    updated_style = ParagraphStyle(
        "Updated",
        parent=base["Normal"],
        alignment=TA_CENTER,
        fontSize=8.5,
        textColor=colors.HexColor("#667085"),
        spaceAfter=8 * mm,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#173F5F"),
        spaceBefore=5 * mm,
        spaceAfter=2.5 * mm,
        keepWithNext=True,
    )
    year_style = ParagraphStyle(
        "Year",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#344054"),
        spaceBefore=3 * mm,
        spaceAfter=1.5 * mm,
        keepWithNext=True,
    )
    citation_style = ParagraphStyle(
        "Citation",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=8.8,
        leading=12.2,
        textColor=colors.HexColor("#182230"),
        leftIndent=7 * mm,
        firstLineIndent=-7 * mm,
        spaceAfter=3.5 * mm,
    )
    story = [
        Paragraph("Alexander Steinmaurer - Publication List", title_style),
        Paragraph(f"Updated {date.today().strftime('%d %B %Y')}", updated_style),
    ]

    for section in SECTION_ORDER:
        if section not in grouped:
            continue
        story.append(Paragraph(html.escape(SECTION_TITLES[section]), section_style))

        years = sorted(
            grouped[section],
            key=lambda year: (year != "n.d.", int(year) if year.isdigit() else -1),
            reverse=True,
        )
        for year in years:
            story.append(Paragraph(html.escape(year), year_style))
            entries = sorted(grouped[section][year], key=author_sort_key)
            for entry in entries:
                content = [Paragraph(apa_reference(entry), citation_style)]
                story.append(KeepTogether(content))

    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"Generated {OUTPUT_FILE.relative_to(ROOT)} from {BIB_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
