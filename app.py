import base64
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ------------------------------------------------------------
# DATA & OBRÁZEK POZADÍ
# ------------------------------------------------------------

BASE = Path(__file__).parent
DATA = json.loads((BASE / "rodokmen_data.json").read_text(encoding="utf-8"))

NODES = DATA["nodes"]
EDGES = DATA["edges"]
STATS = DATA.get("stats", {})

bg_base64 = ""
for fname in ["Strom.jpg", "Strom.png", "strom.jpg", "strom.png"]:
    p = BASE / fname
    if p.exists():
        encoded = base64.b64encode(p.read_bytes()).decode()
        ext = "jpeg" if p.suffix.lower() in [".jpg", ".jpeg"] else "png"
        bg_base64 = f"data:image/{ext};base64,{encoded}"
        break

st.set_page_config(page_title="Rodokmen", page_icon="🌳", layout="wide")
st.title("🌳 Rodokmen")
st.caption("Interaktivní rodokmen s vycentrovaným tiskem na střed stránky.")

# ------------------------------------------------------------
# VZTAHY A VAZEBNÍ LOGIKA
# ------------------------------------------------------------

byid = {n["id"]: n for n in NODES}
parents = {n["id"]: set() for n in NODES}
children = {n["id"]: set() for n in NODES}
spouses = {n["id"]: set() for n in NODES}

RELATION_TYPES = {"parent", "parent_manual", "parent_ods", "spouse"}

for e in EDGES:
    source, target, edge_type = e.get("source"), e.get("target"), e.get("type")
    if source not in byid or target not in byid or edge_type not in RELATION_TYPES:
        continue

    if edge_type in {"parent", "parent_manual", "parent_ods"}:
        parents[target].add(source)
        children[source].add(target)
    elif edge_type == "spouse":
        spouses[source].add(target)
        spouses[target].add(source)

root_candidates = [n for n in NODES if n.get("name") == "Terezie Slívová"]
ROOT_ID = root_candidates[0]["id"] if root_candidates else (NODES[0]["id"] if NODES else None)

# ------------------------------------------------------------
# PODSTROM
# ------------------------------------------------------------

def ods_subtree(start_id, generations=4):
    if not start_id or start_id not in byid:
        return set(byid.keys())

    visited = {start_id}
    current_level = {start_id}

    for _ in range(generations):
        next_level = set()
        for p_id in current_level:
            for c_id in children.get(p_id, []):
                if c_id not in visited:
                    next_level.add(c_id)
            for s_id in spouses.get(p_id, []):
                if s_id not in visited:
                    next_level.add(s_id)
        if not next_level:
            break
        visited.update(next_level)
        current_level = next_level

    extra_spouses = set()
    for p_id in visited:
        for s_id in spouses.get(p_id, []):
            extra_spouses.add(s_id)
    visited.update(extra_spouses)

    return visited

# ------------------------------------------------------------
# POSTRANNÍ PANEL
# ------------------------------------------------------------

name_counts = {}
for n in NODES:
    name = str(n.get("name", "")).strip()
    name_counts[name] = name_counts.get(name, 0) + 1

def person_label(person_id):
    person = byid[person_id]
    name = person.get("name", "Neznámá osoba")
    return f"{name} [{person.get('row', '?')},{person.get('col', '?')}]" if name_counts.get(name, 0) > 1 else name

person_ids = [n["id"] for n in NODES]
default_index = person_ids.index(ROOT_ID) if ROOT_ID in person_ids else 0

with st.sidebar:
    st.header("Zobrazení")
    mode = st.radio("Rozsah", ["Celý rodokmen", "Od vybrané osoby"], index=0)
    selected = None
    generations = 4

    if mode == "Od vybrané osoby":
        selected = st.selectbox("Vyber osobu", person_ids, index=default_index, format_func=person_label)
        generations = st.slider("Počet generací", min_value=1, max_value=8, value=4)

    st.divider()

# ------------------------------------------------------------
# FILTROVÁNÍ DATA
# ------------------------------------------------------------

keep = set(byid.keys()) if mode == "Celý rodokmen" else ods_subtree(selected, generations)
subnodes = [n for n in NODES if n["id"] in keep]
subedges = [e for e in EDGES if e.get("source") in keep and e.get("target") in keep]

st.subheader(f"{mode} · {len(subnodes)} osob")

payload = json.dumps({
    "nodes": subnodes,
    "edges": subedges,
    "selected": selected,
    "root": ROOT_ID,
    "bg_base64": bg_base64
}, ensure_ascii=False)

