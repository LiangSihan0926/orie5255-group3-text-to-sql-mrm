"""Build the editable report from the versioned Markdown and traceability matrices."""
from pathlib import Path
import re

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'deliverables' / 'Group_3_Topic_2_Final_Report.docx'
FONT = 'Calibri'
INK = RGBColor.from_string('162430')
MUTED = RGBColor.from_string('475763')
WIDTH = 6.86
MARKUP = re.compile(r'(\*\*[^*]+\*\*|`[^`]+`|https://[^\s]+)')


def element(tag, **attrs):
    node = OxmlElement(f'w:{tag}')
    for key, val in attrs.items():
        node.set(qn(f'w:{key}'), str(val))
    return node


def link(paragraph, url):
    relationship = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = element('hyperlink')
    hyperlink.set(qn('r:id'), relationship)
    run = element('r')
    style = element('rPr')
    style.append(element('color', val='22516E'))
    style.append(element('u', val='single'))
    run.append(style)
    text = element('t')
    text.text = url
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_text(paragraph, text):
    for part in MARKUP.split(text):
        if part.startswith('**'):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith('`'):
            paragraph.add_run(part[1:-1]).font.name = 'Menlo'
        elif part.startswith('https://'):
            link(paragraph, part)
        else:
            paragraph.add_run(part)
    return paragraph


def style(doc, name, size, *, bold=False, color=INK, before=0, after=0, spacing=1.16, font=FONT):
    if name not in doc.styles:
        doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    st = doc.styles[name]
    st.font.name = font
    st.font.size = Pt(size)
    st.font.bold = bold
    st.font.color.rgb = color
    pf = st.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = spacing
    return st


def setup():
    doc = Document()
    doc.core_properties.title = 'Validating a Text-to-SQL Agent for Bank Portfolio Analytics'
    doc.core_properties.author = 'Sihan Liang and Minxi Lin'
    doc.core_properties.subject = 'ORIE 5255 Capstone · Group 3 · Topic 2'
    s = doc.sections[0]
    s.page_width, s.page_height = Inches(8.5), Inches(11)
    s.left_margin = s.right_margin = Inches(0.82)
    s.top_margin, s.bottom_margin = Inches(0.77), Inches(0.67)
    s.header_distance, s.footer_distance = Inches(0.38), Inches(0.35)
    style(doc, 'Normal', 11.5, after=9, spacing=1.18)
    style(doc, 'Title', 30, bold=True, after=11, spacing=1.05)
    style(doc, 'Heading 1', 22, bold=True, after=12, spacing=1.08)
    style(doc, 'Heading 2', 14, bold=True, before=7, after=5)
    style(doc, 'Byline', 11, color=MUTED, after=5)
    style(doc, 'Reference', 10.5, after=7, spacing=1.08)
    style(doc, 'Table Text', 10, after=0, spacing=1.12)
    style(doc, 'Diagram', 9.3, font='DejaVu Sans Mono', after=0, spacing=1.17)
    style(doc, 'Caption', 9.5, color=MUTED, after=8, spacing=1.05)
    style(doc, 'Small Header', 9, color=MUTED, spacing=1)
    head = s.header.paragraphs[0]
    head.style = 'Small Header'
    head.text = 'ORIE 5255  /  CAPSTONE  /  GROUP 3'
    foot = s.footer.paragraphs[0]
    foot.style = 'Small Header'
    foot.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    foot._p.append(element('fldSimple', instr='PAGE'))
    return doc


def widths_for(matrix):
    cols = len(matrix[0])
    first = matrix[0][0]
    if cols == 2:
        return (0.31, 0.69) if first != 'ID' else (0.10, 0.90)
    if cols == 3:
        return (0.22, 0.47, 0.31) if first in ('Node', 'Item', 'Cases') else (0.44, 0.28, 0.28)
    if cols == 4:
        return (0.17, 0.29, 0.29, 0.25)
    if cols == 5:
        return (0.32, 0.11, 0.19, 0.19, 0.19)
    raise ValueError(f'Unexpected table: {matrix[0]}')


