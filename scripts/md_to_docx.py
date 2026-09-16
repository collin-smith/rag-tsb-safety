#!/usr/bin/env python3
"""Minimal Markdown -> .docx converter, stdlib only.

Matches the hand-rolled style used for articles 02-07 in this project:
Title / Heading1 (##) / Heading2 (###) / Normal / ListBullet, a Code
character style for inline `code` and fenced ``` blocks, **bold** and
*italic* inline (including **`bold code`**). Images become "[Diagram: x]".

Usage: python3 md_to_docx.py INPUT.md OUTPUT.docx
"""
import re
import sys
import zipfile

BOLD = re.compile(r'\*\*(.+?)\*\*', re.S)
INNER = re.compile(r'`([^`]+)`|\*([^*]+?)\*|\[([^\]]+)\]\(([^)]+)\)')

# Populated by convert() as [text](url) spans are encountered; consumed by
# main() to emit real word/_rels/document.xml.rels hyperlink relationships.
# Reset per convert() call so repeated conversions in one process don't leak.
_LINK_REGISTRY = {}


def register_link(url):
    if url not in _LINK_REGISTRY:
        _LINK_REGISTRY[url] = f'rHyp{len(_LINK_REGISTRY) + 1}'
    return _LINK_REGISTRY[url]


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '&quot;'))


def run(text, styles, url=None):
    parts = ''
    if 'code' in styles:
        parts += '<w:rStyle w:val="Code"/>'
    if url:
        parts += '<w:rStyle w:val="Hyperlink"/>'
    if 'b' in styles:
        parts += '<w:b/>'
    if 'i' in styles:
        parts += '<w:i/>'
    rpr = f'<w:rPr>{parts}</w:rPr>' if parts else ''
    r = f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'
    if url:
        rid = register_link(url)
        return f'<w:hyperlink r:id="{rid}" w:history="1">{r}</w:hyperlink>'
    return r


LINK_ONLY = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def _split_links(text, styles):
    """Split text on [label](url), applying `styles` to every resulting span.
    Used for *italic*-wrapped content, which INNER's own alternation can't
    see into -- the italic regex already consumed the whole "*(cited:
    [R13D0054](url))*" span as one atomic match by the time a link inside it
    would otherwise be considered."""
    out, pos = [], 0
    for m in LINK_ONLY.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], set(styles), None))
        out.append((m.group(1), set(styles), m.group(2)))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], set(styles), None))
    return out


def _inner(text, base):
    """`code`, *italic*, and [text](url) spans within text; `base` styles
    applied to all. Link detection happens at this level (not stripped
    beforehand) so a link nested inside **bold** -- e.g. **[R13D0054](url)**
    -- still becomes a real hyperlink, not literal bracket text."""
    out, pos = [], 0
    for m in INNER.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], set(base), None))
        if m.group(1) is not None:
            out.append((m.group(1), base | {'code'}, None))
        elif m.group(2) is not None:
            out += _split_links(m.group(2), base | {'i'})
        else:
            out.append((m.group(3), set(base), m.group(4)))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], set(base), None))
    return out


def _spans(text, base=frozenset()):
    """Full inline parse: **bold** (may wrap `code`/*italic*/link), then `code`/*italic*/link."""
    out, pos = [], 0
    for m in BOLD.finditer(text):
        if m.start() > pos:
            out += _inner(text[pos:m.start()], set(base))
        out += _inner(m.group(1), set(base) | {'b'})
        pos = m.end()
    if pos < len(text):
        out += _inner(text[pos:], set(base))
    return out


def runs(text, base=frozenset()):
    return ''.join(run(t, s, u) for t, s, u in _spans(text, base)) or run('', set())


def para(style, inner):
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{inner}</w:p>'


def _cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def _is_sep(line):
    return bool(re.fullmatch(r'[\s|:-]+', line.strip())) and '-' in line


TBL_BORDERS = ('<w:tblBorders>' + ''.join(
    f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="AAAAAA"/>'
    for e in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')
) + '</w:tblBorders>')