# ------------------------------------------------------------
# D3 HTML ŠABLONA
# ------------------------------------------------------------

html_template = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<style>
html, body {
    margin: 0; padding: 0; width: 100%; height: 100%;
    overflow: hidden; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

#wrap {
    position: relative; width: 100vw; height: 100vh;
    background-size: contain;
    background-position: center center;
    background-repeat: no-repeat;
    background-color: #f4f3ef;
}

#wrap.no-bg {
    background-image: none !important;
    background-color: #ffffff !important;
}

svg {
    width: 100%; height: 100%; cursor: grab; display: block;
}
svg:active { cursor: grabbing; }

.edge {
    stroke: #2b3e2b;
    stroke-width: 2px;
    fill: none;
    opacity: 0.85;
}
.edge.spouse {
    stroke: #b33a3a;
    stroke-width: 2px;
    stroke-dasharray: 4 4;
}

.node rect {
    stroke: #2b3e2b;
    stroke-width: 1.5px;
    rx: 6px; ry: 6px;
    fill: rgba(255, 255, 255, 0.95);
}
.node:hover rect {
    stroke-width: 2.5px;
    fill: #ffffff;
}

.node text {
    font-size: 12px;
    font-weight: 600;
    fill: #111;
    pointer-events: none;
}

#info {
    position: absolute; right: 14px; top: 14px; width: 280px;
    max-height: calc(100% - 80px); overflow-y: auto;
    background: rgba(255,255,255,0.96); border: 1px solid #b5b5b5;
    border-radius: 8px; padding: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    font-size: 13px; z-index: 10;
}
#info h3 { margin: 0 0 8px 0; font-size: 16px; color: #2b3e2b; }

#tools {
    position: absolute; left: 14px; bottom: 14px; display: flex; gap: 8px; z-index: 10;
    background: rgba(255,255,255,0.92); padding: 6px 10px; border-radius: 8px; border: 1px solid #ccc;
}
#tools button {
    background: white; border: 1px solid #888; border-radius: 5px;
    padding: 6px 10px; font-size: 12px; cursor: pointer; font-weight: bold;
}
#tools button:hover { background: #eef4ee; }

/* TISKOVÉ STYLY */
@media print {
    #tools, #info { display: none !important; }
    html, body, #wrap {
        width: 100% !important;
        height: 100% !important;
        overflow: visible !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }
    svg {
        width: 100% !important;
        height: 100% !important;
    }
}
</style>
</head>

<body>
<div id="wrap">
<svg id="mainsvg"></svg>

<div id="tools">
    <button onclick="printTree()">🖨 Tisk / PDF</button>
    <button onclick="toggleBackground()">🖼 Pozadí (Zap/Vyp)</button>
    <button onclick="fitTree()">⛶ Vycentrovat</button>
    <button onclick="changeFontSize(-1)">A-</button>
    <button onclick="changeFontSize(1)">A+</button>
</div>

<div id="info">
    <h3>Detail osoby</h3>
    Klikněte na jakoukoliv osobu v rodokmenu.
</div>
</div>

<script>
let currentFontSize = 12;
let showBg = true;

