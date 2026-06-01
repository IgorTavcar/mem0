#!/usr/bin/env python3
"""mem0 wiki generator.

Reads agent-authored page bodies from wiki/_src/bodies/<slug>.html and metadata
from wiki/_src/pages.json, then emits a consistent, cross-linked static site:
final <slug>.html pages, index.html, glossary.html, concepts.json and
search-index.json. Run from the repo root: `python wiki/_build.py`.

Pure standard library. Idempotent / re-runnable.
"""
from __future__ import annotations
import html
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # wiki/
REPO = ROOT.parent                              # repo root
SRC = ROOT / "_src"
BODIES = SRC / "bodies"

# --------------------------------------------------------------------------
# Page manifest (order = sidebar order). group drives nav + breadcrumb.
# kind: "body"  -> body comes from _src/bodies/<slug>.html
#       "gen"   -> body generated here (index, glossary)
# --------------------------------------------------------------------------
PAGES = [
    ("index",          "Home",                       "",           "gen",  "Project overview, knowledge graph and quick access."),
    ("architecture",   "Architecture Overview",      "Overview",   "body", "Monorepo layout, the two usage modes, the provider plugin pattern, config-driven wiring."),
    ("data-flow",      "Data Flow",                  "Overview",   "body", "End-to-end add() and search() sequences through the engine."),
    ("memory-engine",  "Memory Engine",              "Core",       "body", "Memory / AsyncMemory internals: methods, async, concurrency, SQLite history, telemetry."),
    ("memory-algorithm","Memory Algorithm",          "Core",       "body", "Single-pass ADD-only extraction, multi-signal retrieval, entity linking, temporal reasoning."),
    ("config-system",  "Configuration System",       "Core",       "body", "MemoryConfig, provider configs, enums, the four factories."),
    ("llms",           "LLM Providers",              "Providers",  "body", "LLM provider layer: base class, all providers, structured output."),
    ("embeddings",     "Embedding Providers",        "Providers",  "body", "Embeddings layer: base class, all providers, dimensions."),
    ("vector-stores",  "Vector Stores",              "Providers",  "body", "Vector store layer: base class, all providers, the common interface."),
    ("rerankers",      "Rerankers",                  "Providers",  "body", "Reranker layer and where reranking fits in retrieval."),
    ("graph-memory",   "Graph Memory (deprecated)",  "Providers",  "body", "Status and history of graph memory; its removal; replacement by entity linking."),
    ("client-sdk",     "Hosted Client & Proxy",      "Interfaces", "body", "MemoryClient / AsyncMemoryClient, the proxy LLM wrapper, project APIs."),
    ("server",         "Self-Hosted Server",         "Interfaces", "body", "FastAPI REST server: auth, API keys, routers, rate limiting, Docker."),
    ("typescript-sdk", "TypeScript SDK",             "Interfaces", "body", "mem0-ts: hosted client + OSS Memory, provider parity, build/test."),
    ("openmemory",     "OpenMemory Platform",        "Interfaces", "body", "Self-hosted platform: FastAPI+Alembic+MCP api/ and Next.js ui/."),
    ("integrations",   "Integrations & Ecosystem",   "Ecosystem",  "body", "CLI, mem0-plugin (MCP, hooks), OpenClaw, Vercel AI provider, skills."),
    ("evaluation",     "Evaluation & Benchmarks",    "Ecosystem",  "body", "LoCoMo / LongMemEval / BEAM benchmarks, experiment runner, baselines."),
    ("surprises",      "Surprises & Gotchas",        "Meta",       "body", "Cross-cutting clever patterns, gotchas, perf/security surprises, deprecations."),
    ("glossary",       "Glossary & Concept Index",   "Meta",       "gen",  "All concepts indexed and grouped."),
]
GROUP_ORDER = ["Overview", "Core", "Providers", "Interfaces", "Ecosystem", "Meta"]
PAGE_BY_SLUG = {p[0]: p for p in PAGES}
TITLE = {p[0]: p[1] for p in PAGES}
GROUP = {p[0]: p[2] for p in PAGES}

