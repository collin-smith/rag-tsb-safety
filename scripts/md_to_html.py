#!/usr/bin/env python3
"""Minimal Markdown -> HTML converter for pasting articles into Medium.

Same Markdown subset as md_to_docx.py (## / ### headings, - bullets,
1. numbered lists, ``` fenced code, `code`, **bold**, *italic*,
[text](url), ![alt](src), | tables |), emitted as clean semantic HTML.

Open the output in a browser, Select All, Copy, and paste into a new
Medium story. Medium keeps headings, bold/italic, links, lists and code
blocks on paste. Images do NOT paste - each one is rendered as a visible
placeholder telling you which file to upload at that spot.

Usage: python3 md_to_html.py INPUT.md OUTPUT.html
"""
import html
import re
import sys

TOKEN = re.compile(
    r'`([^`]+)`'                       # 1: inline code
    r'|\*\*(.+?)\*\*'                  # 2: bold
    r'|\*([^*]+?)\*'                   # 3: italic
    r'|\[([^\]]+)\]\(([^)]+)\)'        # 4: link text, 5: link href
)


def inline(text):
    out, pos = [], 0
    for m in TOKEN.finditer(text):
        if m.start() > pos:
            out.append(html.escape(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append(f'<code>{html.escape(m.group(1))}</code>')
        elif m.group(2) is not None:
            out.append(f'<strong>{inline(m.group(2))}</strong>')
        elif m.group(3) is not None:
            out.append(f'<em>{inline(m.group(3))}</em>')
        else:
            href = html.escape(m.group(5), quote=True)
            out.append(f'<a href="{href}">{inline(m.group(4))}</a>')
        pos = m.end()
    if pos < len(text):
        out.append(html.escape(text[pos:]))
    return ''.join(out)


def _is_sep(line):
    return bool(re.fullmatch(r'[\s|:-]+', line.strip())) and '-' in line


def _cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def table(rows):
    header = len(rows) > 1 and _is_sep(rows[1])
    out = ['<table>']
    for idx, r in enumerate(rows):
        if idx == 1 and header:
            continue
        tag = 'th' if (header and idx == 0) else 'td'
        cells = ''.join(f'<{tag}>{inline(c)}</{tag}>' for c in _cells(r))
        out.append(f'<tr>{cells}</tr>')
    out.append('</table>')
    return '\n'.join(out)


def convert(md):
    lines = md.split('\n')
    body, i, n = [], 0, len(lines)
    buf = []

    def flush():
        if not buf:
            return
        text = ' '.join(x.strip() for x in buf).strip()
        buf.clear()
        if text:
            body.append(f'<p>{inline(text)}</p>')

    while i < n:
        line = lines[i]

        if line.startswith('```'):
            flush()
            i += 1
            code = []
            while i < n and not lines[i].startswith('```'):
                code.append(lines[i])
                i += 1
            i += 1
            body.append('<pre><code>' + html.escape('\n'.join(code))
                        + '</code></pre>')
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
            continue

        if line.startswith('# '):
            flush()
            body.append(f'<h1>{inline(line[2:].strip())}</h1>')
        elif line.startswith('### '):
            flush()
            body.append(f'<h3>{inline(line[4:].strip())}</h3>')
        elif line.startswith('## '):
            flush()
            body.append(f'<h2>{inline(line[3:].strip())}</h2>')
        elif line.startswith('!['):
            flush()
            m = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', line)
            alt, src = (m.group(1), m.group(2)) if m else ('', line)
            if src.startswith('http://') or src.startswith('https://'):
                # A real external URL is already hosted and loads live in the
                # browser -- Medium can pull it in on paste too. Only a bare
                # local filename (the architecture diagrams) needs the
                # upload-it-yourself placeholder below.
                body.append(f'<img src="{html.escape(src, quote=True)}" '
                            f'alt="{html.escape(alt, quote=True)}">')
            else:
                body.append(
                    '<p class="img-placeholder">&#128247; UPLOAD IMAGE HERE: '
                    f'<strong>{html.escape(src)}</strong><br><span>{html.escape(alt)}</span></p>')
        elif re.match(r'\s*[-*] ', line) or re.match(r'\s*\d+\. ', line):
            ordered = bool(re.match(r'\s*\d+\. ', line))
            flush()
            items = []
            while i < n:
                m = re.match(r'\s*(?:[-*]|\d+\.) (.*)', lines[i])
                if not m:
                    break
                # segments: interleaved ['text', str] and ['code', [lines]]
                # so a fenced block indented under a list item survives as a
                # real <pre>, not flattened backtick soup.
                segs = [['text', m.group(1)]]
                j = i + 1
                while j < n and lines[j].startswith('  ') and lines[j].strip() \
                        and not re.match(r'\s*(?:[-*]|\d+\.) ', lines[j]):
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
                parts = []
                for kind, val in segs:
                    if kind == 'text':
                        parts.append(inline(val))
                    else:
                        parts.append('<pre><code>'
                                     + html.escape('\n'.join(val))
                                     + '</code></pre>')
                items.append('<li>' + ''.join(parts) + '</li>')
                i = j
            tag = 'ol' if ordered else 'ul'
            body.append(f'<{tag}>\n' + '\n'.join(items) + f'\n</{tag}>')
            continue
        else:
            buf.append(line)
        i += 1

    flush()
    return '\n'.join(body)


PAGE = """<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ max-width: 720px; margin: 2rem auto; padding: 0 1rem;
         font: 18px/1.6 Georgia, serif; color: #222; }}
  h1 {{ font: 700 1.7rem/1.25 -apple-system, Helvetica, Arial, sans-serif;
       margin: 2rem 0 .6rem; }}
  h2 {{ font: 700 1.3rem/1.25 -apple-system, Helvetica, Arial, sans-serif;
       margin: 1.6rem 0 .5rem; }}
  h3 {{ font: 700 1.1rem/1.25 -apple-system, Helvetica, Arial, sans-serif;
       margin: 1.4rem 0 .4rem; }}
  pre {{ background: #f4f4f4; padding: 1rem; overflow-x: auto;
        font: 14px/1.45 Menlo, Consolas, monospace; }}
  code {{ background: #f0f0f0; padding: .1em .3em; font: .85em Menlo, Consolas, monospace; }}
  pre code {{ background: none; padding: 0; }}
  table {{ border-collapse: collapse; }}
  th, td {{ border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; }}
  .img-placeholder {{ background: #fff6d9; border: 2px dashed #d4a017;
       padding: .8rem 1rem; font-family: -apple-system, Helvetica, Arial, sans-serif;
       font-size: .95rem; }}
  .img-placeholder span {{ color: #666; font-style: italic; }}
</style>
{body}
"""


def main():
    src, dst = sys.argv[1], sys.argv[2]
    md = open(src, encoding='utf-8').read()
    title = next((ln[2:].strip() for ln in md.split('\n')
                  if ln.startswith('# ')), 'Article')
    open(dst, 'w', encoding='utf-8').write(
        PAGE.format(title=html.escape(title), body=convert(md)))
    print(f'wrote {dst} ({title})')


if __name__ == '__main__':
    main()