def table(doc, matrix, *, diagram=False):
    if diagram:
        widths = (1,)
    elif matrix[0][0] == 'Node' and len(matrix[0]) == 4:
        widths = (0.10, 0.32, 0.32, 0.26)
    else:
        widths = widths_for(matrix)
    t = doc.add_table(rows=0, cols=len(widths))
    t.autofit = False
    for col, fraction in zip(t.columns, widths):
        col.width = Inches(WIDTH * fraction)
    props = t._tbl.tblPr
    margins = element('tblCellMar')
    for edge, pad in (('top', 78), ('bottom', 78), ('left', 112), ('right', 112)):
        margins.append(element(edge, w=pad, type='dxa'))
    props.append(margins)
    borders = element('tblBorders')
    for edge in ('top', 'bottom', 'left', 'right', 'insideH', 'insideV'):
        borders.append(element(edge, val='single', sz=5, color='D8E1E7'))
    props.append(borders)
    for i, values in enumerate(matrix):
        row = t.add_row()
        row._tr.get_or_add_trPr().append(element('cantSplit'))
        if i == 0 and not diagram:
            row._tr.get_or_add_trPr().append(element('tblHeader', val='true'))
        for j, (cell, value) in enumerate(zip(row.cells, values)):
            cell.width = Inches(WIDTH * widths[j])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            fill = 'F5F8FA' if diagram else 'E5EDF2' if i == 0 else 'F7F9FA' if i % 2 == 0 else 'FFFFFF'
            cell._tc.get_or_add_tcPr().append(element('shd', fill=fill, val='clear'))
            p = cell.paragraphs[0]
            p.style = 'Diagram' if diagram else 'Table Text'
            add_text(p, value)
            if i == 0 and not diagram:
                for run in p.runs:
                    run.bold = True
    spacer = doc.add_paragraph(style='Caption')
    spacer.paragraph_format.space_after = Pt(1)
    spacer.paragraph_format.line_spacing = Pt(5)


def render_page(doc, page):
    trace = (ROOT / 'docs' / 'traceability.md').read_text()
    if page.startswith('{{matrix:'):
        letter = page[len('{{matrix:')]
        matrix = re.search(rf'^## {letter}\. (.*?)(?=^## [A-C]\.|\Z)', trace, re.M | re.S).group(1).strip()
        title, body = matrix.split('\n', 1)
        page = f'## Appendix {letter} · {title}\n{body}'
    for block in re.split(r'\n\s*\n', page):
        block = block.strip()
        if block.startswith(':::diagram'):
            lines = block.splitlines()[1:-1]
            table(doc, [['\n'.join(lines)]], diagram=True)
            add_text(doc.add_paragraph(style='Caption'), 'Figure 1. Proposed node flow, repair loop and terminal decisions.')
        elif block.startswith('|'):
            rows = [line.strip('|').split('|') for line in block.splitlines()]
            matrix = [[c.strip() for c in row] for i, row in enumerate(rows) if i != 1]
            table(doc, matrix)
        elif block.startswith('### '):
            doc.add_paragraph(block[4:], style='Heading 2')
        elif block.startswith('## '):
            name = 'Heading 2' if block == '## Abstract' else 'Heading 1'
            doc.add_paragraph(block[3:], style=name)
        elif block.startswith('# '):
            doc.add_paragraph(block[2:], style='Title')
        elif block.startswith(('ORIE 5255 ·', 'Sihan Liang')):
            doc.add_paragraph(block, style='Byline')
        elif block:
            name = 'Reference' if re.match(r'^\[\d+\]', block) else 'Normal'
            add_text(doc.add_paragraph(style=name), block)


def main():
    doc = setup()
    source = (ROOT / 'docs' / 'report.md').read_text()
    for i, page in enumerate(source.split('<!-- page -->')):
        first = len(doc.paragraphs)
        render_page(doc, page.strip())
        if i:
            doc.paragraphs[first].paragraph_format.page_break_before = True
    doc.save(OUT)


if __name__ == '__main__':
    main()
