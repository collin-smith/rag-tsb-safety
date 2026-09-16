"""Hand-built SVG previews approximating the .drawio diagrams' layout and
content. NOT official AWS icons (those are proprietary stencil assets
bundled with the draw.io desktop app / diagrams.net, not available here) --
plain rounded rectangles colored per AWS's 2023+ Architecture Icons
category-color convention (storage=green, security=red, ML=teal), for an
honest preview. Open the matching .drawio file in app.diagrams.net for the
real, pixel-perfect AWS-icon rendering.

Layout here is hand-coded to match the corresponding .drawio file's boxes
and arrows -- if either diagram's layout changes, update both.

Usage:
    python3 render_diagram_previews.py OUT1.svg OUT2.svg
"""

CLOUD_NAVY = "#232F3E"
EXTERNAL_GRAY = "#F5F5F5"
NOTE_YELLOW = "#FFF6D9"
BLUE = "#dae8fc"

# AWS's 2023+ Architecture Icons use category colors, not uniform orange.
# (dark, light) pairs, dark at the bottom of the gradient matching the
# .drawio resourceIcon fillColor/gradientColor pairs used in this project.
CATEGORY_COLORS = {
    "storage": ("#4D7204", "#7AA116"),   # S3 etc.
    "security": ("#BC1356", "#DD344C"),  # IAM etc.
    "ml": ("#017F6A", "#01A88D"),        # Bedrock/Titan/Nova
}


def svg_header(w, h):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="Helvetica, Arial, sans-serif">'


def rect(x, y, w, h, fill, stroke, stroke_width=1.5, dash=None, rx=6):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"{d}/>'


def text(x, y, s, size=12, weight="normal", color="#111", anchor="start"):
    lines = s.split("\n")
    out = []
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{x}" y="{y + i * (size + 4)}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{esc(line)}</text>'
        )
    return "".join(out)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def aws_icon(x, y, w, h, label, category):
    dark, light = CATEGORY_COLORS[category]
    gid = f"grad_{category}"
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="url(#{gid})"/>'
    return out + text(x + w / 2, y + h + 16, label, size=11, weight="600", anchor="middle")


def category_defs():
    stops = []
    for name, (dark, light) in CATEGORY_COLORS.items():
        stops.append(
            f'<linearGradient id="grad_{name}" x1="0" y1="1" x2="0" y2="0">'
            f'<stop offset="0" stop-color="{dark}"/><stop offset="1" stop-color="{light}"/>'
            '</linearGradient>'
        )
    return "<defs>" + "".join(stops) + "</defs>"


def arrow_marker():
    return (
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
        'orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#555"/></marker></defs>'
    )


