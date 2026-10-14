"""Build Word companions from canonical supplemental milestone Markdown.

Install the docs extra, then render the Word files to PDF with LibreOffice.
Inspect all rendered pages before publishing and run the library build/verify.
No source record or historical evidence is rewritten by this command.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / 'docs/milestones'
GITHUB = 'https://github.com/howardweale/lightyear-carddemo-modernization/blob/main/'


def build_word(source):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
    from markdown_it import MarkdownIt

    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(.7)
    section.left_margin = section.right_margin = Inches(.75)
    section.header_distance = section.footer_distance = Inches(.3)
    styles = document.styles
    for style in styles:
        for border in list(style.element.iter(qn('w:pBdr'))):
            border.getparent().remove(border)
    for name in ['Normal', 'Title', 'Subtitle', 'Heading 1', 'Heading 2', 'Heading 3',
                 'List Bullet', 'List Number', 'Caption']:
        styles[name].font.name = 'Arial'
        styles[name].font.color.rgb = RGBColor(0, 0, 0)
    styles['Normal'].font.size = Pt(11)
    styles['Normal'].paragraph_format.space_after = Pt(5)
    styles['Normal'].paragraph_format.line_spacing = 1.02
    styles['Title'].font.size = Pt(23)
    styles['Title'].paragraph_format.space_after = Pt(15)
    for name, size in [('Heading 1', 15), ('Heading 2', 12), ('Heading 3', 11)]:
        styles[name].font.size = Pt(size)
        styles[name].font.bold = True
        styles[name].paragraph_format.space_before = Pt(13)
        styles[name].paragraph_format.space_after = Pt(6)
        styles[name].paragraph_format.keep_with_next = True
    if source.stem in {'MS-74', 'MS-84', 'MS-91', 'MS-92', 'MS-100'}:
        styles['Normal'].paragraph_format.space_after = Pt(3)
        styles['Normal'].paragraph_format.line_spacing = 1
        styles['Title'].paragraph_format.space_after = Pt(10)
        for name in ['Heading 1', 'Heading 2', 'Heading 3']:
            styles[name].paragraph_format.space_before = Pt(9)
            styles[name].paragraph_format.space_after = Pt(4)
    document.core_properties.author = 'LIGHTYEAR'
    document.core_properties.subject = 'Canonical milestone record and bounded evidence'
    document.core_properties.comments = 'Source SHA256: ' + hashlib.sha256(source.read_bytes()).hexdigest()
    hp = section.header.paragraphs[0]
    hp.add_run().add_picture(str(ROOT / 'brand/assets/lightyear-horizontal.png'), width=Inches(1.2))
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run(source.stem + '  |  ').font.size = Pt(9)
    field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE'); footer._p.append(field)
    tokens = MarkdownIt('commonmark').enable('table').parse(source.read_text(encoding="utf-8"))

    def inline(p, children):
        bold = italic = False
        link = None
        for token in children or []:
            if token.type == 'strong_open': bold = True
            elif token.type == 'strong_close': bold = False
            elif token.type == 'em_open': italic = True
            elif token.type == 'em_close': italic = False
            elif token.type == 'link_open':
                target = token.attrGet('href')
                link = urljoin(GITHUB + source.relative_to(ROOT).as_posix(), target)
            elif token.type == 'link_close': link = None
            elif token.type in ('text', 'code_inline', 'softbreak', 'hardbreak'):
                text = '\n' if token.type == 'hardbreak' else ' ' if token.type == 'softbreak' else token.content
                # Let long hashes, paths and identifiers wrap inside the text area.
                text = re.sub(r'[^\s]{38,}', lambda m: '\u200b'.join(m[0][i:i+24] for i in range(0,len(m[0]),24)), text)
                if link:
                    from docx.opc.constants import RELATIONSHIP_TYPE as RT
                    h = OxmlElement('w:hyperlink'); h.set(qn('r:id'), p.part.relate_to(link, RT.HYPERLINK, is_external=True))
                    rr = OxmlElement('w:r'); props = OxmlElement('w:rPr')
                    color = OxmlElement('w:color'); color.set(qn('w:val'), '244D79'); props.append(color)
                    rr.append(props); tt=OxmlElement('w:t'); tt.set(qn('xml:space'), 'preserve');tt.text=text; rr.append(tt); h.append(rr);p._p.append(h)
                else:
                    run = p.add_run(text); run.bold=bold;run.italic=italic
                    if token.type == 'code_inline': run.font.name='Courier New'; run.font.size=Pt(9)
                    if re.search(r'[\u3400-\u9fff]', text):
                        run.font.name = 'Arial Unicode MS'
                        fonts=run._element.get_or_add_rPr().get_or_add_rFonts()
                        fonts.set(qn('w:eastAsia'), 'Arial Unicode MS')
                        fonts.set(qn('w:hint'), 'eastAsia')

    def table(rows, header=True):
        t = document.add_table(rows=0, cols=len(rows[0]))
        t.style = 'Light Shading Accent 1'
        t.autofit = False
        widths = [7 / len(rows[0])] * len(rows[0])
        if len(rows[0]) == 2: widths = [3.2, 3.8]
        for col, width in zip(t.columns, widths): col.width=Inches(width)
        for i, row in enumerate(rows):
            cells=t.add_row().cells
            trpr=t.rows[-1]._tr.get_or_add_trPr()
            trpr.append(OxmlElement('w:cantSplit'))
            if i == 0 and header: trpr.append(OxmlElement('w:tblHeader'))
            for cell, children, width in zip(cells,row,widths):
                cell.width=Inches(width)
                inline(cell.paragraphs[0],children)
                for p in cell.paragraphs:
                    p.paragraph_format.space_after=Pt(2 if source.stem == "MS-92" else 4)
                    p.paragraph_format.space_before=Pt(2 if source.stem == "MS-92" else 4)
                    for run in p.runs:
                        run.font.size=Pt(10)
                        if i==0 and header:run.bold=True
        document.add_paragraph().paragraph_format.space_after=Pt(0)

    list_stack=[]; heading=None; paragraph=None; first_title=True; i=0
    while i<len(tokens):
        token=tokens[i]
        kind=token.type
        if kind=='table_open':
            rows=[];row=[]
            i+=1
            while tokens[i].type!='table_close':
                if tokens[i].type=='tr_open':row=[]
                elif tokens[i].type=='inline':row.append(tokens[i].children)
                elif tokens[i].type=='tr_close':rows.append(row)
                i+=1
            table(rows)
        elif kind in ('bullet_list_open','ordered_list_open'): list_stack.append(kind)
        elif kind in ('bullet_list_close','ordered_list_close'): list_stack.pop()
        elif kind=='heading_open': heading=int(token.tag[1:])
        elif kind=='heading_close': heading=None
        elif kind=='paragraph_open':
            style=('List Bullet' if list_stack[-1]=='bullet_list_open' else 'List Number') if list_stack else 'Normal'
            paragraph=document.add_paragraph(style=style)
            if len(list_stack)>1:paragraph.paragraph_format.left_indent=Inches(.2*len(list_stack))
        elif kind=='inline':
            if all(t.type=='image' for t in token.children or []):
                if paragraph is not None:paragraph._element.getparent().remove(paragraph._element)
            elif heading:
                text=token.content
                if first_title and heading==1:
                    # Preserve the source title wording in a plain Word title.
                    title=re.sub(r'[^\w\s]', ' ', text)
                    title=re.sub(r'\s+',' ',title).strip()
                    p=document.add_paragraph(title,'Title'); first_title=False
                    document.core_properties.title=title
                else:
                    p=document.add_paragraph(style='Heading '+str(min(heading-1 if heading>1 else 1,3)))
                    inline(p,token.children)
            else:inline(paragraph or document.add_paragraph(),token.children)
        elif kind=='fence':
            if token.info.strip()=='mermaid':
                # A portable edge table retains every directed relationship, including loops.
                labels=dict(re.findall(r'(\w+)\[([^]]+)\]',token.content))
                edges=[]
                for line in token.content.splitlines():
                    simplified=re.sub(r'\[[^]]+\]','',line)
                    match=re.search(r'(\w+)\s*-->\s*(\w+)',simplified)
                    if match:edges.append([MarkdownIt().parseInline(labels.get(x,x))[0].children for x in match.groups()])
                headings=[MarkdownIt().parseInline(x)[0].children for x in ('From','Next step')]
                document.add_paragraph('Workflow relationships', 'Caption')
                table([headings]+edges)
            else:
                for line in token.content.rstrip().splitlines():
                    p=document.add_paragraph()
                    p.paragraph_format.space_after=Pt(0)
                    p.paragraph_format.line_spacing=1
                    # Word can wrap code at these invisible opportunities without deleting bytes.
                    run=p.add_run('\u200b'.join(line[j:j+65] for j in range(0,len(line),65)))
                    run.font.name='Courier New';run.font.size=Pt(8)
                document.add_paragraph().paragraph_format.space_after=Pt(0)
        elif kind=='hr':document.add_paragraph()
        i+=1
    output=source.with_suffix('.docx')
    document.save(output)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--numbers',nargs='*',type=int)
    args=parser.parse_args()
    records=json.loads((DOC_ROOT/'supplemental.json').read_text(encoding="utf-8"))['records']
    for record in records:
        if args.numbers and record['number'] not in args.numbers:continue
        print(build_word(DOC_ROOT/record['path']))


if __name__=='__main__':main()
