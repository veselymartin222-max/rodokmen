import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

BASE = Path(__file__).parent
DATA = json.loads((BASE / 'rodokmen_data.json').read_text(encoding='utf-8'))
NODES = DATA['nodes']
EDGES = DATA['edges']
STATS = DATA['stats']

st.set_page_config(page_title='Rodokmen', page_icon='🌳', layout='wide')
st.title('🌳 Rodokmen')
st.caption('Interaktivní zobrazení rodokmenu z ODS s doplněním údajů z GEDCOMu.')

byid = {n['id']: n for n in NODES}
adj = {n['id']: set() for n in NODES}
parents = {n['id']: set() for n in NODES}
children = {n['id']: set() for n in NODES}
spouses = {n['id']: set() for n in NODES}
for e in EDGES:
    s, t = e['source'], e['target']
    if s not in byid or t not in byid:
        continue
    adj[s].add(t); adj[t].add(s)
    if e['type'].startswith('parent'):
        parents[t].add(s)
        children[s].add(t)
    elif e['type'] == 'spouse':
        spouses[s].add(t); spouses[t].add(s)

def neighborhood(start, generations=4):
    if not start:
        return set(byid)
    seen = {start}; frontier = {start}
    for _ in range(generations):
        nxt = set()
        for u in frontier:
            nxt.update(adj[u] - seen)
        seen |= nxt; frontier = nxt
        if not frontier: break
    return seen

options = []
counts = {}
for n in NODES:
    counts[n['name']] = counts.get(n['name'], 0) + 1
for n in NODES:
    label = n['name'] if counts[n['name']] == 1 else f"{n['name']}  [{n['row']},{n['col']}]"
    options.append((label, n['id']))

with st.sidebar:
    st.header('Zobrazení')
    mode = st.radio('Rozsah', ['Celý rodokmen', 'Od vybrané osoby'], index=0)
    selected = None
    generations = 4
    if mode == 'Od vybrané osoby':
        label = st.selectbox('Vyber osobu', [x[0] for x in options], index=0)
        selected = dict(options)[label]
        generations = st.slider('Počet vazeb od osoby', 1, 8, 4)

    layout = st.radio('Podoba stromu', ['ODS – zleva doprava', 'Klasický strom – shora dolů'], index=0)

    st.divider()
    st.write(f"**ODS:** {STATS['ods_person_cells']} osobních záznamů")
    st.write(f"**Různých jmen:** {STATS['ods_distinct_names']}")
    st.write(f"**GEDCOM:** {STATS['ged_people']} osob")
    st.write(f"**Doplněno z GEDCOM:** {STATS['matched_unique']}")
    st.write(f"**Nejednoznačné shody:** {STATS['ambiguous']}")
    st.write(f"**Bez shody:** {STATS['unmatched']}")

keep = neighborhood(selected, generations) if mode == 'Od vybrané osoby' else set(byid)
subnodes = [n for n in NODES if n['id'] in keep]
subedges = [e for e in EDGES if e['source'] in keep and e['target'] in keep]

st.subheader(f"{mode} · {layout}: {len(subnodes)} osob")

payload = json.dumps({
    'nodes': subnodes,
    'edges': subedges,
    'selected': selected,
    'mode': mode,
    'layout': layout,
}, ensure_ascii=False)

