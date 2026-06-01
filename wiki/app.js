/* mem0 wiki — client behavior (ES module)
   - theme toggle (persisted, system-aware)
   - Mermaid render with theme-aware re-render
   - client-side search over search-index.json
   - mobile sidebar, keyboard shortcuts, heading anchor links
*/

const root = document.documentElement;
const THEME_KEY = "mem0-wiki-theme";

/* ----------------------------- Theme -----------------------------------
   The initial data-theme attribute is set by an inline <head> script (no
   FOUC). Here we only handle toggling + button label + mermaid re-render.
   renderMermaid() is intentionally never called before module init. */
function currentTheme() {
  return root.getAttribute("data-theme") === "light" ? "light" : "dark";
}
function updateThemeButton(t) {
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = t === "dark" ? "◐" : "◑";
}
function setTheme(t) {
  root.setAttribute("data-theme", t);
  localStorage.setItem(THEME_KEY, t);
  updateThemeButton(t);
  renderMermaid(t);
}

/* ----------------------------- Mermaid --------------------------------- */
let mermaidApi = null;
let mermaidLoading = null;
async function ensureMermaid() {
  if (mermaidApi) return mermaidApi;
  if (!document.querySelector(".mermaid")) return null;
  if (!mermaidLoading) {
    mermaidLoading = import("https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs")
      .then((m) => { mermaidApi = m.default; return mermaidApi; })
      .catch(() => null);
  }
  return mermaidLoading;
}
async function renderMermaid(theme) {
  const blocks = Array.from(document.querySelectorAll(".mermaid"));
  if (!blocks.length) return;
  const mermaid = await ensureMermaid();
  if (!mermaid) return;
  // restore original source so we can re-render on theme change
  for (const el of blocks) {
    if (el.dataset.src) { el.innerHTML = el.dataset.src; }
    else { el.dataset.src = el.textContent; }
    el.removeAttribute("data-processed");
  }
  mermaid.initialize({
    startOnLoad: false,
    theme: theme === "light" ? "neutral" : "dark",
    securityLevel: "loose",
    fontFamily: "var(--sans)",
  });
  try { await mermaid.run({ nodes: blocks }); } catch (e) { /* leave source visible */ }
}

/* ----------------------------- Anchor links ---------------------------- */
function addAnchors() {
  document.querySelectorAll(".content h2[id], .content h3[id]").forEach((h) => {
    const a = document.createElement("a");
    a.href = "#" + h.id;
    a.className = "anchor-link";
    a.textContent = "#";
    a.setAttribute("aria-label", "Link to this section");
    h.appendChild(a);
  });
}

/* ----------------------------- Sidebar (mobile) ------------------------ */
function initSidebar() {
  const toggle = document.getElementById("menu-toggle");
  const sidebar = document.getElementById("sidebar");
  if (!toggle || !sidebar) return;
  toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
  document.addEventListener("click", (e) => {
    if (window.innerWidth > 900) return;
    if (!sidebar.contains(e.target) && e.target !== toggle) sidebar.classList.remove("open");
  });
}

/* ----------------------------- Search ---------------------------------- */
const SEARCH = { idx: null, items: [], active: -1 };

async function loadSearch() {
  try {
    const res = await fetch("search-index.json");
    const data = await res.json();
    SEARCH.idx = data.pages || [];
  } catch (e) { SEARCH.idx = []; }
}

function scorePage(p, tokens) {
  const title = (p.title || "").toLowerCase();
  const slug = (p.slug || "").toLowerCase();
  const summary = (p.summary || "").toLowerCase();
  const headings = (p.headings || []).join(" ␟ ").toLowerCase();
  const terms = (p.terms || []).join(" ␟ ").toLowerCase();
  let score = 0;
  for (const t of tokens) {
    if (!t) continue;
    if (title.includes(t)) score += title === t ? 40 : 12;
    if (slug.includes(t)) score += 8;
    if (terms.includes(t)) score += 6;
    if (headings.includes(t)) score += 5;
    if (summary.includes(t)) score += 2;
  }
  return score;
}

function highlight(text, tokens) {
  let out = escapeHtml(text);
  for (const t of tokens) {
    if (t.length < 2) continue;
    out = out.replace(new RegExp("(" + escapeReg(t) + ")", "ig"), "<mark>$1</mark>");
  }
  return out;
}
function escapeHtml(s) { return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function escapeReg(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

function runSearch(q) {
  const box = document.getElementById("search-results");
  if (!box) return;
  const query = q.trim().toLowerCase();
  if (!query) { box.classList.remove("open"); box.innerHTML = ""; SEARCH.items = []; return; }
  const tokens = query.split(/\s+/);
  const ranked = (SEARCH.idx || [])
    .map((p) => ({ p, s: scorePage(p, tokens) }))
    .filter((r) => r.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, 8);
  SEARCH.items = ranked.map((r) => r.p);
  SEARCH.active = -1;
  if (!ranked.length) {
    box.innerHTML = '<div class="sr-empty">No matches for &ldquo;' + escapeHtml(q) + '&rdquo;</div>';
    box.classList.add("open");
    return;
  }
  box.innerHTML = ranked.map((r, i) =>
    '<a class="sr-item" data-i="' + i + '" href="' + r.p.slug + '.html">' +
      '<div class="sr-group">' + escapeHtml(r.p.group || "") + "</div>" +
      '<div class="sr-title">' + highlight(r.p.title, tokens) + "</div>" +
      '<div class="sr-snip">' + highlight(r.p.summary || "", tokens) + "</div>" +
    "</a>"
  ).join("");
  box.classList.add("open");
}

function initSearch() {
  const input = document.getElementById("search-input");
  const box = document.getElementById("search-results");
  if (!input || !box) return;
  let t;
  input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => runSearch(input.value), 90); });
  input.addEventListener("focus", () => { if (input.value) runSearch(input.value); });
  input.addEventListener("keydown", (e) => {
    const items = Array.from(box.querySelectorAll(".sr-item"));
    if (e.key === "ArrowDown") { e.preventDefault(); SEARCH.active = Math.min(SEARCH.active + 1, items.length - 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); SEARCH.active = Math.max(SEARCH.active - 1, 0); }
    else if (e.key === "Enter") { if (SEARCH.active >= 0 && items[SEARCH.active]) { window.location.href = items[SEARCH.active].getAttribute("href"); } else if (items[0]) { window.location.href = items[0].getAttribute("href"); } return; }
    else if (e.key === "Escape") { box.classList.remove("open"); input.blur(); return; }
    else return;
    items.forEach((it, i) => it.classList.toggle("active", i === SEARCH.active));
    if (items[SEARCH.active]) items[SEARCH.active].scrollIntoView({ block: "nearest" });
  });
  document.addEventListener("click", (e) => { if (!box.contains(e.target) && e.target !== input) box.classList.remove("open"); });
  // global "/" focuses search
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== input && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      e.preventDefault(); input.focus();
    }
  });
}

/* ----------------------------- Boot ------------------------------------ */
function initThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.addEventListener("click", () => setTheme(currentTheme() === "dark" ? "light" : "dark"));
}

document.addEventListener("DOMContentLoaded", async () => {
  updateThemeButton(currentTheme());
  initThemeToggle();
  initSidebar();
  addAnchors();
  renderMermaid(currentTheme());
  await loadSearch();
  initSearch();
});