# --------------------------------------------------------------------------
# Load metadata
# --------------------------------------------------------------------------
meta_path = SRC / "pages.json"
if not meta_path.exists():
    raise SystemExit("missing wiki/_src/pages.json — write it from the workflow result first")
DATA = json.loads(meta_path.read_text())
GENERATED = DATA.get("generated", "2026-06-01")
PAGE_META = {p["slug"]: p for p in DATA.get("pages", [])}
SURPRISES_META = DATA.get("surprises", {})
# inject surprises into PAGE_META so it participates in graph/search uniformly
if SURPRISES_META:
    PAGE_META.setdefault("surprises", {
        "slug": "surprises",
        "title": "Surprises & Gotchas",
        "summary": SURPRISES_META.get("summary", ""),
        "concepts": SURPRISES_META.get("concepts", []),
        "crossLinks": {"uses": [], "usedBy": [], "related": SURPRISES_META.get("related", [])},
        "codeRefs": [],
        "searchTerms": SURPRISES_META.get("searchTerms", []),
    })

def summary_of(slug: str) -> str:
    if slug in PAGE_META and PAGE_META[slug].get("summary"):
        return PAGE_META[slug]["summary"]
    return PAGE_BY_SLUG.get(slug, (None, "", "", "", ""))[4]

# --------------------------------------------------------------------------
# Provider counts (computed from the actual repo for accurate metrics)
# --------------------------------------------------------------------------
def count_providers(rel: str) -> int:
    d = REPO / rel
    if not d.is_dir():
        return 0
    skip = {"__init__.py", "base.py", "configs.py", "utils.py"}
    return sum(1 for f in d.glob("*.py") if f.name not in skip)

COUNTS = {
    "llms": count_providers("mem0/llms"),
    "embeddings": count_providers("mem0/embeddings"),
    "vector-stores": count_providers("mem0/vector_stores"),
    "rerankers": count_providers("mem0/reranker"),
}

# --------------------------------------------------------------------------
# Shell template
# --------------------------------------------------------------------------
PRISM = "https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/"

def nav_html(active: str) -> str:
    out = []
    home_cls = " class=\"active\"" if active == "index" else ""
    out.append(f'<div class="nav-group"><a href="index.html"{home_cls}>&#127968; Home</a></div>')
    for g in GROUP_ORDER:
        links = []
        for slug, title, grp, kind, _desc in PAGES:
            if grp != g:
                continue
            cls = ' class="active"' if slug == active else ""
            links.append(f'<a href="{slug}.html"{cls}>{html.escape(title)}</a>')
        if links:
            out.append(f'<div class="nav-group"><div class="nav-label">{g}</div>{"".join(links)}</div>')
    return "\n".join(out)

def breadcrumb_html(slug: str) -> str:
    if slug == "index":
        return '<nav class="breadcrumb" aria-label="Breadcrumb"><span>Home</span></nav>'
    grp = GROUP.get(slug, "")
    return (f'<nav class="breadcrumb" aria-label="Breadcrumb">'
            f'<a href="index.html">Home</a><span class="sep">/</span>'
            f'<span>{html.escape(grp)}</span><span class="sep">/</span>'
            f'<span>{html.escape(TITLE.get(slug, slug))}</span></nav>')

def shell(slug: str, title: str, summary: str, body: str, *, is_home=False) -> str:
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": title,
        "description": summary,
        "keywords": ", ".join(PAGE_META.get(slug, {}).get("searchTerms", [])[:12]),
        "isPartOf": {"@type": "WebSite", "name": "mem0 wiki", "url": "index.html"},
    }, ensure_ascii=False)
    page_title = "mem0 wiki" if is_home else f"{title} · mem0 wiki"
    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{html.escape(summary)}">