try {
    const data = __PAYLOAD__;
    const wrap = document.getElementById("wrap");

    if (data.bg_base64) {
        wrap.style.backgroundImage = "url('" + data.bg_base64 + "')";
    }

    const svg = d3.select("#mainsvg");
    const g = svg.append("g");

    const zoom = d3.zoom()
        .scaleExtent([0.05, 4])
        .on("zoom", e => g.attr("transform", e.transform));

    svg.call(zoom);

    const rawNodes = data.nodes;
    const rawEdges = data.edges;

    const nodeMap = new Map(rawNodes.map(n => [n.id, { ...n, children: [] }]));
    let rootNode = nodeMap.get(data.root) || nodeMap.get(data.selected) || nodeMap.values().next().value;

    rawEdges.forEach(e => {
        if (e.type !== "spouse" && nodeMap.has(e.source) && nodeMap.has(e.target)) {
            const parent = nodeMap.get(e.source);
            const child = nodeMap.get(e.target);
            if (!parent.children.includes(child)) {
                parent.children.push(child);
            }
        }
    });

    const hierarchy = d3.hierarchy(rootNode);
    const treeLayout = d3.tree().nodeSize([220, 140]);

    treeLayout(hierarchy);

    const nodes = hierarchy.descendants();
    const links = hierarchy.links();

    const edge = g.selectAll(".edge")
        .data(links)
        .join("path")
        .attr("class", "edge")
        .attr("d", d => {
            const sx = d.source.x, sy = d.source.y;
            const tx = d.target.x, ty = d.target.y;
            const midY = (sy + ty) / 2;
            return "M" + sx + "," + (sy + 22) +
                   " V" + midY +
                   " H" + tx +
                   " V" + (ty - 22);
        });

    const node = g.selectAll(".node")
        .data(nodes)
        .join("g")
        .attr("class", "node")
        .attr("transform", d => "translate(" + d.x + "," + d.y + ")")
        .on("click", (ev, d) => showInfo(d.data));

    node.append("rect")
        .attr("x", -90)
        .attr("y", -22)
        .attr("width", 180)
        .attr("height", 44)
        .attr("fill", d => d.data.id === data.selected ? "#fff3cd" : "rgba(255,255,255,0.95)")
        .attr("stroke", d => d.data.id === data.selected ? "#856404" : "#2b3e2b");

    node.each(function(d) {
        const text = d3.select(this)
            .append("text")
            .attr("text-anchor", "middle")
            .attr("font-size", currentFontSize + "px");

        const words = String(d.data.name || "Neznámý").split(/\s+/);
        let lines = [""];

        words.forEach(word => {
            const last = lines.length - 1;
            if ((lines[last] + " " + word).trim().length > 20 && lines[last]) {
                lines.push(word);
            } else {
                lines[last] = (lines[last] + " " + word).trim();
            }
        });

        lines.forEach((line, i) => {
            text.append("tspan")
                .attr("x", 0)
                .attr("dy", i === 0 ? (lines.length === 1 ? 4 : -2) : 13)
                .text(line);
        });
    });

    function toggleBackground() {
        showBg = !showBg;
        if (showBg) {
            wrap.classList.remove("no-bg");
        } else {
            wrap.classList.add("no-bg");
        }
    }

    function changeFontSize(delta) {
        currentFontSize = Math.max(8, Math.min(22, currentFontSize + delta));
        g.selectAll(".node text").attr("font-size", currentFontSize + "px");
    }

    function fitTree() {
        const bbox = g.node().getBBox();
        if (!bbox.width || !bbox.height) return;

        const usableW = window.innerWidth - 80;
        const usableH = window.innerHeight - 80;

        let k = Math.min(usableW / bbox.width, usableH / bbox.height);
        k = Math.max(0.15, Math.min(k, 1.0));

        const tx = (window.innerWidth / 2) - (bbox.x + bbox.width / 2) * k;
        const ty = (window.innerHeight / 2) - (bbox.y + bbox.height / 2) * k;

        svg.transition().duration(300).call(
            zoom.transform,
            d3.zoomIdentity.translate(tx, ty).scale(k)
        );
    }

    /* VYCENTROVANÝ TISK */
    function printTree() {
        const oldTransform = d3.zoomTransform(svg.node());
        g.attr("transform", "translate(0,0)");

        const box = g.node().getBBox();
        const pad = 50;

        if (box.width && box.height) {
            svg.attr(
                "viewBox",
                (box.x - pad) + " " + (box.y - pad) + " " +
                (box.width + 2 * pad) + " " +
                (box.height + 2 * pad)
            );
        }

        window.print();

        setTimeout(() => {
            svg.attr("viewBox", null);
            svg.call(zoom.transform, oldTransform);
        }, 500);
    }

    function showInfo(d) {
        const info = document.getElementById("info");
        const p = d.info || {};

        let h = "<h3>" + escapeHtml(d.name || "") + "</h3>";
        if (d.ged_id) {
            h += "<div><b>GEDCOM ID:</b> " + escapeHtml(d.ged_id) + "</div>";
            if (p.birth) h += "<div><b>Narození:</b> " + escapeHtml(p.birth) + "</div>";
            if (p.death) h += "<div><b>Úmrtí:</b> " + escapeHtml(p.death) + "</div>";
        } else {
            h += "<div style='color:#666;'>Bez detailních dat z GEDCOM.</div>";
        }
        info.innerHTML = h;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>'"]/g, c => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
        }[c]));
    }

    window.fitTree = fitTree;
    window.printTree = printTree;
    window.changeFontSize = changeFontSize;
    window.toggleBackground = toggleBackground;

    setTimeout(fitTree, 200);

} catch (err) {
    document.getElementById("wrap").innerHTML = "<div style='color:red; padding:20px;'><b>Chyba:</b><br><pre>" + err.stack + "</pre></div>";
}
</script>
</body>
</html>"""

html = html_template.replace("__PAYLOAD__", payload)
components.html(html, height=800, scrolling=False)