def line(x1, y1, x2, y2, dash=None, label=None, lx=None, ly=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"{d}/>'
    if label:
        out += text(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2 - 6,
                     label, size=10, color="#666", anchor="middle")
    return out


def diagram1():
    w, h = 980, 420
    svg = [svg_header(w, h), category_defs(), arrow_marker()]
    svg.append(f'<rect width="{w}" height="{h}" fill="#ffffff"/>')

    svg.append(rect(40, 60, 240, 110, EXTERNAL_GRAY, "#666666", dash="6,4"))
    svg.append(text(160, 90, "tsb.gc.ca (external, non-AWS)", size=12, weight="700", anchor="middle"))
    svg.append(text(160, 112, "Rail + pipeline report indexes\n526 reports, 1991-2026",
                     size=11, color="#444", anchor="middle"))

    svg.append(rect(360, 75, 160, 80, BLUE, "#666666"))
    svg.append(text(440, 100, "Dev machine", size=12, weight="700", anchor="middle"))
    svg.append(text(440, 118, "parse_tsb_index.py\ningest_reports.py", size=10, color="#333", anchor="middle"))

    svg.append(rect(360, 210, 200, 80, NOTE_YELLOW, "#D4A017"))
    svg.append(text(460, 235, "reports_manifest.csv", size=12, weight="700", anchor="middle"))
    svg.append(text(460, 253, "24 reports (16 rail, 8 pipeline)\ncurated + licensing-checked",
                     size=10, color="#444", anchor="middle"))

    svg.append(rect(640, 40, 300, 260, "none", CLOUD_NAVY, stroke_width=2))
    svg.append(text(655, 65, "AWS Cloud (us-east-1)", size=13, weight="700", color=CLOUD_NAVY))

    svg.append(aws_icon(680, 100, 78, 78, "S3 raw zone\nrag-tsb-safety-raw-...\nreports/{mode}/{id}.txt", "storage"))
    svg.append(aws_icon(800, 100, 78, 78, "IAM role\nKB execution\n(used in Phase 2)", "security"))

    svg.append(line(280, 100, 355, 100, label="curl (browser UA header)", lx=310, ly=85))
    svg.append(line(440, 155, 440, 205))
    svg.append(line(440, 155, 680, 140, label="upload + tag", lx=560, ly=130))

    svg.append("</svg>")
    return "\n".join(svg)


def diagram2():
    w, h = 1040, 560
    svg = [svg_header(w, h), category_defs(), arrow_marker()]
    svg.append(f'<rect width="{w}" height="{h}" fill="#ffffff"/>')

    svg.append(rect(30, 240, 150, 80, BLUE, "#666666"))
    svg.append(text(105, 265, "demo.py", size=12, weight="700", anchor="middle"))
    svg.append(text(105, 283, "5 real questions +\n1 weak-spot query", size=10, color="#333", anchor="middle"))

    svg.append(rect(230, 40, 780, 480, "none", CLOUD_NAVY, stroke_width=2))
    svg.append(text(245, 65, "AWS Cloud (ca-central-1)", size=13, weight="700", color=CLOUD_NAVY))

    svg.append(aws_icon(260, 100, 78, 78, "S3 raw zone\n(Phase 1 output, migrated)\n370 reports + metadata", "storage"))
    svg.append(aws_icon(280, 420, 60, 60, "IAM role\nKB execution", "security"))
    svg.append(aws_icon(460, 260, 90, 90, "Bedrock Knowledge Base\nZ3Q6F4RTPY\nchunk 1500tok/10% overlap", "ml"))
    svg.append(aws_icon(470, 100, 70, 70, "Titan Embeddings V2\n(60 req/min quota)", "ml"))
    svg.append(aws_icon(700, 100, 78, 78, "S3 Vectors\nrag-tsb-safety-vectors\n370 docs, date_numeric", "storage"))
    svg.append(aws_icon(700, 280, 70, 70, "Amazon Nova Lite\nvia ca.amazon.nova-lite-v1:0\nCA inference profile", "ml"))

    svg.append(line(180, 280, 500, 300, label="retrieve() query + optional metadata filter", lx=340, ly=270))
    svg.append(line(505, 355, 180, 340, dash="4,3", label="answer + citations (rag_utils.py)", lx=340, ly=365))
    svg.append(line(340, 178, 500, 135, label="sync: fetch + chunk", lx=420, ly=145))
    svg.append(line(540, 135, 700, 135, label="embeddings", lx=620, ly=120))
    svg.append(line(550, 300, 700, 250, label="filtered vector search", lx=650, ly=260))
    svg.append(line(550, 320, 700, 315, label="chunks -> rag_utils -> converse()", lx=630, ly=345))
    svg.append(line(310, 420, 480, 350, dash="4,3", label="assumed by", lx=370, ly=400))

    svg.append("</svg>")
    return "\n".join(svg)


def diagram3():
    w, h = 1080, 700
    svg = [svg_header(w, h), category_defs(), arrow_marker()]
    svg.append(f'<rect width="{w}" height="{h}" fill="#ffffff"/>')

    svg.append(rect(20, 280, 120, 65, BLUE, "#666666"))
    svg.append(text(80, 305, "Dev machine", size=12, weight="700", anchor="middle"))
    svg.append(text(80, 323, "extract_structured_findings.py\nagent_router.py", size=9, color="#333", anchor="middle"))

    svg.append(rect(20, 480, 190, 90, NOTE_YELLOW, "#D4A017"))
    svg.append(text(115, 500, "structured_findings.json/csv", size=11, weight="700", anchor="middle"))
    svg.append(text(115, 516, "(local file, NOT an AWS resource)\n57 rows: root cause, fatalities,\ndangerous goods, prior rec. status",
                     size=9, color="#444", anchor="middle"))

    svg.append(rect(780, 540, 260, 110, EXTERNAL_GRAY, "#666666", dash="6,4"))
    svg.append(text(910, 560, "No VPC", size=12, weight="700", anchor="middle"))
    svg.append(text(910, 578, "All AWS services reached over their\npublic API via boto3 -- no compute\ndeployed inside a VPC boundary.\nWould only apply behind a\nproductionized Lambda/ECS task.",
                     size=9, color="#444", anchor="middle"))

    svg.append(rect(260, 30, 720, 500, "none", CLOUD_NAVY, stroke_width=2))
    svg.append(text(275, 55, "AWS Cloud (us-east-1) -- no VPC", size=13, weight="700", color=CLOUD_NAVY))

    svg.append(aws_icon(280, 60, 60, 60, "S3 raw zone\n(reused)", "storage"))
    svg.append(aws_icon(280, 450, 55, 55, "IAM role\n(reused)", "security"))
    svg.append(aws_icon(440, 220, 110, 95, "Bedrock Knowledge Base\nretrieve (report_id filter) +\nretrieve_and_generate (mode filter)", "ml"))
    svg.append(aws_icon(640, 60, 60, 60, "S3 Vectors\n(reused)", "storage"))
    svg.append(aws_icon(640, 210, 90, 80, "Nova Lite\nextraction\n(1 call/report)", "ml"))
    svg.append(aws_icon(800, 360, 110, 90, "Nova Lite\ntool-use router\n(picks aggregate\nvs. semantic tool)", "ml"))

    svg.append(line(140, 300, 440, 260, label="report_id filter (loop, 1/report)", lx=270, ly=245))
    svg.append(line(640, 250, 730, 250, label="all chunks", lx=685, ly=235))
    svg.append(line(700, 290, 200, 480, dash="4,3", label="57 extracted rows", lx=440, ly=400))
    svg.append(line(140, 320, 800, 400, label="natural-language question", lx=470, ly=345))
    svg.append(line(850, 450, 220, 520, dash="4,3", label="tool: aggregate_structured_findings", lx=560, ly=500))
    svg.append(line(800, 400, 550, 280, label="tool: verified_semantic_query", lx=650, ly=345))
    svg.append(line(800, 440, 140, 335, dash="4,3", label="final answer / fail-safe fallback", lx=470, ly=395))

    svg.append("</svg>")
    return "\n".join(svg)


def diagram4():
    w, h = 900, 420
    svg = [svg_header(w, h), category_defs(), arrow_marker()]
    svg.append(f'<rect width="{w}" height="{h}" fill="#ffffff"/>')

    svg.append(rect(580, 240, 230, 90, NOTE_YELLOW, "#D4A017"))
    svg.append(text(695, 260, "structured_findings.json/csv", size=11, weight="700", anchor="middle"))
    svg.append(text(695, 276, "(local file from Phase 3, not an AWS resource)\n57 rows: root cause, fatalities,\ndangerous goods, prior rec. status",
                     size=9, color="#444", anchor="middle"))

    svg.append(rect(670, 60, 180, 90, BLUE, "#666666"))
    svg.append(text(760, 80, "This article", size=12, weight="700", anchor="middle"))
    svg.append(text(760, 98, "4 findings + 5 recommended\nactions, each traced to an\nexact count or a direct quote",
                     size=9, color="#333", anchor="middle"))

    svg.append(rect(20, 30, 520, 280, "none", CLOUD_NAVY, stroke_width=2))
    svg.append(text(35, 55, "AWS Cloud (us-east-1) -- no VPC, reused from Phases 1-3", size=12, weight="700", color=CLOUD_NAVY))

    svg.append(aws_icon(40, 80, 60, 60, "S3 raw zone\n57 TSB reports", "storage"))
    svg.append(aws_icon(40, 220, 60, 60, "S3 Vectors\nreports-index", "storage"))
    svg.append(aws_icon(200, 190, 100, 90, "Bedrock Knowledge Base\nretrieve (report_id filter)", "ml"))
    svg.append(aws_icon(390, 190, 100, 90, "Nova Lite\nstructured extraction", "ml"))

    svg.append(line(70, 140, 240, 190, label="ingested docs", lx=140, ly=175))
    svg.append(line(100, 250, 200, 235, label="chunk vectors", lx=140, ly=245))
    svg.append(line(300, 235, 390, 235, label="all chunks/report", lx=345, ly=220))
    svg.append(line(490, 235, 580, 280, dash="4,3", label="57 extracted rows", lx=530, ly=270))
    svg.append(line(695, 240, 760, 150, dash="4,3", label="read + aggregated by mode", lx=780, ly=200))

    svg.append("</svg>")
    return "\n".join(svg)


def diagram5():
    w, h = 1000, 500
    svg = [svg_header(w, h), category_defs(), arrow_marker()]
    svg.append(f'<rect width="{w}" height="{h}" fill="#ffffff"/>')

    svg.append(text(20, 25, "Solid / colored = built and measured (Phases 1-3). Dashed / gray = proposed in this article, not built.",
                     size=11, weight="700", color=CLOUD_NAVY, anchor="start"))

    svg.append(rect(20, 50, 470, 200, "none", CLOUD_NAVY, stroke_width=2))
    svg.append(text(35, 70, "AWS Cloud (us-east-1) -- built, Phases 1-3", size=12, weight="700", color=CLOUD_NAVY))

    svg.append(aws_icon(40, 90, 60, 60, "S3 raw zone\n+ manifest", "storage"))
    svg.append(aws_icon(40, 190, 60, 60, "S3 Vectors", "storage"))
    svg.append(aws_icon(190, 100, 80, 70, "Bedrock\nKnowledge Base", "ml"))
    svg.append(aws_icon(360, 170, 90, 70, "Nova Lite\nsemantic generation", "ml"))

    # Proposed (Thread 1) elements: plain gray dashed boxes, not aws4-colored
    svg.append(rect(530, 170, 160, 80, EXTERNAL_GRAY, "#999999", dash="4,3"))
    svg.append(text(610, 195, "Entity verification", size=10, weight="700", anchor="middle"))
    svg.append(text(610, 210, "(Thread 1, PROPOSED)\ndoes cited report_id match\nthe named entity?", size=8, color="#444", anchor="middle"))

    svg.append(rect(530, 300, 230, 90, EXTERNAL_GRAY, "#999999", dash="4,3"))
    svg.append(text(645, 320, "Entity index (Thread 1, PROPOSED)", size=10, weight="700", anchor="middle"))
    svg.append(text(645, 335, "report_id -> {location, company, incident}\nbuilt from manifest columns already tracked,\nno new extraction needed", size=8, color="#444", anchor="middle"))

    svg.append(rect(750, 170, 200, 80, BLUE, "#666666"))
    svg.append(text(850, 190, "Match: surface the answer", size=9, weight="700", anchor="middle"))
    svg.append(text(850, 205, "Mismatch: flag \"grounded in a\ndifferent report\" instead of\na silently wrong answer", size=8, color="#333", anchor="middle"))

    svg.append(rect(20, 320, 250, 110, EXTERNAL_GRAY, "#999999", dash="4,3"))
    svg.append(text(145, 340, "Thread 2 (PROPOSED, not run)", size=10, weight="700", anchor="middle"))
    svg.append(text(145, 355, "same pipeline above, pointed at a\n~320-report stratified sample or the\nfull 2,422-report TSB population,\ninstead of the curated 57", size=8, color="#444", anchor="middle"))

    svg.append(rect(290, 320, 250, 110, EXTERNAL_GRAY, "#999999", dash="4,3"))
    svg.append(text(415, 340, "Thread 3 (PROPOSED, not built)", size=10, weight="700", anchor="middle"))
    svg.append(text(415, 355, "same pipeline, pointed at a different\ncorpus -- legal discovery, incident\nreports, support tickets, compliance\nfilings -- schema changes, phases don't", size=8, color="#444", anchor="middle"))

    svg.append(line(100, 120, 190, 130, label="ingested docs", lx=140, ly=105))
    svg.append(line(100, 210, 190, 150, label="chunk vectors", lx=140, ly=190))
    svg.append(line(270, 140, 360, 195, label="all chunks/report", lx=310, ly=170))
    svg.append(line(450, 200, 530, 205, dash="4,3", label="answer + citation", lx=490, ly=185))
    svg.append(line(610, 300, 610, 250, dash="4,3"))
    svg.append(line(690, 205, 750, 205, dash="4,3"))

    svg.append("</svg>")
    return "\n".join(svg)


def diagram6():
    w, h = 1080, 520
    svg = [svg_header(w, h), category_defs(), arrow_marker()]
    svg.append(f'<rect width="{w}" height="{h}" fill="#ffffff"/>')

    svg.append(text(20, 25, "Solid / colored = built and measured (Phases 1-3). Dashed / red = tested standalone this phase, not yet wired into rag_utils.py.",
                     size=11, weight="700", color=CLOUD_NAVY, anchor="start"))

    svg.append(rect(20, 220, 130, 65, BLUE, "#666666"))
    svg.append(text(85, 245, "User question", size=11, weight="700", anchor="middle"))
    svg.append(text(85, 263, "demo.py / agent_router.py", size=9, color="#333", anchor="middle"))

    svg.append(rect(190, 50, 780, 430, "none", CLOUD_NAVY, stroke_width=2))
    svg.append(text(205, 75, "AWS Cloud (ca-central-1)", size=13, weight="700", color=CLOUD_NAVY))

    # Guardrail call 1 -- gate, dashed (not yet wired in)
    svg.append(rect(230, 220, 170, 90, "#FDEDED", "#BC1356", dash="4,3"))
    svg.append(text(315, 245, "Bedrock Guardrail", size=10, weight="700", anchor="middle"))
    svg.append(text(315, 260, "Call 1: topic + content gate", size=9, color="#333", anchor="middle"))
    svg.append(text(315, 274, "BLOCKS before retrieve()\nruns -- tested, not wired in", size=8, color="#BC1356", anchor="middle"))

    svg.append(aws_icon(470, 230, 90, 90, "Bedrock Knowledge Base\nZ3Q6F4RTPY\nretrieve()", "ml"))
    svg.append(aws_icon(470, 60, 78, 78, "S3 Vectors\n370 docs, date_numeric", "storage"))
    svg.append(aws_icon(660, 230, 78, 78, "Amazon Nova Lite\nconverse()", "ml"))

    # Guardrail call 2 -- grounding/relevance/PII, dashed (not yet wired in)
    svg.append(rect(660, 350, 220, 110, "#FDEDED", "#BC1356", dash="4,3"))
    svg.append(text(770, 372, "Bedrock Guardrail", size=10, weight="700", anchor="middle"))
    svg.append(text(770, 387, "Call 2: grounding + relevance + PII", size=9, color="#333", anchor="middle"))
    svg.append(text(770, 402, "Tested: 0.92-0.97 grounded scores\non both correct AND a tight wrong\nparaphrase -- catches loose\nfabrications, not tight ones", size=8, color="#BC1356", anchor="middle"))

    svg.append(line(150, 250, 230, 260, label="question"))
    svg.append(line(400, 260, 470, 265, label="if not blocked", lx=435, ly=250))
    svg.append(line(510, 230, 510, 138, label="filtered vector search", lx=560, ly=180))
    svg.append(line(560, 265, 660, 265, label="retrieved chunks -> prompt", lx=610, ly=250))
    svg.append(line(730, 308, 760, 350, dash="4,3", label="generated answer", lx=790, ly=330))
    svg.append(line(660, 400, 400, 300, dash="4,3", label="answer (blocked/anonymized/passed)", lx=500, ly=420))
    svg.append(line(85, 285, 85, 460, dash="4,3"))
    svg.append(line(85, 460, 660, 460, dash="4,3", label="final answer to caller", lx=350, ly=450))

    svg.append("</svg>")
    return "\n".join(svg)


if __name__ == "__main__":
    import sys
    out1, out2 = sys.argv[1], sys.argv[2]
    open(out1, "w").write(diagram1())
    open(out2, "w").write(diagram2())
    print("wrote", out1, out2)
    if len(sys.argv) > 3:
        out3 = sys.argv[3]
        open(out3, "w").write(diagram3())
        print("wrote", out3)
    if len(sys.argv) > 4:
        out4 = sys.argv[4]
        open(out4, "w").write(diagram4())
        print("wrote", out4)
    if len(sys.argv) > 5:
        out5 = sys.argv[5]
        open(out5, "w").write(diagram5())
        print("wrote", out5)
    if len(sys.argv) > 6:
        out6 = sys.argv[6]
        open(out6, "w").write(diagram6())
        print("wrote", out6)