<meta name="generator" content="mem0-wiki-build">
<title>{html.escape(page_title)}</title>
<script>(function(){{try{{var t=localStorage.getItem('mem0-wiki-theme');if(t!=='light'&&t!=='dark'){{t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark';}}document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<link rel="stylesheet" href="style.css">
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header class="topbar">
  <button id="menu-toggle" class="icon-btn" aria-label="Toggle navigation">&#9776;</button>
  <a class="brand" href="index.html">mem0&nbsp;<span>wiki</span></a>
  <div class="search" role="search">
    <input id="search-input" type="search" placeholder="Search the wiki…  ( / )" autocomplete="off" aria-label="Search">
    <div id="search-results" role="listbox"></div>
  </div>
  <button id="theme-toggle" class="icon-btn" aria-label="Toggle theme">&#9680;</button>
  <a class="gh" href="https://github.com/mem0ai/mem0" target="_blank" rel="noopener">GitHub&nbsp;&#8599;</a>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar" aria-label="Site navigation">
    {nav_html(slug)}
  </aside>
  <main class="content" id="content">
    {breadcrumb_html(slug)}
    {body}
  </main>
</div>
<script src="{PRISM}components/prism-core.min.js"></script>
<script src="{PRISM}plugins/autoloader/prism-autoloader.min.js"></script>
<script type="module" src="app.js"></script>
</body>
</html>
"""

# --------------------------------------------------------------------------
# Connections footer (bidirectional, derived from metadata)
# --------------------------------------------------------------------------
def link_to(slug: str) -> str:
    if slug not in TITLE:
        return f'<code>{html.escape(slug)}</code>'
    return f'<a href="{slug}.html">{html.escape(TITLE[slug])}</a>'

def build_reverse():
    uses_rev, related_rev = {}, {}
    for slug, m in PAGE_META.items():
        cl = m.get("crossLinks", {}) or {}
        for u in cl.get("uses", []) or []:
            uses_rev.setdefault(u, set()).add(slug)
        for r in cl.get("related", []) or []:
            related_rev.setdefault(r, set()).add(slug)
    return uses_rev, related_rev

USES_REV, RELATED_REV = build_reverse()

def connections_html(slug: str) -> str:
    m = PAGE_META.get(slug, {})
    cl = m.get("crossLinks", {}) or {}
    uses = [s for s in dict.fromkeys(cl.get("uses", []) or []) if s in TITLE and s != slug]
    usedby = sorted((set(cl.get("usedBy", []) or []) | USES_REV.get(slug, set())) - {slug})
    usedby = [s for s in usedby if s in TITLE]
    related = set(cl.get("related", []) or []) | RELATED_REV.get(slug, set())
    related = sorted(related - {slug} - set(uses) - set(usedby))
    related = [s for s in related if s in TITLE]
    refs = m.get("codeRefs", []) or []

    def col(label, slugs):
        if not slugs:
            items = '<li class="conn-empty">—</li>'
        else:
            items = "".join(f"<li>{link_to(s)}</li>" for s in slugs)
        return f'<div><h4>{label}</h4><ul>{items}</ul></div>'

    cols = [col("Uses", uses), col("Used by", usedby), col("Related", related)]
    if refs:
        ritems = "".join(
            f'<li><code>{html.escape(r.get("path",""))}</code>'
            + (f' — {html.escape(r.get("note",""))}' if r.get("note") else "")
            + "</li>"
            for r in refs[:10]
        )
        cols.append(f'<div><h4>Source files</h4><ul>{ritems}</ul></div>')
    return f'<footer class="connections" aria-label="Related pages">{"".join(cols)}</footer>'

def pagefoot() -> str:
    return (f'<footer class="pagefoot">Generated {html.escape(GENERATED)} by '
            f'<code>wiki/_build.py</code> from the mem0 source tree · '
            f'<a href="concepts.json">concepts.json</a> · '
            f'<a href="https://github.com/mem0ai/mem0" target="_blank" rel="noopener">mem0ai/mem0</a></footer>')

# --------------------------------------------------------------------------
# Heading extraction (for search index)
# --------------------------------------------------------------------------
TAG_RE = re.compile(r"<[^>]+>")
H_RE = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", re.I | re.S)

def headings_of(body: str) -> list[str]:
    out = []
    for raw in H_RE.findall(body):
        txt = html.unescape(TAG_RE.sub("", raw)).strip()
        txt = re.sub(r"\s+", " ", txt)
        if txt and txt != "#":
            out.append(txt.replace("#", "").strip())
    return out

# --------------------------------------------------------------------------
# Emit content + surprises pages
# --------------------------------------------------------------------------
def read_body(slug: str) -> str | None:
    f = BODIES / f"{slug}.html"
    if f.exists():
        t = f.read_text().strip()
        return t if len(t) > 40 else None
    return None

emitted = []
missing = []
all_headings = {}
for slug, title, grp, kind, desc in PAGES:
    if kind != "body":
        continue
    body = read_body(slug)
    if body is None:
        missing.append(slug)
        body = (f"<h1>{html.escape(title)}</h1>"
                f'<p class="lead">{html.escape(summary_of(slug))}</p>'
                f'<aside class="callout gotcha"><strong>Pending</strong> This page body was not generated. '
                f'Re-run the build after authoring <code>wiki/_src/bodies/{slug}.html</code>.</aside>')
    all_headings[slug] = headings_of(body)
    full = shell(slug, title, summary_of(slug), body + connections_html(slug) + pagefoot())
    (ROOT / f"{slug}.html").write_text(full)
    emitted.append(slug)

# --------------------------------------------------------------------------
# Glossary (generated from concepts across all pages)
# --------------------------------------------------------------------------
KIND_LABEL = {
    "class": "Classes", "module": "Modules", "algorithm": "Algorithms",
    "pattern": "Patterns", "provider": "Providers", "service": "Services",
    "concept": "Concepts", "interface": "Interfaces",
}
KIND_ORDER = ["concept", "algorithm", "class", "module", "pattern", "interface", "service", "provider"]

def build_concepts():
    concepts = {}  # id -> {label, kind, pages:set}
    for slug, m in PAGE_META.items():
        for c in m.get("concepts", []) or []:
            cid = c.get("id") or re.sub(r"[^a-z0-9]+", "-", (c.get("label", "")).lower()).strip("-")
            if not cid:
                continue
            rec = concepts.setdefault(cid, {"label": c.get("label", cid), "kind": c.get("kind", "concept"), "pages": set()})
            rec["pages"].add(slug)
            if len(c.get("label", "")) > len(rec["label"]):
                rec["label"] = c["label"]
    return concepts

CONCEPTS = build_concepts()

def glossary_body() -> str:
    parts = ['<h1>Glossary &amp; Concept Index</h1>',
             '<p class="lead">Every named concept, class, module, algorithm, pattern and provider surfaced across the wiki, '
             'grouped by kind and linked to the page where it lives. Use this as a jump table or feed it to an agent via '
             '<a href="concepts.json">concepts.json</a>.</p>']
    by_kind = {}
    for cid, rec in CONCEPTS.items():
        by_kind.setdefault(rec["kind"], []).append((cid, rec))
    ordered_kinds = [k for k in KIND_ORDER if k in by_kind] + [k for k in by_kind if k not in KIND_ORDER]
    for k in ordered_kinds:
        items = sorted(by_kind[k], key=lambda x: x[1]["label"].lower())
        cards = []
        for cid, rec in items:
            pages = sorted(rec["pages"])
            plinks = " · ".join(link_to(s) for s in pages)
            cards.append(
                f'<div class="gloss-item"><div class="g-kind">{html.escape(rec["kind"])}</div>'
                f'<div class="g-term">{html.escape(rec["label"])}</div>'
                f'<div class="g-pages">{plinks}</div></div>'
            )
        parts.append(f'<section class="glossary-group" id="kind-{k}"><h2>{KIND_LABEL.get(k, k.title())} '
                     f'<span class="kind-pill">{len(items)}</span></h2>'
                     f'<div class="glossary-grid">{"".join(cards)}</div></section>')
    return "\n".join(parts)

(ROOT / "glossary.html").write_text(
    shell("glossary", "Glossary & Concept Index",
          "All concepts indexed and grouped, linked to their pages.",
          glossary_body() + pagefoot())
)
all_headings["glossary"] = headings_of(glossary_body())

# --------------------------------------------------------------------------
# Home / index
# --------------------------------------------------------------------------
def index_mermaid() -> str:
    """Clickable knowledge graph from the 'uses' edges, grouped into subgraphs."""
    nodes_by_group = {}
    for slug, title, grp, kind, _desc in PAGES:
        if slug in ("index", "glossary"):
            continue
        nodes_by_group.setdefault(grp, []).append((slug, title))
    lines = ["flowchart LR"]
    nid = lambda s: s.replace("-", "_")
    for g in GROUP_ORDER:
        if g not in nodes_by_group:
            continue
        lines.append(f'  subgraph {g.replace(" ", "_")}["{g}"]')
        for slug, title in nodes_by_group[g]:
            lines.append(f'    {nid(slug)}["{title}"]')
        lines.append("  end")
    seen = set()
    for slug, m in PAGE_META.items():
        if slug in ("index", "glossary"):
            continue
        for u in (m.get("crossLinks", {}) or {}).get("uses", []) or []:
            if u in ("index", "glossary") or u == slug or u not in TITLE:
                continue
            key = (slug, u)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  {nid(slug)} --> {nid(u)}")
    for slug, title, grp, kind, _desc in PAGES:
        if slug in ("index", "glossary"):
            continue
        lines.append(f'  click {nid(slug)} "{slug}.html" "{title}"')
    return "<pre class=\"mermaid\">\n" + "\n".join(lines) + "\n</pre>"

def index_cards() -> str:
    out = []
    for g in GROUP_ORDER:
        cards = []
        for slug, title, grp, kind, desc in PAGES:
            if grp != g or slug in ("index",):
                continue
            d = summary_of(slug) if slug in PAGE_META else desc
            cards.append(
                f'<a class="card" href="{slug}.html"><div class="card-eyebrow">{g}</div>'
                f'<div class="card-title">{html.escape(title)}</div>'
                f'<div class="card-desc">{html.escape(d[:140])}</div></a>'
            )
        if cards:
            out.append(f'<h2 id="area-{g.lower()}">{g}</h2><div class="cards">{"".join(cards)}</div>')
    return "\n".join(out)

def index_body() -> str:
    metrics = [
        ("91.6", "LoCoMo"),
        ("94.8", "LongMemEval"),
        ("64.1", "BEAM (1M)"),
        (str(COUNTS["llms"] or "24") + "+", "LLM providers"),
        (str(COUNTS["vector-stores"] or "26") + "+", "Vector stores"),
        (str(COUNTS["embeddings"] or "15") + "+", "Embedders"),
    ]
    mrow = "".join(f'<div class="metric"><div class="m-val">{v}</div><div class="m-label">{l}</div></div>' for v, l in metrics)
    return f"""
<section class="hero" id="overview">
  <h1>mem0 &mdash; the memory layer for AI agents</h1>
  <p class="tagline">An intelligent, persistent memory layer for AI assistants and agents. This wiki is a condensed,
  cross-linked knowledge graph of the entire <a href="https://github.com/mem0ai/mem0" target="_blank" rel="noopener">mem0ai/mem0</a>
  codebase &mdash; architecture, the engine, the new retrieval algorithm, every provider layer, the SDKs, servers and ecosystem.</p>
  <div class="badges">
    <span class="badge hot">Apr-2026 algorithm</span>
    <span class="badge">Apache-2.0</span>
    <span class="badge">Python + TypeScript</span>
    <span class="badge">Self-hosted &amp; hosted</span>
    <span class="badge">Polyglot monorepo</span>
  </div>
</section>

<section id="why">
  <p>Start with <a href="architecture.html">Architecture</a> for the big picture, follow the <a href="data-flow.html">Data Flow</a>
  to see <code>add()</code> and <code>search()</code> end to end, then dive into the <a href="memory-algorithm.html">Memory Algorithm</a>
  &mdash; the single-pass, ADD-only extraction with multi-signal retrieval that drives the headline benchmark numbers below.
  Curious what is clever or surprising? Jump straight to <a href="surprises.html">Surprises &amp; Gotchas</a>.</p>
  <div class="metrics">{mrow}</div>
  <p style="color:var(--text-dim);font-size:13px;margin-top:-6px">Benchmark scores are single-pass (one retrieval call, no agentic loops) &mdash; see <a href="evaluation.html">Evaluation</a>. Provider counts computed from the source tree at build time.</p>
</section>

<section id="graph">
  <h2>Knowledge graph</h2>
  <p>Each node is a page; arrows are &ldquo;uses&rdquo; dependencies. Click any node to open that page.</p>
  {index_mermaid()}
</section>

<section id="areas">
  <h2>Explore by area</h2>
  {index_cards()}
</section>

<section id="agents">
  <h2>For AI agents</h2>
  <p>This wiki is built for machine retrieval as much as human reading:</p>
  <ul>
    <li><a href="concepts.json">concepts.json</a> &mdash; the full node/edge knowledge graph (pages, concepts, and their relationships).</li>
    <li><a href="search-index.json">search-index.json</a> &mdash; per-page titles, summaries, headings and keywords powering the in-page search.</li>
    <li>Every page carries a JSON-LD <code>TechArticle</code> block, stable section <code>id</code>s, and a machine-readable <em>Connections</em> footer (Uses / Used by / Related / Source files).</li>
    <li>The <a href="glossary.html">Glossary</a> is a flat jump table of every named concept across the codebase.</li>
  </ul>
</section>
"""

(ROOT / "index.html").write_text(shell("index", "mem0 wiki", "Condensed, cross-linked knowledge graph of the mem0 codebase.", index_body() + pagefoot(), is_home=True))
all_headings["index"] = headings_of(index_body())

# --------------------------------------------------------------------------
# concepts.json  (knowledge graph for agents)
# --------------------------------------------------------------------------
graph_pages = [
    {"slug": s, "title": TITLE[s], "group": GROUP[s], "summary": summary_of(s)}
    for s, _t, _g, _k, _d in PAGES if s not in ("index",)
]
graph_concepts = [
    {"id": cid, "label": rec["label"], "kind": rec["kind"], "pages": sorted(rec["pages"])}
    for cid, rec in sorted(CONCEPTS.items())
]
edges = []
for slug, m in PAGE_META.items():
    cl = m.get("crossLinks", {}) or {}
    for u in dict.fromkeys(cl.get("uses", []) or []):
        if u in TITLE and u != slug:
            edges.append({"from": slug, "to": u, "type": "uses"})
    for r in dict.fromkeys(cl.get("related", []) or []):
        if r in TITLE and r != slug:
            edges.append({"from": slug, "to": r, "type": "related"})
    for c in m.get("concepts", []) or []:
        cid = c.get("id")
        if cid:
            edges.append({"from": slug, "to": cid, "type": "contains"})

(ROOT / "concepts.json").write_text(json.dumps({
    "name": "mem0 wiki knowledge graph",
    "generated": GENERATED,
    "source": "https://github.com/mem0ai/mem0",
    "pages": graph_pages,
    "concepts": graph_concepts,
    "edges": edges,
}, indent=2, ensure_ascii=False))

# --------------------------------------------------------------------------
# search-index.json
# --------------------------------------------------------------------------
search_pages = []
for slug, title, grp, kind, desc in PAGES:
    m = PAGE_META.get(slug, {})
    terms = list(dict.fromkeys(
        (m.get("searchTerms", []) or []) + [c.get("label", "") for c in (m.get("concepts", []) or [])]
    ))
    search_pages.append({
        "slug": slug,
        "title": title if slug != "index" else "Home — mem0 wiki",
        "group": grp or "Overview",
        "summary": summary_of(slug) if slug in PAGE_META else desc,
        "headings": all_headings.get(slug, [])[:40],
        "terms": [t for t in terms if t][:40],
    })
(ROOT / "search-index.json").write_text(json.dumps({"pages": search_pages}, indent=2, ensure_ascii=False))

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
print(f"Emitted {len(emitted)} content pages + index + glossary")
print(f"Concepts: {len(graph_concepts)} | Edges: {len(edges)} | Provider counts: {COUNTS}")
if missing:
    print("WARNING missing bodies (stubbed):", ", ".join(missing))
