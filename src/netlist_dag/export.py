import html
import json
import subprocess
from collections import defaultdict
from pathlib import Path

from .errors import BuildError, Diagnostic
from .frontend import executable


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def to_dot(result):
    def quote(text):
        return json.dumps(text, ensure_ascii=False)
    lines = ["digraph circuit {", 'graph [rankdir=LR, bgcolor="#f8fafc", pad="0.4", nodesep="0.3", ranksep="0.8", fontname="Helvetica"];',
             'node [shape=box, style="rounded,filled", fillcolor="white", color="#cbd5e1", fontname="Helvetica", fontsize=11, margin="0.15,0.1"];',
             'edge [color="#64748b", arrowsize=0.7, fontname="Helvetica", fontsize=9];']
    path = result.get("longest_logic_path") or {}
    path_nodes = set(path.get("nodes", []))
    path_edges = set(zip(path.get("nodes", []), path.get("nodes", [])[1:]))
    groups = defaultdict(list)
    for node in result["nodes"]:
        groups[node.get("instance")].append(node)
    loop_nodes = {n for cycle in result["cycles"] for n in cycle["nodes"]}
    for instance in sorted(groups, key=lambda s: s or ""):
        if instance is not None:
            cell = groups[instance][0]["cell_type"]
            lines.extend([f"subgraph {quote('cluster_' + instance)} {{",
                          f"label={quote(instance + ' · ' + cell)}; color=\"#cbd5e1\"; style=rounded;"])
        for node in groups[instance]:
            color = "#fee2e2" if node["id"] in loop_nodes else "#ffedd5" if node["id"] in path_nodes else (
                "#dbeafe" if node["role"] in ("register_input", "register_output") else
                "#e2e8f0" if node["role"] == "clock" else "#dcfce7" if node["kind"] == "port" else "white")
            label = node["pin"] if instance else node["label"]
            if node["role"] in ("register_input", "register_output", "clock"):
                label += "\n" + node["role"].replace("_", " ")
            lines.append(f"{quote(node['id'])} [label={quote(label)}, fillcolor={quote(color)}, tooltip={quote(node['label'])}];")
        if instance is not None:
            lines.append("}")
    for edge in result["edges"]:
        is_cell = edge["kind"] == "cell"
        names = edge.get("net_names", [])
        label = "" if is_cell else (names[0] if names else str(edge.get("net_bit", "")))
        attrs = f"label={quote(label)}, color=\"{'#2563eb' if is_cell else '#64748b'}\""
        if (edge["source"], edge["target"]) in path_edges:
            attrs += ', color="#ea580c", penwidth=3'
        lines.append(f"{quote(edge['source'])} -> {quote(edge['target'])} [{attrs}];")
    for edge in result["control_connections"]:
        lines.append(f"{quote(edge['source'])} -> {quote(edge['target'])} [style=dashed, color=\"#94a3b8\", label=\"clock\", constraint=false];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render(result, out, dot=None, limit=400, timeout=30):
    out = Path(out)
    (out / "graph.dot").write_text(to_dot(result))
    if len(result["nodes"]) > limit:
        return Diagnostic("RENDER_SKIPPED", f"SVG skipped: {len(result['nodes'])} nodes exceeds render limit {limit}; use the cone command", "warning")
    try:
        binary = executable("dot", dot)
        process = subprocess.run([binary, "-Tsvg", str(out / "graph.dot"), "-o", str(out / "graph.svg")],
                                 capture_output=True, text=True, timeout=timeout)
        if process.returncode:
            raise BuildError("RENDER_FAILED", process.stderr[-2000:])
    except (BuildError, subprocess.TimeoutExpired, OSError) as error:
        (out / "graph.svg").unlink(missing_ok=True)
        return Diagnostic("RENDER_FAILED", str(error), "warning")
    return None


def report(out, summary, diagnostics):
    out = Path(out)
    esc = html.escape
    valid = summary.get("valid_dag", False)
    cards = "".join(f'<div class="card"><span>{esc(label)}</span><strong>{esc(str(summary.get(key, "—")))}</strong></div>'
                    for key, label in [("instances", "Cell instances"), ("registers", "Registers"),
                                       ("nodes", "Pins & ports"), ("logic_depth", "Logic depth")])
    rows = "".join(f'<tr><td>{esc(d.severity)}</td><td><code>{esc(d.code)}</code></td><td>{esc(d.message)}</td></tr>' for d in diagnostics)
    drawing = '<object data="graph.svg" type="image/svg+xml"><a href="graph.svg">Open diagram</a></object>' if (out / "graph.svg").exists() else '<p>No SVG generated. See diagnostics or render a smaller cone.</p>'
    path = summary.get("longest_logic_path")
    if path:
        stages = " → ".join(esc(s["instance"] + " (" + s["cell_type"] + ")") for s in path["stages"]) or "Direct connection — no gates"
        path_report = (f'<p><strong>{path["logic_depth"]} combinational stages</strong> · '
                       f'{esc(path["start"])} → {esc(path["end"])}</p><p>{stages}</p>'
                       '<p>One longest path is highlighted in orange. Equal-depth paths use a deterministic tie-break. '
                       'Endpoints may include unused logic outputs. This measures gate depth, not timing delay.</p>')
    else:
        path_report = '<p>No complete longest path available in this report. Invalid circuits are not analyzed; a cone may omit part of the full-design path.</p>'
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Netlist DAG report</title><style>
*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#0f172a;font:15px/1.6 system-ui,sans-serif}main{max-width:1400px;margin:48px auto;padding:0 28px}header{display:flex;align-items:center;justify-content:space-between;gap:24px}h1{font-size:34px;letter-spacing:-1px;margin:8px 0}.eyebrow{font-size:12px;letter-spacing:2px;color:#475569}p{color:#475569}.badge{padding:8px 16px;border-radius:24px;background:BADGECOLOR;font-weight:650}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:28px 0}.card,section{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:22px}.card span{display:block;color:#64748b}.card strong{font-size:32px}section{margin:20px 0}h2{font-size:18px;margin:0 0 12px}object{display:block;width:100%;height:600px;border:0}a{color:#2563eb}nav{display:flex;gap:22px;flex-wrap:wrap}table{width:100%;border-collapse:collapse;font-size:13px}td{border-bottom:1px solid #e2e8f0;padding:10px;vertical-align:top;overflow-wrap:anywhere}code{font-size:12px}@media(max-width:700px){.cards{grid-template-columns:repeat(2,1fr)}header{display:block}object{height:400px}}
</style><main><header><div><div class="eyebrow">NETLIST → DEPENDENCY GRAPH</div><h1>TOP</h1><p>Pin-level connectivity · register boundaries · deterministic analysis</p></div><span class="badge">STATUS</span></header><div class="cards">CARDS</div><section><h2>Longest logic path</h2>PATHREPORT</section><section><h2>Circuit graph</h2><p>Orange: selected longest logic path. Blue arrows: other cell dependencies. Gray arrows: wires. Dashed arrows: clock connections excluded from the data DAG. Register input and output pins are separate boundaries.</p>DRAWING</section><section><h2>Export files</h2><nav><a href="graph.json">Graph JSON</a><a href="graph.dot">Graphviz DOT</a><a href="summary.json">Summary</a><a href="diagnostics.json">Diagnostics</a><a href="manifest.json">Provenance</a></nav></section><section><h2>Diagnostics</h2>DIAGNOSTICS</section><p>Logic depth counts combinational stages; it is not a timing delay. Structural dependencies do not prove that every path is sensitizable.</p></main></html>'''
    for key, replacement in {"BADGECOLOR": "#dcfce7" if valid else "#fee2e2", "TOP": esc(summary.get("top") or "Input validation"),
                             "STATUS": "Valid DAG" if valid else "Needs attention", "CARDS": cards,
                             "DRAWING": drawing, "PATHREPORT": path_report, "DIAGNOSTICS": f"<table>{rows}</table>" if rows else "<p>No issues detected.</p>"}.items():
        page = page.replace(key, replacement)
    (out / "report.html").write_text(page)
