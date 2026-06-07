#!/usr/bin/env python3
"""Render the Luban knowledge graph to a self-contained interactive HTML (vis-network).

Reads the built ``knowledge_graph.json`` (nodes + typed edges) and emits one standalone HTML file with
the REAL graph data embedded — same stack (vis-network) as the existing _syllabus_graph prototype, so it
'wires the kmap to real data'. Node size = content richness (four-source count); colour = top L2 area;
edge colour = relation type (hierarchy grey / prerequisite red-arrow / related blue). Open in a browser.

NO remote / network at build time (vis-network loaded from CDN at view time). Read-only.

Usage:
  python scripts/run_luban_knowledge_graph_viewer.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
GRAPH = _REPO / "artifacts" / "luban_grading_artifacts" / "knowledge_graph_20260606" / "knowledge_graph.json"
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "knowledge_graph_20260606" / "knowledge_graph_viewer.html"

_AREA_COLORS = {  # by L1/L2 area prefix
    "1A411": "#4f9dde", "1A412": "#5fb878", "1A413": "#f7a35c", "1A421": "#9b8cd6",
    "1A422": "#9b8cd6", "1A431": "#e57aa0", "1A432": "#e57aa0", "1A433": "#e57aa0",
    "1A434": "#e57aa0", "1A435": "#e57aa0", "1A436": "#d65f5f", "1A437": "#62c0c0", "1A438": "#c9a227",
}
_EDGE_STYLE = {
    "hierarchy": {"color": "#cfcfcf", "arrows": "", "dashes": False},
    "prerequisite": {"color": "#d65f5f", "arrows": "to", "dashes": False},
    "related": {"color": "#6f9fd8", "arrows": "", "dashes": True},
    "preceding": {"color": "#e0922b", "arrows": "to", "dashes": False},
    "part_of": {"color": "#9b8cd6", "arrows": "to", "dashes": False},
}


def _node_color(code: str) -> str:
    return _AREA_COLORS.get(code[:5], "#bdbdbd")


def run() -> dict[str, Any]:
    g = json.loads(GRAPH.read_text("utf-8"))
    nodes_in = g.get("nodes") or {}
    vnodes = []
    for code, n in nodes_in.items():
        cnt = sum((n.get("counts") or {}).values())
        label = (n.get("name_path") or code).split(" > ")[-1]
        vnodes.append({
            "id": code, "label": label,
            "title": f"{code}\n{n.get('name_path','')}\n四源: {n.get('counts')}",
            "value": 1 + cnt, "color": _node_color(code),
            "shape": "dot" if n.get("populated") else "diamond",
        })
    vedges = []
    for e in g.get("edges") or []:
        st = _EDGE_STYLE.get(e["type"], _EDGE_STYLE["related"])
        conf = e.get("confidence")
        vedges.append({
            "from": e["src"], "to": e["dst"],
            "color": {"color": st["color"], "opacity": 0.55},
            "arrows": st["arrows"], "dashes": st["dashes"],
            "title": f"{e['type']}" + (f" ({conf})" if conf else "")
                     + (f" — {e.get('relation_detail')}" if e.get("relation_detail") else ""),
        })
    html = _HTML.replace("__NODES__", json.dumps(vnodes, ensure_ascii=False)) \
               .replace("__EDGES__", json.dumps(vedges, ensure_ascii=False)) \
               .replace("__STATS__", json.dumps(g.get("stats") or {}, ensure_ascii=False))
    OUT.write_text(html, "utf-8")
    return {"out": str(OUT), "nodes": len(vnodes), "edges": len(vedges)}


_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>鲁班知识图谱 — canonical taxonomy</title>
<!-- local-only viewer (opened from file://). Version pinned for reproducibility. If this is ever
     SERVED on the web, add integrity="sha384-..." crossorigin="anonymous" (Subresource Integrity). -->
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js" crossorigin="anonymous"></script>
<style>
 html,body{margin:0;height:100%;background:#1b1f24;color:#e8e8e8;font-family:-apple-system,sans-serif}
 #net{width:100%;height:calc(100% - 64px)}
 #bar{height:64px;display:flex;align-items:center;gap:18px;padding:0 18px;border-bottom:1px solid #333}
 .lg{font-size:12px;color:#bbb} .sw{display:inline-block;width:22px;height:0;border-top:3px solid;vertical-align:middle;margin-right:5px}
 b{color:#fff}
</style></head><body>
<div id="bar">
 <div><b>鲁班知识图谱</b> <span class="lg" id="st"></span></div>
 <div class="lg"><span class="sw" style="border-color:#cfcfcf"></span>层级</div>
 <div class="lg"><span class="sw" style="border-color:#d65f5f"></span>前置(prerequisite→)</div>
 <div class="lg"><span class="sw" style="border-color:#6f9fd8;border-top-style:dashed"></span>相关(related)</div>
 <div class="lg">● 有内容节点 ◆ 结构节点 · 大小=四源丰富度</div>
</div>
<div id="net"></div>
<script>
 const nodes=new vis.DataSet(__NODES__), edges=new vis.DataSet(__EDGES__), stats=__STATS__;
 document.getElementById('st').textContent=`节点 ${stats.node_count} · 边 ${stats.edge_count} · `+
   Object.entries(stats.edges_by_type||{}).map(([k,v])=>k+':'+v).join(' / ');
 new vis.Network(document.getElementById('net'),{nodes,edges},{
   nodes:{font:{color:'#e8e8e8',size:13},scaling:{min:6,max:42}},
   edges:{smooth:{type:'continuous'},width:0.6},
   physics:{barnesHut:{gravitationalConstant:-9000,springLength:130,springConstant:0.02},stabilization:{iterations:220}},
   interaction:{hover:true,tooltipDelay:120}
 });
</script></body></html>"""


def main() -> int:
    r = run()
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