def table(rows):
    header = len(rows) > 1 and _is_sep(rows[1])
    out = [f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>{TBL_BORDERS}</w:tblPr>']
    for idx, r in enumerate(rows):
        if idx == 1 and header:
            continue
        base = frozenset({'b'}) if (header and idx == 0) else frozenset()
        out.append('<w:tr>')
        for c in _cells(r):
            out.append('<w:tc><w:tcPr/><w:p><w:pPr><w:pStyle w:val="Normal"/>'
                       f'</w:pPr>{runs(c, base)}</w:p></w:tc>')
        out.append('</w:tr>')
    out.append('</w:tbl>')
    return ''.join(out)


def convert(md):
    _LINK_REGISTRY.clear()
    lines = md.split('\n')
    body, i, n = [], 0, len(lines)
    buf = []

    def flush():
        if not buf:
            return
        text = ' '.join(x.strip() for x in buf).strip()
        buf.clear()
        if not text:
            return
        if text.startswith('*') and text.endswith('*') and not text.startswith('**'):
            body.append(para('Normal', runs(text[1:-1], {'i'})))
        else:
            body.append(para('Normal', runs(text)))

    while i < n:
        line = lines[i]
        if line.startswith('```'):
            flush()
            i += 1
            while i < n and not lines[i].startswith('```'):
                cl = lines[i] if lines[i].strip() else ' '
                body.append(para('Normal', run(cl, {'code'})))
                i += 1
            i += 1
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        if line.lstrip().startswith('|'):
            flush()
            rows = []
            while i < n and lines[i].lstrip().startswith('|'):
                rows.append(lines[i])
                i += 1
            body.append(table(rows))
            body.append(para('Normal', run('', set())))
            continue
        if line.startswith('# '):
            flush()
            body.append(para('Title', run(line[2:].strip(), set())))
        elif line.startswith('### '):
            flush()
            body.append(para('Heading2', run(line[4:].strip(), set())))
        elif line.startswith('## '):
            flush()
            body.append(para('Heading1', run(line[3:].strip(), set())))
        elif line.startswith('!['):
            flush()
            m = re.search(r'\]\(([^)]+)\)', line)
            body.append(para('Normal', run(f'[Diagram: {m.group(1)}]', set())))
        elif line.startswith('- '):
            flush()
            # segments: interleaved ['text', str] and ['code', [lines]] so a
            # fenced block indented under a bullet keeps its Code styling
            # instead of being flattened into the bullet text.
            segs = [['text', line[2:]]]
            j = i + 1
            while j < n and lines[j].startswith('  ') and lines[j].strip() \
                    and not lines[j].lstrip().startswith('- '):
                stripped = lines[j].strip()
                if stripped.startswith('```'):
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    j += 1
                    code = []
                    while j < n and not lines[j].strip().startswith('```'):
                        cl = lines[j]
                        code.append(cl[indent:] if not cl[:indent].strip()
                                    else cl.strip())
                        j += 1
                    j += 1
                    segs.append(['code', code])
                elif segs[-1][0] == 'text':
                    segs[-1][1] += ' ' + stripped
                    j += 1
                else:
                    segs.append(['text', stripped])
                    j += 1
            i = j - 1
            for k, (kind, val) in enumerate(segs):
                if kind == 'text':
                    prefix = run('•  ', set()) if k == 0 else run('', set())
                    body.append(para('ListBullet', prefix + runs(val)))
                else:
                    for cl in val:
                        body.append(para('Normal',
                                         run(cl if cl.strip() else ' ', {'code'})))
        else:
            buf.append(line)
        i += 1
    flush()
    return ''.join(body)


DOCUMENT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
            '<w:body>{}</w:body></w:document>')

STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="360" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="240" w:after="100"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="0"/></w:numPr><w:ind w:left="360" w:hanging="360"/></w:pPr></w:style>
<w:style w:type="character" w:styleId="Code"><w:name w:val="Code"/><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:shd w:val="clear" w:color="auto" w:fill="EEEEEE"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>
</w:styles>'''

CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''

RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

APP_XML = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">\n'
           '<Application>python</Application>\n</Properties>')


def main():
    src, dst = sys.argv[1], sys.argv[2]
    md = open(src, encoding='utf-8').read()
    title = 'Article'
    for ln in md.split('\n'):
        if ln.startswith('# '):
            title = ln[2:].strip()
            break
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'<dc:title>{esc(title)}</dc:title>\n<dc:creator>Collin Smith</dc:creator>\n'
            '</cp:coreProperties>')
    document = DOCUMENT.format(convert(md))
    doc_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>']
    for url, rid in _LINK_REGISTRY.items():
        doc_rels.append(
            f'<Relationship Id="{rid}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{esc(url)}" TargetMode="External"/>')
    doc_rels.append('</Relationships>')
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', CONTENT_TYPES)
        z.writestr('_rels/.rels', RELS)
        z.writestr('docProps/core.xml', core)
        z.writestr('docProps/app.xml', APP_XML)
        z.writestr('word/document.xml', document)
        z.writestr('word/styles.xml', STYLES)
        z.writestr('word/_rels/document.xml.rels', ''.join(doc_rels))
    print(f'wrote {dst} ({title})')


if __name__ == '__main__':
    main()
