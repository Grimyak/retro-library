(() => {
  "use strict";
  const $ = s => document.querySelector(s);
  const PAGE = 120;

  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  };

  const state = {
    q:"", sys:new Set(), genre:"", sort:"title", shown:PAGE,
    view: store.get("view", "cover") === "box3d" ? "box3d" : "cover",
  };
  let DATA, SYS = {}, view = [];
  // Artwork keeps its filename across re-scrapes — only the bytes change — so a
  // cached copy would otherwise survive a rebuild. Stamping the build date on
  // every request retires the old one the moment the catalogue is regenerated.
  let V = "";

  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const gb  = b => b >= 2**30 ? (b/2**30).toFixed(1)+" GB" : Math.max(1,Math.round(b/2**20))+" MB";
  const num = n => n.toLocaleString("en-US");
  // 0-100 rating as a 20-cell block meter, e.g. ██████████████████░░
  const meter = r => { const f = Math.round(r / 5); return "█".repeat(f) + "░".repeat(20 - f); };

  // Revalidate rather than trust a cached copy: this file carries the build date
  // that retires stale artwork, so serving it from cache would defeat the point.
  // GitHub Pages sends an ETag, so an unchanged catalogue costs a 304.
  fetch("data/games.json", { cache: "no-cache" })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(r.status)))
    .then(d => { DATA = d; init(); })
    .catch(e => { $("#grid").innerHTML =
      `<p class="empty">Couldn't load the catalogue (${esc(e.message)}).</p>`; });

  function init() {
    DATA.systems.forEach(s => { SYS[s.id] = s; });
    DATA.games.forEach(g => {
      g._s = (g.t+" "+(g.d||"")+" "+(g.p||"")+" "+(g.se||"")+" "+(g.g||"")).toLowerCase();
    });

    const st = DATA.stats;
    $("#stats").innerHTML = [
      ["Games", num(st.games)], ["Systems", DATA.systems.length],
      ["On disk", gb(st.bytes)], ["Rated", num(st.rated)],
    ].map(([k,v]) => `<div><dd>${v}</dd><dt>${k}</dt></div>`).join("");

    $("#systems").innerHTML = DATA.systems.map(s =>
      `<button class="pill" data-sys="${s.id}" aria-pressed="false">${esc(s.short)} <span class="n">${s.n}</span></button>`
    ).join("");
    $("#genre").insertAdjacentHTML("beforeend",
      DATA.genres.map(g => `<option value="${esc(g)}">${esc(g)}</option>`).join(""));
    V = "?v=" + encodeURIComponent(DATA.generated);
    $("#generated").textContent = `Catalogue generated ${DATA.generated}.`;

    applyView();
    bind();
    readHash();
    apply();
  }

  function applyView() {
    $("#grid").classList.toggle("box3d", state.view === "box3d");
    document.querySelectorAll("#view button").forEach(b =>
      b.setAttribute("aria-pressed", b.dataset.view === state.view));
  }

  function bind() {
    let t;
    $("#q").addEventListener("input", e => {
      $("#qclear").hidden = !e.target.value;
      clearTimeout(t);
      t = setTimeout(() => { state.q = e.target.value.trim().toLowerCase(); state.shown = PAGE; apply(); }, 130);
    });
    $("#qclear").addEventListener("click", () => {
      $("#q").value = ""; $("#qclear").hidden = true;
      state.q = ""; state.shown = PAGE; apply(); $("#q").focus();
    });
    $("#sort").addEventListener("change", e => { state.sort = e.target.value; state.shown = PAGE; apply(); });
    $("#genre").addEventListener("change", e => { state.genre = e.target.value; state.shown = PAGE; apply(); });

    $("#view").addEventListener("click", e => {
      const b = e.target.closest("button[data-view]"); if (!b) return;
      state.view = b.dataset.view; store.set("view", state.view);
      applyView(); render();
    });

    $("#systems").addEventListener("click", e => {
      const b = e.target.closest(".pill"); if (!b) return;
      const id = b.dataset.sys;
      state.sys.has(id) ? state.sys.delete(id) : state.sys.add(id);
      b.setAttribute("aria-pressed", state.sys.has(id));
      state.shown = PAGE; apply();
    });

    $("#more").addEventListener("click", () => { state.shown += PAGE * 2; render(); });
    $("#grid").addEventListener("click", e => {
      const c = e.target.closest(".card"); if (c) open(+c.dataset.i);
    });
    $("#modal").addEventListener("click", e => { if (e.target.dataset.close !== undefined) close(); });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && !$("#modal").hidden) close();
      else if (e.key === "/" && document.activeElement !== $("#q")) { e.preventDefault(); $("#q").focus(); }
    });
    window.addEventListener("hashchange", () => { if (!location.hash) close(); });
  }

  function readHash() {
    const m = decodeURIComponent(location.hash.slice(1));
    if (m) requestAnimationFrame(() => {
      const i = DATA.games.findIndex(g => g.s + "/" + g.f === m);
      if (i > -1) open(i, true);
    });
  }

  function apply() {
    const { q, sys, genre } = state;
    view = DATA.games.map((g, i) => (g._i = i, g)).filter(g =>
      (!sys.size || sys.has(g.s)) &&
      (!genre || g.g === genre) &&
      (!q || g._s.includes(q))
    );
    view.sort({
      title:   (a,b) => a.k.localeCompare(b.k),
      rating:  (a,b) => (b.r||-1) - (a.r||-1) || a.k.localeCompare(b.k),
      year:    (a,b) => (b.y||0) - (a.y||0) || a.k.localeCompare(b.k),
      yearAsc: (a,b) => (a.y||9999) - (b.y||9999) || a.k.localeCompare(b.k),
      size:    (a,b) => (b.z||0) - (a.z||0),
    }[state.sort]);
    render();
  }

  function render() {
    const n = view.length, slice = view.slice(0, state.shown);
    $("#count").textContent = n
      ? `${num(n)} game${n===1?"":"s"}${n>slice.length ? ` — showing ${num(slice.length)}` : ""}`
      : "";
    $("#empty").hidden = n > 0;
    $("#more").hidden = n <= slice.length;
    $("#grid").innerHTML = slice.map(card).join("");
  }

  function card(g) {
    // fall back to the other artwork style when the preferred one is missing
    const src = state.view === "box3d" ? (g.b || g.c) : (g.c || g.b);
    const art = src
      ? `<img src="img/${src}${V}" alt="" loading="lazy" decoding="async">`
      : `<span class="noart">No artwork</span>`;
    return `<button class="card" data-i="${g._i}">
      <span class="art">${g.r ? `<span class="badge">${g.r}</span>` : ""}${art}</span>
      <span class="meta">
        <span class="name">${esc(g.t)}</span>
        <span class="sub"><span class="sys">${esc(SYS[g.s].short)}</span>${g.y ? " · " + g.y : ""}</span>
      </span></button>`;
  }

  let lastFocus = null;
  function open(i, fromHash) {
    const g = DATA.games[i]; if (!g) return;
    lastFocus = document.activeElement;
    const facts = [
      ["Developer", g.d], ["Publisher", g.p], ["Released", g.y], ["Genre", g.g],
      ["Players", g.pl], ["Region", g.rg], ["Series", g.se],
      ["Discs", g.dc], ["Size", g.z ? gb(g.z) : null],
    ].filter(([, v]) => v);
    const caps = [["shot","Screenshot","i"], ["title","Title screen","n"]]
      .filter(([,,k]) => g[k])
      .map(([,label,k]) =>
        `<figure><img src="img/${g[k]}${V}" alt="${esc(label)} from ${esc(g.t)}" loading="lazy">
         <figcaption>${label}</figcaption></figure>`).join("");

    $("#sheet-body").innerHTML = `
      ${g.l ? `<img class="sheet-logo" src="img/${g.l}${V}" alt="${esc(g.t)} logo">` : ""}
      <div class="sheet-head">
        ${(g.c || g.b || g.m) ? `<div class="sheet-media">
          ${(g.c || g.b) ? `<div class="sheet-art"><img src="img/${g.c || g.b}${V}" alt="Box art for ${esc(g.t)}"></div>` : ""}
          ${g.m ? `<img class="sheet-disc" src="img/${g.m}${V}" alt="Cartridge or disc for ${esc(g.t)}" loading="lazy">` : ""}
        </div>` : ""}
        <div class="sheet-info">
          <h2 id="m-title">${esc(g.t)}</h2>
          <p class="sheet-sys">${esc(SYS[g.s].name)}</p>
          <p class="score">${g.r
            ? `<span class="meter">${meter(g.r)}</span> ${g.r}/100`
            : `<span class="none">no rating</span>`}</p>
          <dl class="facts">${facts.map(([k,v]) =>
            `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
        </div>
      </div>
      ${g.x ? `<p class="desc">${esc(g.x)}</p>` : ""}
      ${caps ? `<div class="caps">${caps}</div>` : ""}
      <p class="filename">${esc(g.f)}</p>`;

    $("#modal").hidden = false;
    document.body.style.overflow = "hidden";
    if (!fromHash) history.replaceState(null, "", "#" + encodeURIComponent(g.s + "/" + g.f));
    $(".close").focus();
  }

  function close() {
    $("#modal").hidden = true;
    document.body.style.overflow = "";
    history.replaceState(null, "", location.pathname + location.search);
    if (lastFocus) lastFocus.focus();
  }
})();
