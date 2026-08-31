#!/usr/bin/env python3
"""Build and verify the MS #1-44 customer documentation library."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs" / "milestones"
CATALOG_PATH = DOC_ROOT / "catalog.json"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
MANIFEST_PATH = DOC_ROOT / "manifest.json"
GENERATOR_VERSION = "1.0"
FIXED_TIME = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
EXPECTED_MILESTONES = tuple(range(1, 45))
BOUNDARY_TERMS = (
    "remain false", "remains false", "remain blocked", "remains blocked",
    "unclaimed", "not claim", "does not", "no customer", "non-production",
    "kept native", "kept all live", "kept every", "cannot satisfy", "excluded",
)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_catalog() -> dict[str, Any]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    numbers = [entry["number"] for entry in catalog["milestones"]]
    if numbers != list(EXPECTED_MILESTONES):
        raise ValueError(f"catalog must contain MS #1-44 exactly; found {numbers}")
    return catalog


def parse_changelog() -> dict[int, list[dict[str, Any]]]:
    sections: dict[int, list[dict[str, Any]]] = {}
    current: dict[str, Any] | None = None
    current_item: list[str] | None = None
    header = re.compile(r"^## 0\.(\d+)\.(\d+)\s+.+?\s+(\d{4}-\d{2}-\d{2})$")
    for raw in CHANGELOG_PATH.read_text(encoding="utf-8").splitlines():
        match = header.match(raw)
        if match:
            minor, patch, date = int(match.group(1)), int(match.group(2)), match.group(3)
            current = {"version": f"0.{minor}.{patch}", "patch": patch, "date": date, "items": []}
            sections.setdefault(minor, []).append(current)
            current_item = None
        elif current is not None and raw.startswith("- "):
            current_item = [raw[2:].strip()]
            current["items"].append(current_item)
        elif current_item is not None and raw.startswith("  "):
            current_item.append(raw.strip())
        elif not raw.strip():
            current_item = None
    normalized: dict[int, list[dict[str, Any]]] = {}
    for minor, releases in sections.items():
        normalized[minor] = []
        for release in sorted(releases, key=lambda row: row["patch"]):
            normalized[minor].append({**release, "items": [" ".join(parts) for parts in release["items"]]})
    return normalized


def plain(text: str) -> str:
    return (
        re.sub(r"`([^`]+)`", r"\1", text)
        .replace("\u2192", "to")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2011", "-")
    )


def finish_sentence(text: str) -> str:
    value = plain(text).strip()
    return value if value.endswith((".", "!", "?")) else value + "."


def build_model(
    entry: dict[str, Any], releases: dict[int, list[dict[str, Any]]], titles: dict[int, str]
) -> dict[str, Any]:
    number = entry["number"]
    release_rows = releases.get(number, [])
    deliverables = list(entry.get("deliverables", [])) or [
        item for release in release_rows for item in release["items"]
    ]
    if not deliverables:
        raise ValueError(f"MS #{number} has no deliverables")
    if "release" in entry:
        release_label, date_label = entry["release"], entry["date"]
    else:
        release_label = ", ".join(row["version"] for row in release_rows)
        date_label = (
            f"{release_rows[0]['date']} to {release_rows[-1]['date']}"
            if len(release_rows) > 1 else release_rows[0]["date"]
        )
    boundaries = list(entry.get("boundaries", [])) or [
        item for item in deliverables if any(term in item.lower() for term in BOUNDARY_TERMS)
    ]
    if not boundaries:
        boundaries = [
            "This milestone establishes only the bounded capabilities and evidence listed here; later capabilities are not retroactive.",
            "Production readiness and platform equivalence require the explicit evidence and policy gates applicable to the customer environment.",
        ]
    relationship = (
        "This is the starting engineering milestone. It creates the executable behavioral reference that later graph, factory, qualification, and customer-pilot work can govern."
        if number == 1
        else f"MS #{number} builds on MS #{number - 1} ({titles[number - 1]}). The earlier milestone established its own bounded capability; this milestone adds {entry['title'].lower()} while preserving the earlier evidence and its limits."
    )
    return {
        **entry,
        "status": "Complete",
        "release": release_label,
        "date": date_label,
        "deliverables": [finish_sentence(item) for item in deliverables],
        "boundaries": [finish_sentence(item) for item in boundaries],
        "relationship": relationship,
        "executive_summary": (
            f"MS #{number} - {entry['title']} converts a specific part of the LIGHTYEAR modernization approach "
            f"into a governed, reviewable capability. {entry['customer_value']}"
        ),
    }


def markdown_text(model: dict[str, Any], audience: str) -> str:
    number = model["number"]
    lines = [
        f"# MS #{number:02d} - {model['title']}", "",
        f"> **Status:** {model['status']}", ">", f"> **Release:** {model['release']}", ">",
        f"> **Date:** {model['date']}", ">", f"> **Audience:** {audience}", "",
        "## Executive summary", "", model["executive_summary"], "",
        "## Why this matters to a customer", "", model["customer_value"], "",
        "The practical result is a narrower, evidence-backed decision instead of a broad modernization claim. "
        "The milestone packages capability, proof, and limitations together so commercial, architecture, "
        "delivery, security, and assurance teams can review the same record.", "",
        "## What the milestone delivers", "",
    ]
    lines.extend(f"- {item}" for item in model["deliverables"])
    lines.extend([
        "", "## How it differs from earlier work", "", model["relationship"], "",
        "Earlier work remains useful evidence, but it is not automatically promoted into this milestone. "
        "A successful parser, simulator, local comparison, or generated artifact is not presented as live "
        "platform equivalence or production readiness.", "",
        "## What a customer can do with it", "",
        f"A customer can use {model['title'].lower()} as a bounded decision and delivery capability. "
        "It can be attached to the customer's approved source package, owners, policies, target architecture, "
        "acceptance criteria, and authorized evidence.", "",
        "Unresolved semantic loss, policy decisions, unsupported behavior, and live-evidence requirements remain "
        "visible rather than being averaged into one pass/fail statement.", "",
        "## Evidence and acceptance posture", "",
        "The milestone is complete as a repository capability because its committed implementation and release "
        "record are present. Customer qualification remains claim-specific: only the delivered behaviors listed "
        "above are supported, and only at the evidence class recorded by their underlying receipts and gates.", "",
        "A customer review should confirm:", "",
        "1. the exact source, graph, policy, fixture, and artifact identities referenced by the evidence;",
        "2. the difference between deterministic development evidence and authorized live evidence;",
        "3. every policy decision, lossy transformation, unsupported behavior, and explicit exclusion;",
        "4. the acceptance gates that passed and the live or production gates that remain blocked; and",
        "5. that later changes have not invalidated the content-addressed evidence.", "",
        "## Boundaries and claims not made", "",
    ])
    lines.extend(f"- {item}" for item in model["boundaries"])
    lines.extend([
        "", "These boundaries are part of the deliverable. They prevent bounded development evidence from becoming "
        "an unsupported customer promise.", "", "## Source of record", "",
        f"- Release record: [CHANGELOG.md](../../../CHANGELOG.md), release section(s) {model['release']}.",
        "- Product and operating guidance: [README.md](../../../README.md).",
        "- Governing sequence and claim classifications: [LIGHTYEAR-ROADMAP.md](../../../LIGHTYEAR-ROADMAP.md).",
        "- Machine-readable milestone metadata: [catalog.json](../catalog.json).",
        "- Artifact integrity: [manifest.json](../manifest.json).", "", "---", "",
        "This document is a customer-readable explanation of committed repository evidence. The underlying schemas, "
        "receipts, ledgers, tests, and policy decisions remain authoritative when greater detail is required.", "",
    ])
    return "\n".join(lines)


def set_run_font(run: Any, name: str = "Calibri") -> None:
    from docx.oxml.ns import qn
    run.font.name = name
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn("w:ascii"), name)
    fonts.set(qn("w:hAnsi"), name)


def set_table_geometry(table: Any, widths: list[int], indent: int = 120) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    total = sum(widths)
    table.autofit = False
    properties = table._tbl.tblPr
    for name in ("tblW", "tblInd", "tblLayout"):
        for child in list(properties):
            if child.tag == qn(f"w:{name}"):
                properties.remove(child)
    for name, attrs in (
        ("tblW", {"w:w": str(total), "w:type": "dxa"}),
        ("tblInd", {"w:w": str(indent), "w:type": "dxa"}),
        ("tblLayout", {"w:type": "fixed"}),
    ):
        element = OxmlElement(f"w:{name}")
        for key, value in attrs.items():
            element.set(qn(key), value)
        properties.append(element)
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        column = OxmlElement("w:gridCol")
        column.set(qn("w:w"), str(width))
        grid.append(column)
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            cell.width = width
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.first_child_found_in("w:tcW")
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")
            margins = tc_pr.first_child_found_in("w:tcMar")
            if margins is None:
                margins = OxmlElement("w:tcMar")
                tc_pr.append(margins)
            for side, value in (("top", 80), ("bottom", 80), ("start", 120), ("end", 120)):
                part = margins.find(qn(f"w:{side}"))
                if part is None:
                    part = OxmlElement(f"w:{side}")
                    margins.append(part)
                part.set(qn("w:w"), str(value))
                part.set(qn("w:type"), "dxa")


def shade_cell(cell: Any, fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), fill)


def add_page_field(paragraph: Any) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    run = paragraph.add_run()
    for tag, value in (("fldChar", "begin"), ("instrText", " PAGE "), ("fldChar", "separate"), ("t", "1"), ("fldChar", "end")):
        node = OxmlElement(f"w:{tag}")
        if tag == "fldChar":
            node.set(qn("w:fldCharType"), value)
        else:
            node.text = value
        run._r.append(node)


def normalize_docx(source: Path, output: Path) -> None:
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
        for name in sorted(zin.namelist()):
            info = zipfile.ZipInfo(name, (2026, 8, 31, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zout.writestr(info, zin.read(name))


def build_docx(model: dict[str, Any], audience: str, output: Path) -> None:
    try:
        from docx import Document
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt, RGBColor
    except ImportError as exc:
        raise RuntimeError("DOCX build requires python-docx; install the docs optional dependencies") from exc
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.right_margin = section.bottom_margin = section.left_margin = Inches(1)
    section.header_distance = section.footer_distance = Inches(0.492)
    normal = document.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(11)
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:ascii"), "Calibri")
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:hAnsi"), "Calibri")
    normal.paragraph_format.space_after, normal.paragraph_format.line_spacing = Pt(6), 1.10
    for name, size, color, before, after in (
        ("Heading 1", 16, "2E74B5", 16, 8), ("Heading 2", 13, "2E74B5", 12, 6),
        ("Heading 3", 12, "1F4D78", 8, 4),
    ):
        style = document.styles[name]
        style.font.name, style.font.size, style.font.bold = "Calibri", Pt(size), True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before, style.paragraph_format.space_after = Pt(before), Pt(after)
        style.paragraph_format.keep_with_next = True
    for name in ("List Bullet", "List Number"):
        style = document.styles[name]
        style.font.name, style.font.size = "Calibri", Pt(11)
        style.paragraph_format.left_indent, style.paragraph_format.first_line_indent = Inches(0.5), Inches(-0.25)
        style.paragraph_format.space_after, style.paragraph_format.line_spacing = Pt(8), 1.167
    header = section.header.paragraphs[0]
    run = header.add_run("LIGHTYEAR  |  MILESTONE DOCUMENTATION")
    set_run_font(run)
    run.font.size, run.font.bold, run.font.color.rgb = Pt(8.5), True, RGBColor.from_string("6B7280")
    border = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("w:val", "single"), ("w:sz", "6"), ("w:space", "3"), ("w:color", "D7DBE2")):
        bottom.set(qn(key), value)
    border.append(bottom)
    header._p.get_or_add_pPr().append(border)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run(f"MS #{model['number']:02d}  |  Page ")
    set_run_font(run)
    run.font.size, run.font.color.rgb = Pt(8.5), RGBColor.from_string("6B7280")
    add_page_field(footer)
    kicker = document.add_paragraph()
    kicker.paragraph_format.space_after = Pt(0)
    run = kicker.add_run("CUSTOMER MILESTONE BRIEF")
    set_run_font(run)
    run.font.size, run.font.bold, run.font.color.rgb = Pt(9), True, RGBColor.from_string("9A6B16")
    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(8)
    run = title.add_run(f"MS #{model['number']:02d} - {plain(model['title'])}")
    set_run_font(run)
    run.font.size, run.font.bold, run.font.color.rgb = Pt(28), True, RGBColor.from_string("0B2545")
    subtitle = document.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(18)
    run = subtitle.add_run("Purpose, customer value, delivered capability, evidence, and claim boundaries")
    set_run_font(run)
    run.font.size, run.font.color.rgb = Pt(13.5), RGBColor.from_string("4B5563")
    table = document.add_table(rows=4, cols=2)
    table.style = "Table Grid"
    set_table_geometry(table, [2700, 6660])
    metadata = (("Status", model["status"]), ("Release", model["release"]), ("Date", model["date"]), ("Audience", audience))
    for row, (label, value) in zip(table.rows, metadata):
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shade_cell(row.cells[0], "F2F4F7")
        label_run = row.cells[0].paragraphs[0].add_run(label)
        set_run_font(label_run)
        label_run.bold, label_run.font.color.rgb = True, RGBColor.from_string("1F4D78")
        value_run = row.cells[1].paragraphs[0].add_run(plain(value))
        set_run_font(value_run)
    content = [
        ("Executive summary", [model["executive_summary"]], False),
        ("Why this matters to a customer", [model["customer_value"], "The practical result is a narrower, evidence-backed decision instead of a broad modernization claim. Commercial, architecture, delivery, security, and assurance teams can review the same capability, proof, and limits."], False),
        ("What the milestone delivers", model["deliverables"], True),
        ("How it differs from earlier work", [model["relationship"], "Earlier evidence is not automatically promoted into this milestone. A parser, simulator, local comparison, or generated artifact is not live platform equivalence or production readiness."], False),
        ("What a customer can do with it", [f"A customer can use {model['title'].lower()} as a bounded decision and delivery capability, attached to approved sources, owners, policies, target architecture, acceptance criteria, and authorized evidence.", "Unresolved semantic loss, policy decisions, unsupported behavior, and live-evidence requirements remain visible."], False),
        ("Evidence and acceptance posture", ["The repository capability is complete because its committed implementation and release record are present. Customer qualification remains claim-specific and evidence-class-specific.", "Review exact source and artifact identities, distinguish development from authorized live evidence, inspect policy and loss classifications, confirm passed and blocked gates, and verify that later changes have not invalidated the evidence."], False),
        ("Boundaries and claims not made", model["boundaries"], True),
        ("Source of record", [f"CHANGELOG.md release section(s): {model['release']}", "README.md product and operating guidance", "LIGHTYEAR-ROADMAP.md governing sequence and claim classifications", "docs/milestones/catalog.json metadata and docs/milestones/manifest.json artifact integrity"], True),
    ]
    for heading, values, bullets in content:
        document.add_heading(heading, level=1)
        for value in values:
            document.add_paragraph(plain(value), style="List Bullet" if bullets else None)
    note = document.add_paragraph()
    note.paragraph_format.space_before = Pt(10)
    run = note.add_run("The underlying schemas, receipts, ledgers, tests, and policy decisions remain authoritative when greater detail is required.")
    set_run_font(run)
    run.italic, run.font.size, run.font.color.rgb = True, Pt(9), RGBColor.from_string("6B7280")
    properties = document.core_properties
    properties.title, properties.subject, properties.author = f"MS #{model['number']:02d} - {plain(model['title'])}", "LIGHTYEAR customer milestone documentation", "LIGHTYEAR"
    properties.created = properties.modified = FIXED_TIME.replace(tzinfo=None)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="milestone-docx-") as temp:
        raw = Path(temp) / output.name
        document.save(raw)
        normalize_docx(raw, output)


def build_pdf(model: dict[str, Any], audience: str, output: Path) -> None:
    try:
        import reportlab
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("PDF build requires reportlab; install the docs optional dependencies") from exc
    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    for name, filename in (("LYSans", "Vera.ttf"), ("LYSans-Bold", "VeraBd.ttf"), ("LYSans-Italic", "VeraIt.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="LYSans", fontSize=10.3, leading=13.2, spaceAfter=6, textColor=colors.HexColor("#111827"))
    heading = ParagraphStyle("H1", parent=styles["Heading1"], fontName="LYSans-Bold", fontSize=15, leading=18, textColor=colors.HexColor("#2E74B5"), spaceBefore=14, spaceAfter=7, keepWithNext=True)
    bullet = ParagraphStyle("Bullet", parent=body, leftIndent=18, firstLineIndent=-10, spaceAfter=6)
    label = ParagraphStyle("Label", parent=body, fontName="LYSans-Bold", textColor=colors.HexColor("#1F4D78"), spaceAfter=0)
    value = ParagraphStyle("Value", parent=body, spaceAfter=0)
    def safe(text: str) -> str:
        return html.escape(plain(text))
    def furniture(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D7DBE2")); canvas.setLineWidth(0.5)
        canvas.line(inch, LETTER[1] - 0.58 * inch, LETTER[0] - inch, LETTER[1] - 0.58 * inch)
        canvas.setFillColor(colors.HexColor("#6B7280")); canvas.setFont("LYSans-Bold", 8)
        canvas.drawString(inch, LETTER[1] - 0.48 * inch, "LIGHTYEAR  |  MILESTONE DOCUMENTATION")
        canvas.setFont("LYSans", 8)
        canvas.drawRightString(LETTER[0] - inch, 0.48 * inch, f"MS #{model['number']:02d}  |  Page {doc.page}")
        canvas.restoreState()
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output), pagesize=LETTER, rightMargin=inch, leftMargin=inch, topMargin=0.82 * inch, bottomMargin=0.72 * inch, title=f"MS #{model['number']:02d} - {plain(model['title'])}", author="LIGHTYEAR", subject="LIGHTYEAR customer milestone documentation", invariant=1, pageCompression=1)
    story: list[Any] = [Spacer(1, 8)]
    story.append(Paragraph("CUSTOMER MILESTONE BRIEF", ParagraphStyle("Kicker", parent=body, fontName="LYSans-Bold", fontSize=8.5, textColor=colors.HexColor("#9A6B16"), spaceAfter=2)))
    story.append(Paragraph(f"MS #{model['number']:02d} - {safe(model['title'])}", ParagraphStyle("Title", parent=styles["Title"], fontName="LYSans-Bold", fontSize=24, leading=28, textColor=colors.HexColor("#0B2545"), spaceAfter=7)))
    story.append(Paragraph("Purpose, customer value, delivered capability, evidence, and claim boundaries", ParagraphStyle("Subtitle", parent=body, fontSize=12, leading=15, textColor=colors.HexColor("#4B5563"), spaceAfter=14)))
    rows = [[Paragraph(k, label), Paragraph(safe(v), value)] for k, v in (("Status", model["status"]), ("Release", model["release"]), ("Date", model["date"]), ("Audience", audience))]
    table = Table(rows, colWidths=[1.55 * inch, 4.95 * inch], hAlign="LEFT")
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#D7DBE2")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F4F7")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(table)
    content = [
        ("Executive summary", [model["executive_summary"]], False),
        ("Why this matters to a customer", [model["customer_value"], "The practical result is a narrower, evidence-backed decision instead of a broad modernization claim. Commercial, architecture, delivery, security, and assurance teams can review the same capability, proof, and limits."], False),
        ("What the milestone delivers", model["deliverables"], True),
        ("How it differs from earlier work", [model["relationship"], "Earlier evidence is not automatically promoted into this milestone. A parser, simulator, local comparison, or generated artifact is not live platform equivalence or production readiness."], False),
        ("What a customer can do with it", [f"A customer can use {model['title'].lower()} as a bounded decision and delivery capability, attached to approved sources, owners, policies, target architecture, acceptance criteria, and authorized evidence.", "Unresolved semantic loss, policy decisions, unsupported behavior, and live-evidence requirements remain visible."], False),
        ("Evidence and acceptance posture", ["The repository capability is complete because its committed implementation and release record are present. Customer qualification remains claim-specific and evidence-class-specific.", "Review exact source and artifact identities, distinguish development from authorized live evidence, inspect policy and loss classifications, confirm passed and blocked gates, and verify that later changes have not invalidated the evidence."], False),
        ("Boundaries and claims not made", model["boundaries"], True),
        ("Source of record", [f"CHANGELOG.md release section(s): {model['release']}", "README.md product and operating guidance", "LIGHTYEAR-ROADMAP.md governing sequence and claim classifications", "docs/milestones/catalog.json metadata and docs/milestones/manifest.json artifact integrity"], True),
    ]
    for title, values, bullets in content:
        story.append(Paragraph(safe(title), heading))
        for item in values:
            story.append(Paragraph(("-  " if bullets else "") + safe(item), bullet if bullets else body))
    story.append(Spacer(1, 8))
    story.append(Paragraph("The underlying schemas, receipts, ledgers, tests, and policy decisions remain authoritative when greater detail is required.", ParagraphStyle("Note", parent=body, fontName="LYSans-Italic", fontSize=8.7, leading=11, textColor=colors.HexColor("#6B7280"))))
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)


def source_sha256() -> str:
    digest = hashlib.sha256()
    for path in (Path(__file__).resolve(), CATALOG_PATH, CHANGELOG_PATH):
        digest.update(path.relative_to(ROOT).as_posix().encode()); digest.update(b"\0")
        digest.update(path.read_bytes()); digest.update(b"\0")
    return digest.hexdigest()


def write_index(models: list[dict[str, Any]]) -> None:
    lines = [
        "# LIGHTYEAR milestone documentation library", "",
        "This library is the customer-readable body of record for MS #1 through MS #44. Every milestone is",
        "published from one governed catalog in Markdown, Microsoft Word (`.docx`), and PDF.", "",
        "The documents explain purpose, customer value, delivered capability, evidence posture, limitations, and",
        "the relationship to earlier work. They do not override the underlying schemas, receipts, ledgers, tests,",
        "or policy decisions.", "", "## Milestone index", "",
        "| Milestone | Title | Status | Formats |", "|---|---|---|---|",
    ]
    for model in models:
        stem = f"MS-{model['number']:02d}"
        lines.append(f"| MS #{model['number']:02d} | {model['title']} | {model['status']} | [Markdown]({stem}/{stem}.md) - [Word]({stem}/{stem}.docx) - [PDF]({stem}/{stem}.pdf) |")
    lines.extend(["", "## Build and verification", "", "```bash", "./milestone-documentation.sh verify", "./milestone-documentation.sh build", "```", "", "Windows:", "", "```powershell", ".\\milestone-documentation.ps1 verify", ".\\milestone-documentation.ps1 build", "```", "", "`verify` uses only the Python standard library. `build` requires the `docs` optional dependency set.", "", "The content-addressed [manifest](manifest.json) fails verification if a canonical source changes, an artifact is missing or modified, or an untracked milestone artifact appears.", ""])
    (DOC_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def build() -> None:
    catalog, releases = load_catalog(), parse_changelog()
    titles = {entry["number"]: entry["title"] for entry in catalog["milestones"]}
    models = [build_model(entry, releases, titles) for entry in catalog["milestones"]]
    expected = {f"MS-{number:02d}" for number in EXPECTED_MILESTONES}
    for path in DOC_ROOT.glob("MS-*"):
        if path.is_dir() and path.name not in expected:
            shutil.rmtree(path)
    for model in models:
        stem = f"MS-{model['number']:02d}"; directory = DOC_ROOT / stem
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{stem}.md").write_text(markdown_text(model, catalog["audience"]), encoding="utf-8")
        build_docx(model, catalog["audience"], directory / f"{stem}.docx")
        build_pdf(model, catalog["audience"], directory / f"{stem}.pdf")
    write_index(models)
    artifacts = []
    for number in EXPECTED_MILESTONES:
        stem = f"MS-{number:02d}"
        for suffix in (".md", ".docx", ".pdf"):
            path = DOC_ROOT / stem / f"{stem}{suffix}"
            artifacts.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_path(path)})
    manifest = {"schema_version": "1.0", "generator_version": GENERATOR_VERSION, "source_sha256": source_sha256(), "milestone_count": 44, "artifact_count": 132, "formats": ["md", "docx", "pdf"], "artifacts": artifacts}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "built", "milestones": 44, "artifacts": 132}, sort_keys=True))


def verify() -> None:
    load_catalog()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")); errors = []
    if manifest.get("source_sha256") != source_sha256(): errors.append("documentation sources changed without regeneration")
    if manifest.get("milestone_count") != 44: errors.append("manifest milestone count is not 44")
    if manifest.get("artifact_count") != 132: errors.append("manifest artifact count is not 132")
    declared = set()
    for artifact in manifest.get("artifacts", []):
        relative = artifact["path"]; declared.add(relative); path = ROOT / relative
        if not path.is_file(): errors.append(f"missing artifact: {relative}"); continue
        if path.stat().st_size != artifact["bytes"]: errors.append(f"size mismatch: {relative}")
        if sha256_path(path) != artifact["sha256"]: errors.append(f"hash mismatch: {relative}")
    actual = {path.relative_to(ROOT).as_posix() for path in DOC_ROOT.glob("MS-*/*") if path.is_file() and path.suffix in {".md", ".docx", ".pdf"}}
    errors.extend(f"undeclared artifact: {path}" for path in sorted(actual - declared))
    errors.extend(f"declared artifact missing: {path}" for path in sorted(declared - actual))
    if errors:
        raise SystemExit("Milestone documentation verification failed:\n- " + "\n- ".join(errors))
    print(json.dumps({"status": "verified", "milestones": 44, "artifacts": 132}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify")); args = parser.parse_args()
    build() if args.command == "build" else verify()


if __name__ == "__main__":
    main()
