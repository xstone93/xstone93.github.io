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
    Spacer,
)

from build_publications import (
    OWN_NAME,
    SECTION_ORDER,
    SECTION_TITLES,
    TYPE_LABELS,
    clean,
    keywords,
    publication_section,
    publication_type,
    venue,
)

ROOT = Path(__file__).resolve().parents[1]
BIB_FILE = ROOT / "_bibliography" / "publications.bib"
OUTPUT_FILE = ROOT / "files" / "publications.pdf"


def pdf_authors(author: str) -> str:
    """Format BibTeX authors and underline the site owner's name."""
    people = []
    for raw_person in (part.strip() for part in author.split(" and ")):
        if not raw_person:
            continue
        person = clean(raw_person)
        if "," in person:
            last, first = (part.strip() for part in person.split(",", 1))
            display = f"{first} {last}"
        else:
            display = person
        escaped = html.escape(display)
        if OWN_NAME.lower() in display.lower():
            escaped = f"<u>{escaped}</u>"
        people.append(escaped)

    if len(people) == 1:
        return people[0]
    if len(people) == 2:
        return f"{people[0]} &amp; {people[1]}"
    return ", ".join(people[:-1]) + f", &amp; {people[-1]}"


def pdf_venue(entry: dict) -> str:
    """Reuse the HTML generator's venue normalization as plain text."""
    return html.unescape(venue(entry))


def entry_links(entry: dict) -> str:
    links = []
    doi = clean(entry.get("doi"))
    if doi:
        url = f"https://doi.org/{doi}"
        links.append(f'<link href="{html.escape(url, quote=True)}">DOI: {html.escape(doi)}</link>')
    elif clean(entry.get("url")):
        url = clean(entry.get("url"))
        links.append(f'<link href="{html.escape(url, quote=True)}">Online</link>')
    return "  |  ".join(links)


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
        spaceAfter=1.5 * mm,
    )
    link_style = ParagraphStyle(
        "Links",
        parent=citation_style,
        fontSize=7.8,
        leading=10,
        textColor=colors.HexColor("#175CD3"),
        spaceAfter=3.5 * mm,
    )
    note_style = ParagraphStyle(
        "Note",
        parent=citation_style,
        fontName="Helvetica-Bold",
        fontSize=8.2,
        leading=10.5,
        textColor=colors.HexColor("#9A3412"),
        spaceAfter=1.5 * mm,
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
            entries = sorted(grouped[section][year], key=lambda item: clean(item.get("title")).lower())
            for entry in entries:
                title = html.escape(clean(entry.get("title")) or "Untitled")
                authors = pdf_authors(entry.get("author", ""))
                place = html.escape(pdf_venue(entry))
                kind = html.escape(TYPE_LABELS[publication_type(entry)])
                citation_parts = [f"<b>{title}</b>", authors]
                if place:
                    citation_parts.append(f"<i>{place}</i>")
                citation_parts.append(f"{kind}, {html.escape(year)}")
                content = [Paragraph("<br/>".join(citation_parts), citation_style)]
                note = clean(entry.get("note"))
                if note:
                    content.append(Paragraph(f"Note: {html.escape(note)}", note_style))
                links = entry_links(entry)
                if links:
                    content.append(Paragraph(links, link_style))
                else:
                    content.append(Spacer(1, 2 * mm))
                story.append(KeepTogether(content))

    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"Generated {OUTPUT_FILE.relative_to(ROOT)} from {BIB_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