html = f'''<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<style>
html,body,#wrap{{margin:0;width:100%;height:100%;overflow:hidden;font-family:Arial,sans-serif}}
#wrap{{position:relative;background:#fafafa}}
svg{{width:100%;height:100%;cursor:grab}} svg:active{{cursor:grabbing}}
.edge{{stroke:#888;stroke-width:1.5;fill:none;opacity:.72}}
.edge.spouse{{stroke:#b66;stroke-width:2.2;stroke-dasharray:5 4}}
.node rect{{stroke:#555;stroke-width:1;rx:7;ry:7}}
.node text{{font-size:12px;pointer-events:none}}
#info{{position:absolute;right:12px;top:12px;width:290px;max-height:calc(100% - 24px);overflow:auto;background:rgba(255,255,255,.97);border:1px solid #bbb;border-radius:8px;padding:12px;box-shadow:0 2px 10px rgba(0,0,0,.15);font-size:13px}}
#info h3{{margin:0 0 8px;font-size:17px}}
#hint{{position:absolute;left:12px;top:12px;background:rgba(255,255,255,.92);border:1px solid #ccc;border-radius:6px;padding:7px 10px;font-size:12px}}
</style></head><body><div id="wrap"><svg></svg>
<div id="hint">Kolečko = zoom · tažení = posun · kliknutí = detail</div>
<div id="info"><h3>Vyber osobu</h3>Klikni na libovolné jméno.</div></div>
<script>
const data = {payload};
const W = window.innerWidth, H = window.innerHeight;
const svg = d3.select('svg');
const g = svg.append('g');
const zoom = d3.zoom().scaleExtent([0.01, 6]).on('zoom', e => g.attr('transform', e.transform));
svg.call(zoom);
const nodes = data.nodes.map(d => ({{...d}}));
const by = new Map(nodes.map(d => [d.id,d]));
const links = data.edges.map(e => ({{...e,source:by.get(e.source),target:by.get(e.target)}})).filter(e => e.source && e.target);

function parentLinks() {{ return links.filter(e => e.type.startsWith('parent')); }}

function layoutODS() {{
    // Použijeme pevné rozestupy podle původních řádků a sloupců ODS.
    // Díky tomu se jména nesrazí ani při zobrazení velkého stromu.
    const left=110, top=60, colGap=240, rowGap=64;
    nodes.forEach(d => {{
        d.x = left + d.col * colGap;
        d.y = top + (d.row-1) * rowGap;
    }});
}}

function layoutClassic() {{
    const ps = new Map(nodes.map(d=>[d.id,new Set()]));
    const cs = new Map(nodes.map(d=>[d.id,new Set()]));
    const spouseMap = new Map(nodes.map(d=>[d.id,new Set()]));
    parentLinks().forEach(e=>{{
        ps.get(e.target.id).add(e.source.id);
        cs.get(e.source.id).add(e.target.id);
    }});
    links.filter(e=>e.type==='spouse').forEach(e=>{{
        spouseMap.get(e.source.id).add(e.target.id);
        spouseMap.get(e.target.id).add(e.source.id);
    }});

    // Generace: předkové nahoře, děti pod nimi.
    const gen = new Map();
    if (data.mode === 'Od vybrané osoby' && data.selected) {{
        const root=data.selected;
        gen.set(root,0);
        let front=[root];
        for(let step=1;step<=50 && front.length;step++) {{
            const next=[];
            front.forEach(id=>ps.get(id).forEach(p=>{{
                if(!gen.has(p)){{gen.set(p,-step);next.push(p);}}
            }}));
            front=next;
        }}
        front=[root];
        for(let step=1;step<=50 && front.length;step++) {{
            const next=[];
            front.forEach(id=>cs.get(id).forEach(c=>{{
                if(!gen.has(c)){{gen.set(c,step);next.push(c);}}
            }}));
            front=next;
        }}
    }} else {{
        const roots=nodes.filter(d=>ps.get(d.id).size===0).map(d=>d.id);
        roots.forEach(id=>gen.set(id,0));
        let front=roots;
        for(let step=1;step<=80 && front.length;step++) {{
            const next=[];
            front.forEach(id=>cs.get(id).forEach(c=>{{
                if(!gen.has(c)){{gen.set(c,step);next.push(c);}}
                else if(gen.get(c)<step) gen.set(c,step);
            }}));
            front=next;
        }}
        nodes.forEach(d=>{{if(!gen.has(d.id)) gen.set(d.id,0);}});
        // U vícegeneračních větví použijeme nejdelší cestu od kořene,
        // aby rodič nikdy neskončil pod vlastním dítětem.
        for(let pass=0;pass<nodes.length;pass++) {{
            let changed=false;
            parentLinks().forEach(e=>{{
                const next=gen.get(e.source.id)+1;
                if(next>gen.get(e.target.id)) {{gen.set(e.target.id,next);changed=true;}}
            }});
            if(!changed) break;
        }}
    }}

    const groups=d3.group(nodes,d=>gen.get(d.id));
    const levels=Array.from(groups.keys()).sort((a,b)=>a-b);
    const order=new Map();
    // Původní ODS pořadí je výchozí vodítko, aby větve zůstaly rozpoznatelné.
    levels.forEach(gv=>{{
        groups.get(gv).sort((a,b)=>(a.row-b.row)||(a.col-b.col)||a.name.localeCompare(b.name,'cs'));
        order.set(gv,groups.get(gv).map(d=>d.id));
    }});

    // Několik průchodů řadí každou generaci podle polohy rodičů i dětí.
    // Tím se větve seskupí a rodiče se vizuálně drží nad svými potomky.
    for(let pass=0;pass<8;pass++) {{
        const down = pass%2===0;
        const seq = down ? levels : [...levels].reverse();
        seq.forEach(gv=>{{
            const ids=order.get(gv);
            const pos=new Map();
            levels.forEach(l=>order.get(l).forEach((id,i)=>pos.set(id,i)));
            ids.sort((a,b)=>{{
                const related=id=>{{
                    const set=down?ps.get(id):cs.get(id);
                    const vals=[...set].map(x=>pos.get(x)).filter(Number.isFinite);
                    if(vals.length) return vals.reduce((x,y)=>x+y,0)/vals.length;
                    const n=by.get(id); return n.row*0.001+n.col*0.0001;
                }};
                return related(a)-related(b) || by.get(a).row-by.get(b).row || a.localeCompare(b);
            }});
        }});
    }}

    const cardW=190, cardH=46, gapX=42, levelGap=128;
    const maxCount=d3.max(levels,gv=>order.get(gv).length)||1;
    const canvasW=maxCount*(cardW+gapX)+160;
    const top=80;
    levels.forEach((gv,levelIndex)=>{{
        const ids=order.get(gv);
        const rowWidth=ids.length*(cardW+gapX)-gapX;
        const startX=(canvasW-rowWidth)/2+cardW/2;
        ids.forEach((id,i)=>{{
            const d=by.get(id);
            d.x=startX+i*(cardW+gapX);
            d.y=top+levelIndex*levelGap;
            d.generation=gv;
        }});
    }});

    // Manžele necháme ve stejné generaci a snažíme se je umístit vedle sebe,
    // pouze pokud tím nevznikne překrytí; pevné rozestupy zůstávají zachovány.
    const idToIndex=new Map();
    levels.forEach(gv=>order.get(gv).forEach((id,i)=>idToIndex.set(id,{{gv,i}})));
}}

if(data.layout.startsWith('ODS')) layoutODS(); else layoutClassic();

const edge = g.selectAll('.edge').data(links).join('path').attr('class',d=>'edge '+d.type);
const node = g.selectAll('.node').data(nodes).join('g').attr('class','node')
    .attr('transform',d=>`translate(${{d.x}},${{d.y}})`).on('click',(ev,d)=>showInfo(d));
node.append('rect').attr('x',-95).attr('y',-23).attr('width',190).attr('height',46)
    .attr('fill',d=>d.id===data.selected?'#dff0ff':'white');
node.each(function(d){{
    const text=d3.select(this).append('text').attr('text-anchor','middle').attr('font-size',11);
    const words=String(d.name).split(/\\s+/);
    let lines=[''];
    words.forEach(word=>{{let last=lines.length-1; if((lines[last]+' '+word).trim().length>23 && lines[last]) lines.push(word); else lines[last]=(lines[last]+' '+word).trim();}});
    if(lines.length>2) lines=[lines[0],lines.slice(1).join(' ').slice(0,23)+'…'];
    lines.forEach((line,i)=>text.append('tspan').attr('x',0).attr('dy',i===0?(lines.length===1?4:-3):14).text(line));
}});

function drawEdge(e) {{
    if(data.layout.startsWith('ODS')) {{ const mx=(e.source.x+e.target.x)/2; return `M${{e.source.x}},${{e.source.y}} H${{mx}} V${{e.target.y}} H${{e.target.x}}`; }}
    if(e.type==='spouse') return `M${{e.source.x}},${{e.source.y}} L${{e.target.x}},${{e.target.y}}`;
    const mid=(e.source.y+e.target.y)/2;
    return `M${{e.source.x}},${{e.source.y+23}} C${{e.source.x}},${{mid}} ${{e.target.x}},${{mid}} ${{e.target.x}},${{e.target.y-23}}`;
}}
edge.attr('d',drawEdge);

function showInfo(d) {{
 const i=document.getElementById('info'), p=d.info||{{}};
 let h='<h3>'+escapeHtml(d.name)+'</h3>';
 if(d.ged_id){{h+='<div><b>GEDCOM:</b> '+escapeHtml(d.ged_id)+'</div>'; if(p.birth)h+='<div><b>Narození:</b> '+escapeHtml(p.birth)+(p.birth_place?' — '+escapeHtml(p.birth_place):'')+'</div>'; if(p.death)h+='<div><b>Úmrtí:</b> '+escapeHtml(p.death)+(p.death_place?' — '+escapeHtml(p.death_place):'')+'</div>'; if(p.sex)h+='<div><b>Pohlaví:</b> '+escapeHtml(p.sex)+'</div>'; if(p.occupation)h+='<div><b>Povolání:</b> '+escapeHtml(p.occupation)+'</div>'; if(p.married_names&&p.married_names.length)h+='<div><b>Další příjmení:</b> '+escapeHtml(p.married_names.join(', '))+'</div>';}}
 else if(d.ged_ids&&d.ged_ids.length){{h+='<div><b>GEDCOM:</b> více možných osob ('+d.ged_ids.length+')</div><div>'+escapeHtml(d.ged_ids.join(', '))+'</div>';}}
 else h+='<div>V GEDCOMu nebyla nalezena jednoznačná shoda.</div>';
 i.innerHTML=h;
}}
function escapeHtml(s){{return String(s).replace(/[&<>'\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}}[c]));}}

setTimeout(()=>{{
 const box=g.node().getBBox();
 if(box.width&&box.height){{
   const k=Math.min((W-40)/box.width,(H-40)/box.height,1.4);
   const tx=W/2-(box.x+box.width/2)*k, ty=H/2-(box.y+box.height/2)*k;
   svg.call(zoom.transform,d3.zoomIdentity.translate(tx,ty).scale(k));
 }}
}},100);
</script></body></html>'''

components.html(html, height=780, scrolling=False)

if selected:
    n = byid[selected]
    st.info(f"Vybraná osoba: **{n['name']}**. Kliknutím na osobu v grafu se zobrazí její dostupné údaje z GEDCOMu.")
else:
    st.info('Klikni na osobu v grafu. Kolečkem myši přibližuješ/oddaluješ a tažením se pohybuješ po stromu.')
