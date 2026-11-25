// Light/dark switch. Light is the default; a dark choice is kept in localStorage (no cookies)
// and applied before paint by the inline script in <head>. Without JS the button stays hidden.
(function () {
  var btn = document.querySelector(".theme-toggle");
  if (!btn) return;
  var root = document.documentElement;
  function show(dark) {
    if (dark) root.setAttribute("data-theme", "dark"); else root.removeAttribute("data-theme");
    btn.setAttribute("aria-pressed", String(dark));
  }
  show(root.getAttribute("data-theme") === "dark");
  btn.hidden = false;
  btn.addEventListener("click", function () {
    var dark = root.getAttribute("data-theme") !== "dark";
    show(dark);
    try { if (dark) localStorage.setItem("theme", "dark"); else localStorage.removeItem("theme"); } catch (e) {}
  });
})();

// Filters: a track (Technical / Political / Economic) and a mentioned name.
// Both narrow the cards; together they combine. Without JS every card shows and the controls stay inert.
(function () {
  var nav = document.querySelector(".filters");
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card"));
  var empty = document.querySelector(".empty");
  var stateEl = document.querySelector(".filter-state");
  var trackButtons = nav ? nav.querySelectorAll("button[data-track]") : [];
  var termButtons = document.querySelectorAll(".term");
  var state = { track: "", term: "" };

  function apply() {
    var shown = 0;
    cards.forEach(function (c) {
      var terms = (c.dataset.terms || "").split("|");
      var ok = (!state.track || c.dataset.track === state.track) && (!state.term || terms.indexOf(state.term) !== -1);
      c.hidden = !ok;
      if (ok) shown++;
    });
    trackButtons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.track === state.track)); });
    termButtons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.term === state.term)); });
    if (empty) empty.hidden = shown !== 0;
    if (stateEl) stateEl.textContent = state.track || state.term ? shown + " of " + cards.length + " stories" : "";
  }

  if (nav) nav.hidden = false;
  trackButtons.forEach(function (b) {
    b.addEventListener("click", function () { state.track = b.dataset.track; apply(); });
  });
  termButtons.forEach(function (b) {
    b.disabled = false;
    b.addEventListener("click", function () {
      state.term = state.term === b.dataset.term ? "" : b.dataset.term;
      apply();
    });
  });
  var reset = document.querySelector(".reset");
  if (reset) reset.addEventListener("click", function () { state = { track: "", term: "" }; apply(); });
})();

// Rising: filter the category groups.
(function () {
  var nav = document.querySelector(".rising-filters");
  if (!nav) return;
  nav.hidden = false;
  var buttons = nav.querySelectorAll("button[data-category]");
  var groups = document.querySelectorAll(".rgroup");
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      var cat = b.dataset.category;
      buttons.forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      groups.forEach(function (g) { g.hidden = !!cat && g.dataset.category !== cat; });
      document.querySelector(".rising-groups").classList.toggle("single", !!cat);
    });
  });
})();

// Expanded sources, tabbed: with JS, every open card shares one window below the row of the card
// opened last, one tab per card. Without JS each card's panel opens under its own row (CSS only).
(function () {
  var grid = document.querySelector(".stories");
  if (!grid) return;
  var tray = document.createElement("section");
  tray.className = "tray";
  tray.hidden = true;
  tray.setAttribute("aria-label", "Expanded sources");
  var tabs = document.createElement("div");
  tabs.className = "tray-tabs";
  tabs.setAttribute("role", "tablist");
  tray.appendChild(tabs);
  grid.classList.add("tabbed");
  var open = [];       // cards in the order they were opened
  var active = null;   // the card whose sources show

  function detailsOf(card) { return card.querySelector(".card-foot details"); }
  function panelOf(card) { return document.getElementById(card.id + "-more"); }

  function render() {
    tabs.textContent = "";
    open.forEach(function (card) {
      var panel = panelOf(card);
      var on = card === active;
      var tab = document.createElement("div");
      tab.className = "tray-tab" + (on ? " is-active" : "");
      var pick = document.createElement("button");
      pick.type = "button";
      pick.className = "tray-pick";
      pick.setAttribute("role", "tab");
      pick.setAttribute("aria-selected", String(on));
      pick.setAttribute("aria-controls", panel.id);
      pick.id = card.id + "-tab";
      pick.tabIndex = on ? 0 : -1;
      var rank = card.querySelector(".rank");
      var head = card.querySelector("h2");
      pick.innerHTML = "<span class=\"tray-rank\"></span><span class=\"tray-title\"></span>";
      pick.firstChild.textContent = rank ? rank.textContent : "";
      pick.lastChild.textContent = head ? head.textContent : "";
      pick.title = head ? head.textContent : "";
      pick.addEventListener("click", function () { active = card; render(); });
      var close = document.createElement("button");
      close.type = "button";
      close.className = "tray-close";
      close.setAttribute("aria-label", "Close " + (head ? head.textContent : "these sources"));
      close.textContent = "×";
      close.addEventListener("click", function () { detailsOf(card).open = false; });
      tab.appendChild(pick);
      tab.appendChild(close);
      tabs.appendChild(tab);
      panel.classList.toggle("is-active", on);
      panel.setAttribute("role", "tabpanel");
      panel.setAttribute("aria-labelledby", pick.id);
    });
    tray.hidden = open.length === 0;
  }

  function add(card) {
    if (open.indexOf(card) === -1) open.push(card);
    active = card;
    tray.appendChild(panelOf(card));
    card.after(tray);  // the grid packs densely: the tray takes the next row, the row stays whole
    render();
  }

  function remove(card) {
    var i = open.indexOf(card);
    if (i === -1) return;
    open.splice(i, 1);
    var panel = panelOf(card);
    panel.classList.remove("is-active");
    panel.setAttribute("role", "region");
    panel.removeAttribute("aria-labelledby");
    card.after(panel);  // back home; CSS keeps it hidden while the grid is tabbed
    if (active === card) active = open[open.length - 1] || null;
    if (open.length && tray.previousElementSibling !== open[open.length - 1]) open[open.length - 1].after(tray);
    render();
  }

  // Arrow keys move between tabs.
  tabs.addEventListener("keydown", function (ev) {
    if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
    var i = open.indexOf(active) + (ev.key === "ArrowRight" ? 1 : -1);
    if (i < 0 || i >= open.length) return;
    active = open[i];
    render();
    document.getElementById(active.id + "-tab").focus();
  });

  Array.prototype.forEach.call(grid.querySelectorAll(".card"), function (card) {
    var d = detailsOf(card);
    if (!d || !panelOf(card)) return;
    d.addEventListener("toggle", function () { if (d.open) add(card); else remove(card); });
    if (d.open) add(card);
    // A card hidden by a filter closes its tab.
    new MutationObserver(function () { if (card.hidden && d.open) d.open = false; }).observe(card, { attributes: true, attributeFilter: ["hidden"] });
  });
})();

// The greeting: on the first page of a visit the sentiment figure counts up from zero in 450 ms while
// its line steps in (CSS, under html.greet, set before paint). Later pages show it still.
(function () {
  var root = document.documentElement;
  var num = document.querySelector(".sent-num");
  if (!root.classList.contains("greet")) return;
  try { sessionStorage.setItem("greeted", "1"); } catch (e) {}
  // A tab opened in the background pauses animation frames: show the figure still instead.
  if (!num || !window.requestAnimationFrame || document.hidden) return;
  var target = parseFloat(num.getAttribute("data-value"));
  if (isNaN(target)) return;
  var shown = num.textContent;
  var start = null;
  function fmt(v) { return (v < 0 ? "\u2212" : "+") + Math.abs(v).toFixed(2); }
  function frame(t) {
    if (start === null) start = t;
    var p = Math.min(1, (t - start) / 450);
    num.textContent = p < 1 ? fmt(target * (1 - Math.pow(1 - p, 3))) : shown;
    if (p < 1) requestAnimationFrame(frame);
  }
  num.textContent = fmt(0);
  requestAnimationFrame(frame);
})();

// The narrative seal, on a narrative's page. The lattice's threads twist into a cord; the cord pays its thread out to
// a pen that writes the day count, then "day", then "narrative", in the wordmark's Baskerville: stroke by stroke in a
// calligrapher's order, slowing into each curve and lifting between strokes, the newest ink a little darker. After each
// word the threads wind back into the cord; after the last (the Q of the masthead), the two halves of the lattice spin
// against each other, slow and lock, and then the lattice keeps turning slowly (style.css). In the lattice and the
// cord the threads wear the seal's stance tint (the same radial gradient as the SVG); as letters they are ink. The letters
// are the font itself: each word is set on a hidden canvas, its distance field gives the outline and inlines (the way
// engraved type is cut), and a pen path per letter (DUCTUS, fitted to the letter and pulled onto the middle of each
// stroke) decides when each part of them is written. It plays once when the page opens and again on hover or click.
// Without JS, or when the reader asks for reduced motion, the seal rests.
(function () {
  var seal = document.querySelector(".seal.big[data-k]");
  if (!seal || !window.requestAnimationFrame) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var canvas = document.createElement("canvas");
  if (!canvas.getContext) return;
  var K = +seal.getAttribute("data-k"), M = +seal.getAttribute("data-m"), DAYS = seal.getAttribute("data-days");
  var R0 = 36.5, AMP = 9.5, CORD = 37, NT = 72, P = 44, G = 200;  // R0, AMP must match build.seal; threads; points; field grid
  var STOPS = JSON.parse(seal.getAttribute("data-stops") || "[]");
  var TINT = { "-2": "--crit", "-1": "--crit-soft", "0": "--neut", "1": "--pos-soft", "2": "--pos" }, REST = 0.9;
  var lattices = seal.querySelectorAll(".seal-lat");

  // Pen paths, in writing order. Digits and Q: x across the figure, y up its height (0 to 1); a stroke that starts with
  // "o" is drawn in the box of an O instead (the Q's bowl), "ot" too but kept close to its path (the Q's thin tail). Letters: x across the letter, y up in
  // x-heights from the baseline; 9 is the top of the letter (9.1 a tenth of an x-height below it), -9 its foot.
  var DUCTUS = {
    "0": [[[.5, 1], [.17, .86], [.08, .5], [.17, .14], [.5, 0], [.83, .14], [.92, .5], [.83, .86], [.5, 1], [.32, .95]]],
    "1": [[[.22, .8], [.55, 1], [.55, 0]], [[.16, .02], [.9, .02]]],
    "2": [[[.13, .74], [.3, .96], [.6, .99], [.84, .8], [.8, .58], [.52, .33], [.1, .02], [.95, .03]]],
    "3": [[[.15, .84], [.45, .99], [.78, .88], [.74, .64], [.42, .53], [.8, .41], [.86, .18], [.55, .01], [.12, .11]]],
    "4": [[[.68, .98], [.05, .3], [.97, .3]], [[.69, .97], [.69, 0]]],
    "5": [[[.24, .98], [.19, .56], [.5, .62], [.83, .46], [.86, .2], [.55, .01], [.12, .1]], [[.24, .98], [.88, .98]]],
    "6": [[[.8, .96], [.42, .8], [.13, .45], [.16, .14], [.5, 0], [.85, .18], [.85, .42], [.5, .58], [.16, .42]]],
    "7": [[[.05, .97], [.95, .97], [.46, .4], [.36, 0]]],
    "8": [[[.55, .53], [.21, .7], [.23, .92], [.5, .99], [.77, .9], [.74, .7], [.5, .5], [.16, .32], [.18, .1], [.5, 0], [.82, .1], [.82, .32], [.55, .5]]],
    "9": [[[.84, .6], [.5, .45], [.16, .6], [.16, .85], [.5, .99], [.84, .85], [.84, .55], [.6, .2], [.2, .02]]],
    Q: [["o", [.5, 1], [.16, .86], [.07, .5], [.16, .14], [.5, 0], [.84, .14], [.93, .5], [.84, .86], [.5, 1], [.32, .96]],
        ["ot", [.3, -.04], [.48, -.1], [.72, -.15], [.98, -.14], [1.16, -.1], [1.28, -.04]]],
    a: [[[.2, .78], [.38, .97], [.62, .96], [.73, .78], [.74, .4], [.75, .1], [.86, 0], [1, .08]], [[.73, .58], [.35, .47], [.1, .27], [.2, .03], [.45, .02], [.73, .2]]],
    d: [[[.74, .82], [.45, .98], [.15, .8], [.07, .45], [.17, .1], [.45, 0], [.74, .18]], [[.58, 9.04], [.78, 9], [.78, .15], [.9, 0], [1, .06]]],
    e: [[[.08, .55], [.92, .55], [.86, .86], [.5, 1], [.15, .85], [.06, .5], [.18, .12], [.5, 0], [.88, .18]]],
    i: [[[.5, 1], [.5, 0]], [[.5, 9.04], [.5, 9.14]]],
    n: [[[.14, 1], [.14, 0]], [[.14, .62], [.35, .93], [.6, .98], [.8, .8], [.82, 0]]],
    r: [[[.22, 1], [.22, 0]], [[.22, .6], [.45, .92], [.72, .99], [.9, .88]]],
    t: [[[.35, 9], [.35, .15], [.55, 0], [.9, .1]], [[0, .93], [.85, .93]]],
    v: [[[0, 1], [.5, 0], [1, 1]]],
    y: [[[0, 1], [.5, .02]], [[1, 1], [.6, .05], [.4, -8.6], [.25, -9], [.08, -8.85]]]
  };

  function clamp(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function jerk(u) { return u * u * u * (10 + u * (6 * u - 15)); }  // a hand's minimum-jerk stroke: slow, fast, slow
  function unjerk(q) { var lo = 0, hi = 1; for (var i = 0; i < 24; i++) { var mid = (lo + hi) / 2; if (jerk(mid) < q) lo = mid; else hi = mid; } return (lo + hi) / 2; }
  function hash(i) { var s = Math.sin(i * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); }

  // Squared Euclidean distance transform (Felzenszwalb and Huttenlocher), in place.
  function edt1(f, n, d, v, z) {
    var k = 0, q, s;
    v[0] = 0; z[0] = -Infinity; z[1] = Infinity;
    for (q = 1; q < n; q++) {
      s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]);
      while (s <= z[k]) { k--; s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]); }
      k++; v[k] = q; z[k] = s; z[k + 1] = Infinity;
    }
    for (k = 0, q = 0; q < n; q++) { while (z[k + 1] < q) k++; d[q] = (q - v[k]) * (q - v[k]) + f[v[k]]; }
  }
  function edt(g, W) {
    var f = new Float64Array(W), d = new Float64Array(W), v = new Int32Array(W), z = new Float64Array(W + 1), x, y;
    for (x = 0; x < W; x++) { for (y = 0; y < W; y++) f[y] = g[y * W + x]; edt1(f, W, d, v, z); for (y = 0; y < W; y++) g[y * W + x] = d[y]; }
    for (y = 0; y < W; y++) { for (x = 0; x < W; x++) f[x] = g[y * W + x]; edt1(f, W, d, v, z); for (x = 0; x < W; x++) g[y * W + x] = d[x]; }
  }
  function sample(F, x, y) {
    var u = G / 100, fx = Math.max(0, Math.min(G - 1e-6, x * u)), fy = Math.max(0, Math.min(G - 1e-6, y * u)), i = fx | 0, j = fy | 0, tx = fx - i, ty = fy - j, S = G + 1, p = j * S + i;
    return (F[p] * (1 - tx) + F[p + 1] * tx) * (1 - ty) + (F[p + S] * (1 - tx) + F[p + S + 1] * tx) * ty;
  }

  // A word set in the wordmark's font, letter by letter, each with a breath of unevenness (a hair off the baseline,
  // a fraction of a degree of slant), fitted to boxW x boxH and centred: its distance field (seal units, negative
  // inside) and where each letter sits.
  function displayFont() {
    var cs = getComputedStyle(document.documentElement);
    return (cs.getPropertyValue("--display").trim() || "Baskerville, serif").replace(/var\(--serif\)/g, cs.getPropertyValue("--serif").trim() || "serif");
  }
  function setWord(text, family, boxW, boxH, seed) {
    var R = G * 2, S = R + 1, u = 100 / R, c = document.createElement("canvas");
    c.width = c.height = S;
    var x = c.getContext("2d", { willReadFrequently: true }), font = function (px) { return "400 " + px + "px " + family; };
    x.font = font(200);
    var m = x.measureText(text);
    var f = 200 * Math.min(boxW / u / (m.actualBoundingBoxLeft + m.actualBoundingBoxRight), boxH / u / (m.actualBoundingBoxAscent + m.actualBoundingBoxDescent));
    x.font = font(f);
    m = x.measureText(text);
    var ox = R / 2 + 0.5 - (m.actualBoundingBoxRight - m.actualBoundingBoxLeft) / 2, base = R / 2 + 0.5 + (m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2;
    var xh = x.measureText("x").actualBoundingBoxAscent * u, glyphs = [];
    for (var i = 0; i < text.length; i++) {
      var ch = text[i], gx = ox + x.measureText(text.slice(0, i)).width, g = x.measureText(ch);
      var dy = (hash(seed + i) - 0.5) * 0.02 * f, rot = (hash(seed + i + 50) - 0.5) * 0.02;
      x.save(); x.translate(gx, base + dy); x.rotate(rot); x.fillText(ch, 0, 0); x.restore();
      var o = x.measureText("O");
      glyphs.push({ ch: ch, l: (gx - g.actualBoundingBoxLeft) * u, r: (gx + g.actualBoundingBoxRight) * u, t: (base - g.actualBoundingBoxAscent) * u,
                    b: (base + g.actualBoundingBoxDescent) * u, ox: gx * u, base: base * u, dy: dy * u, rot: rot, xh: xh,
                    ow: (o.actualBoundingBoxLeft + o.actualBoundingBoxRight) * u, oh: (o.actualBoundingBoxAscent + o.actualBoundingBoxDescent) * u });
    }
    var a = x.getImageData(0, 0, S, S).data, N = S * S, fin = new Float64Array(N), fout = new Float64Array(N), p;
    for (p = 0; p < N; p++) { var ins = a[p * 4 + 3] > 127; fin[p] = ins ? 0 : 1e20; fout[p] = ins ? 1e20 : 0; }
    edt(fin, S); edt(fout, S);
    var Gs = G + 1, F = new Float32Array(Gs * Gs);
    for (var j = 0; j < Gs; j++) for (i = 0; i < Gs; i++) {
      p = 2 * j * S + 2 * i;
      F[j * Gs + i] = (fin[p] > 0 ? Math.sqrt(fin[p]) - 0.5 : 0.5 - Math.sqrt(fout[p])) * u;
    }
    return { F: F, glyphs: glyphs };
  }

  // The closed curves where the field equals L (marching squares, joined through shared cell edges).
  function contours(F, L) {
    var S = G + 1, u = 100 / G, pos = {}, adj = {};
    function link(a, b) {
      pos[a[0]] = [a[1], a[2]]; pos[b[0]] = [b[1], b[2]];
      (adj[a[0]] = adj[a[0]] || []).push(b[0]); (adj[b[0]] = adj[b[0]] || []).push(a[0]);
    }
    for (var j = 0; j < G; j++) for (var i = 0; i < G; i++) {
      var p = j * S + i, a = F[p] - L, b = F[p + 1] - L, c = F[p + S + 1] - L, d = F[p + S] - L;
      var idx = (a > 0 ? 8 : 0) | (b > 0 ? 4 : 0) | (c > 0 ? 2 : 0) | (d > 0 ? 1 : 0);
      if (idx === 0 || idx === 15) continue;
      var x = i * u, y = j * u;
      var T = [p * 2, x + u * a / (a - b), y], Rr = [(p + 1) * 2 + 1, x + u, y + u * b / (b - c)],
          B = [(p + S) * 2, x + u * d / (d - c), y + u], Lf = [p * 2 + 1, x, y + u * a / (a - d)];
      if (idx === 1 || idx === 14) link(Lf, B);
      else if (idx === 2 || idx === 13) link(B, Rr);
      else if (idx === 3 || idx === 12) link(Lf, Rr);
      else if (idx === 4 || idx === 11) link(T, Rr);
      else if (idx === 6 || idx === 9) link(T, B);
      else if (idx === 7 || idx === 8) link(Lf, T);
      else if ((idx === 5) === (a + b + c + d > 0)) { link(Lf, T); link(B, Rr); }
      else { link(T, Rr); link(Lf, B); }
    }
    var seen = {}, out = [];
    Object.keys(adj).forEach(function (start) {
      if (seen[start]) return;
      var chain = [pos[start]], prev = null, cur = start;
      seen[start] = 1;
      for (;;) {
        var next = adj[cur].filter(function (e) { return String(e) !== prev && !seen[e]; })[0];
        if (next === undefined) break;
        seen[next] = 1; chain.push(pos[next]); prev = cur; cur = String(next);
      }
      out.push(curve(chain, true));
    });
    return out.filter(function (c) { return c.len >= 1; });
  }
  function curve(pts, closed) {
    var p = closed ? pts.concat([pts[0]]) : pts, cum = [0];
    for (var i = 1; i < p.length; i++) cum.push(cum[i - 1] + Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]));
    return { pts: p, cum: cum, len: cum[cum.length - 1], closed: closed };
  }
  function at(c, d) {
    d = c.closed ? ((d % c.len) + c.len) % c.len : Math.max(0, Math.min(c.len, d));
    var lo = 0, hi = c.cum.length - 1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (c.cum[mid] < d) lo = mid; else hi = mid; }
    var f = (d - c.cum[lo]) / ((c.cum[hi] - c.cum[lo]) || 1);
    return [lerp(c.pts[lo][0], c.pts[hi][0], f), lerp(c.pts[lo][1], c.pts[hi][1], f)];
  }
  function piece(c, d0, d1) { var out = []; for (var i = 0; i < P; i++) out.push(at(c, lerp(d0, d1, i / (P - 1)))); return out; }
  // Share NT threads among the curves by length (at least one each) and cut each curve into its threads.
  function share(curves) {
    curves = curves.sort(function (a, b) { return b.len - a.len; }).slice(0, NT);
    var tot = curves.reduce(function (s, c) { return s + c.len; }, 0), i;
    var n = curves.map(function (c) { return Math.max(1, Math.round(NT * c.len / tot)); }), sum = n.reduce(function (a, b) { return a + b; }, 0);
    while (sum > NT) { var big = 0; for (i = 1; i < n.length; i++) if (n[i] > n[big]) big = i; n[big]--; sum--; }
    while (sum < NT) { var most = 0; for (i = 1; i < n.length; i++) if (curves[i].len / n[i] > curves[most].len / n[most]) most = i; n[most]++; sum++; }
    var out = [];
    curves.forEach(function (c, ci) { var l = c.len / n[ci]; for (var q = 0; q < n[ci]; q++) out.push(piece(c, q * l, (q + 1.03) * l)); });
    return out;
  }
  function angle(p) { var a = Math.atan2(p[1] - 50, p[0] - 50) + Math.PI / 2; return a < 0 ? a + 2 * Math.PI : a; }
  function centre(s) { var x = 0, y = 0; s.forEach(function (p) { x += p[0]; y += p[1]; }); return [x / s.length, y / s.length]; }
  function turn(s, a) { var c = Math.cos(a), n = Math.sin(a); return s.map(function (p) { var x = p[0] - 50, y = p[1] - 50; return [50 + x * c - y * n, 50 + x * n + y * c]; }); }
  // A shape's threads in clockwise order from twelve o'clock, each running clockwise: thread r of every shape meets
  // the cord at the same place, so the threads travel short ways and never cross the seal.
  function order(segs, signs) {
    var o = segs.map(function (s, i) { return { i: i, a: angle(centre(s)) }; }).sort(function (a, b) { return a.a - b.a; });
    return {
      segs: o.map(function (e) {
        var s = segs[e.i], d = angle(s[s.length - 1]) - angle(s[0]);
        if (d > Math.PI) d -= 2 * Math.PI; else if (d < -Math.PI) d += 2 * Math.PI;
        return d < 0 ? s.slice().reverse() : s;
      }),
      signs: signs && o.map(function (e) { return signs[e.i]; })
    };
  }
  function lattice() {  // the seal's own lattice (as build.seal draws it), each curve cut into equal threads
    var segs = [], signs = [], per = NT / (2 * M);
    [1, -1].forEach(function (sign) {
      for (var j = 0; j < M; j++) {
        var pts = [], rot = sign * j * Math.PI / (M * K);
        for (var i = 0; i < 360; i++) { var t = 2 * Math.PI * i / 360, r = R0 + AMP * Math.sin(K * t); pts.push([50 + r * Math.cos(t + rot), 50 + r * Math.sin(t + rot)]); }
        var c = curve(pts, true);
        for (var q = 0; q < per; q++) { segs.push(piece(c, q * c.len / per, (q + 1.03) * c.len / per)); signs.push(sign); }
      }
    });
    return order(segs, signs);
  }
  // The cord between shapes: three strands twisted round the middle.
  function cord(r, psi) {
    var th = -Math.PI / 2 + 2 * Math.PI * (r + 0.5) / NT + psi, span = 6 * Math.PI / NT, ph = 2 * Math.PI * (r % 3) / 3, out = [];
    for (var i = 0; i < P; i++) {
      var a = th - span / 2 + span * i / (P - 1), rad = CORD + 2.8 * Math.sin(K * (a - psi) + ph);
      out.push([50 + rad * Math.cos(a), 50 + rad * Math.sin(a)]);
    }
    return out;
  }

  // The pen: each letter's path fitted to where the letter sits, smoothed, and pulled onto the middle of its strokes.
  function spline(pts) {
    var out = [], e = [pts[0]].concat(pts, [pts[pts.length - 1]]);
    for (var i = 1; i < e.length - 2; i++) {
      var p0 = e[i - 1], p1 = e[i], p2 = e[i + 1], p3 = e[i + 2], n = Math.max(2, Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / 0.25));
      for (var k = 0; k < n; k++) {
        var t = k / n, t2 = t * t, t3 = t2 * t, q = [];
        for (var d = 0; d < 2; d++) q.push(0.5 * (2 * p1[d] + (p2[d] - p0[d]) * t + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * t2 + (3 * p1[d] - p0[d] - 3 * p2[d] + p3[d]) * t3));
        out.push(q);
      }
    }
    out.push(pts[pts.length - 1]);
    return out;
  }
  function snap(F, pts, S) {
    var off = pts.map(function (p, i) {
      var a = pts[Math.max(0, i - 2)], b = pts[Math.min(pts.length - 1, i + 2)], tx = b[0] - a[0], ty = b[1] - a[1], tl = Math.hypot(tx, ty) || 1;
      var nx = -ty / tl, ny = tx / tl, best = 0, bv = sample(F, p[0], p[1]);
      for (var s = -S; s <= S; s += S / 8) { var v = sample(F, p[0] + nx * s, p[1] + ny * s); if (v < bv - 1e-6) { bv = v; best = s; } }
      return [nx, ny, best];
    });
    return pts.map(function (p, i) {
      var sum = 0, n = 0;
      for (var j = Math.max(0, i - 5); j <= Math.min(pts.length - 1, i + 5); j++) { sum += off[j][2]; n++; }
      return [p[0] + off[i][0] * sum / n, p[1] + off[i][1] * sum / n];
    });
  }
  function strokes(word) {
    var out = [];
    word.glyphs.forEach(function (g, gi) {
      var digit = /[0-9Q]/.test(g.ch), spec = DUCTUS[g.ch] || [[[0, .5], [1, .5]]];
      var c = Math.cos(g.rot), s = Math.sin(g.rot), cy = g.base + g.dy;
      spec.forEach(function (st) {
        var inO = st[0] === "o" || st[0] === "ot", near = st[0] === "ot" ? 0.3 : 1;
        var pts = (inO ? st.slice(1) : st).map(function (p) {
          var X = g.l + p[0] * (inO ? g.ow : g.r - g.l), Y = inO ? g.t + (1 - p[1]) * g.oh : digit ? g.b - p[1] * (g.b - g.t) : p[1] >= 9 ? g.t + (p[1] - 9) * g.xh : p[1] <= -9 ? g.b - (p[1] + 9) * g.xh : g.base - p[1] * g.xh;
          Y += g.dy;
          var dx = X - g.ox, dy = Y - cy;
          return [g.ox + dx * c - dy * s, cy + dx * s + dy * c];
        });
        out.push({ pts: snap(word.F, spline(pts), near * (digit ? 0.09 * (g.b - g.t) : 0.22 * g.xh)), letter: gi });
      });
    });
    return out;
  }
  // When the pen passes each point: a stroke takes a hand's time (its length, a little uneven), the pen lifts between
  // strokes and a little longer between letters; the whole word is then paced to `dur` seconds, rhythm kept.
  function pen(word, dur) {
    var st = strokes(word), t = 0, segs = [], samples = [];
    st.forEach(function (s, i) {
      var c = curve(s.pts, false), d = (0.07 + c.len / 140) * (0.88 + 0.24 * hash(i * 3 + 11 * s.letter));
      if (i) t += (s.letter !== st[i - 1].letter ? 0.085 : 0.05) * (0.8 + 0.4 * hash(i * 5 + 1));
      segs.push({ c: c, t0: t, d: d });
      for (var q = 0; q <= c.len; q += 0.3) { var p = at(c, q); samples.push([p[0], p[1], t + d * unjerk(q / c.len)]); }
      t += d;
    });
    var k = dur / t;
    segs.forEach(function (g) { g.t0 *= k; g.d *= k; });
    samples.forEach(function (p) { p[2] *= k; });
    return { segs: segs, samples: samples, dur: dur };
  }
  function penAt(pn, tau) {
    var s = pn.segs, i;
    for (i = 0; i < s.length; i++) {
      if (tau < s[i].t0) {
        if (!i) return at(s[0].c, 0);
        var a = at(s[i - 1].c, s[i - 1].c.len), b = at(s[i].c, 0), q = ease((tau - s[i - 1].t0 - s[i - 1].d) / (s[i].t0 - s[i - 1].t0 - s[i - 1].d));
        return [lerp(a[0], b[0], q), lerp(a[1], b[1], q)];
      }
      if (tau <= s[i].t0 + s[i].d) return at(s[i].c, s[i].c.len * jerk((tau - s[i].t0) / s[i].d));
    }
    return at(s[s.length - 1].c, s[s.length - 1].c.len);
  }
  // Each word's threads and, for every point on them, when the pen reaches it.
  function word(text, boxW, boxH, levels, seed, dur) {
    var w = setWord(text, family, boxW, boxH, seed), cs = [];
    levels.forEach(function (L) { cs = cs.concat(contours(w.F, L)); });
    var segs = order(share(cs)).segs, pn = pen(w, dur), sm = pn.samples;
    var times = segs.map(function (s) {
      return s.map(function (p) {
        var best = Infinity, t = 0;
        for (var i = 0; i < sm.length; i++) { var dx = sm[i][0] - p[0], dy = sm[i][1] - p[1], d = dx * dx + dy * dy; if (d < best) { best = d; t = sm[i][2]; } }
        return t;
      });
    });
    return { segs: segs, times: times, pen: pn };
  }

  var family, shapes, words, signs, PH, playing = false, start = 0, theta = 0, ctx, ink, tint, dev;
  function prepare() {
    family = displayFont();
    var rest = lattice(), deep = [], i;
    for (i = 0; i < 9; i++) deep.push(-0.62 * i);
    signs = rest.signs;
    words = {
      n: word(DAYS, DAYS.length > 1 ? 58 : 44, 54, deep, 3, 0.45 + 0.22 * DAYS.length),
      day: word("day", 60, 38, [0, -0.5, -1, -1.5, -2], 17, 1),
      narrative: word("narrative", 72, 30, [0, -0.45, -0.9, -1.35], 29, 1.7),
      q: word("Q", 56, 54, deep, 41, 0.85)  // the Q of Qaiet Times, last, before the seal settles
    };
    shapes = { rest: rest.segs, n: words.n.segs, day: words.day.segs, narrative: words.narrative.segs, q: words.q.segs };
    PH = [
      { move: "rest", to: "cord", dur: 1.1 },
      { write: "n", dur: words.n.pen.dur }, { hold: "n", dur: 0.6 }, { move: "n", to: "cord", dur: 0.8 },
      { write: "day", dur: words.day.pen.dur }, { hold: "day", dur: 0.5 }, { move: "day", to: "cord", dur: 0.8 },
      { write: "narrative", dur: words.narrative.pen.dur }, { hold: "narrative", dur: 0.7 }, { move: "narrative", to: "cord", dur: 0.8 },
      { write: "q", dur: words.q.pen.dur }, { hold: "q", dur: 0.8 },
      { move: "q", to: "rest", dur: 2.8, last: true }
    ];
  }

  function begin() { ctx.setTransform(canvas.width / 100, 0, 0, canvas.width / 100, 0, 0); ctx.clearRect(0, 0, 100, 100); ctx.lineJoin = "round"; ctx.lineCap = "round"; }
  // Threads in the seal's tint, or in ink (inked 1), or on their way between the two.
  function stroke(threads, alpha, width, inked) {
    var path = new Path2D();
    threads.forEach(function (s) { path.moveTo(s[0][0], s[0][1]); for (var i = 1; i < s.length; i++) path.lineTo(s[i][0], s[i][1]); });
    ctx.lineWidth = width * dev;
    if (inked < 1) { ctx.strokeStyle = tint; ctx.globalAlpha = alpha * (1 - inked); ctx.stroke(path); }
    if (inked > 0) { ctx.strokeStyle = ink; ctx.globalAlpha = alpha * inked; ctx.stroke(path); }
  }
  // The pen at time tau of writing `key`: what it has written (the newest ink darker and a touch wider, as if still
  // wet), the cord paying out what is left of its thread, and that thread running taut to the pen.
  function drawWrite(key, tau) {
    var w = words[key], settled = new Path2D(), wet = new Path2D(), prog = tau / w.pen.dur;
    begin();
    w.segs.forEach(function (s, r) {
      var ts = w.times[r];
      for (var j = 0; j < P - 1; j++) {
        var t = Math.max(ts[j], ts[j + 1]);
        if (t > tau) continue;
        var path = tau - t < 0.3 ? wet : settled;
        path.moveTo(s[j][0], s[j][1]); path.lineTo(s[j + 1][0], s[j + 1][1]);
      }
    });
    ctx.strokeStyle = ink;
    ctx.globalAlpha = 0.85; ctx.lineWidth = 1.1 * dev; ctx.stroke(settled);
    ctx.globalAlpha = 1; ctx.lineWidth = 1.6 * dev; ctx.stroke(wet);
    if (prog >= 1) return;
    var left = [], first = Math.floor(prog * NT);
    for (var r = first; r < NT; r++) left.push(cord(r, 0));
    stroke(left, REST, 1.1, 0);
    var from = left[0][0], to = penAt(w.pen, tau);
    ctx.beginPath(); ctx.moveTo(from[0], from[1]); ctx.lineTo(to[0], to[1]);
    ctx.globalAlpha = 0.24; ctx.lineWidth = dev; ctx.stroke();
  }
  function drawMove(ph, tau) {
    var out = [], phi = ph.last ? 0.75 * Math.pow(1 - tau, 2.2) : 0, psi = ph.last ? 0.45 * ease(tau) : 0;
    for (var r = 0; r < NT; r++) {
      var A = ph.move === "rest" ? turn(shapes.rest[r], theta) : shapes[ph.move][r], C = cord(r, psi), from, to, q;
      var p = clamp((tau - 0.3 * r / NT) / 0.7);
      if (ph.to === "cord") { from = A; to = C; q = ease(p); }
      else {
        var B = phi ? turn(shapes.rest[r], signs[r] * phi) : shapes.rest[r];  // the lattice, still turning, each half its own way
        if (p < 0.45) { from = A; to = C; q = ease(p / 0.45); }
        else if (p < 0.55) { from = C; to = C; q = 0; }
        else { from = C; to = B; q = ease((p - 0.55) / 0.45); }
      }
      var pts = [];
      for (var j = 0; j < P; j++) pts.push([lerp(from[j][0], to[j][0], q), lerp(from[j][1], to[j][1], q)]);
      out.push(pts);
    }
    begin();  // the lattice and the cord wear the tint; a word leaving for the cord gives up its ink on the way
    stroke(out, REST, 1.1, ph.move === "rest" ? 0 : 1 - ease(clamp(tau / (ph.last ? 0.45 : 0.8))));
  }
  function render(t) {
    for (var i = 0, acc = 0; i < PH.length; acc += PH[i++].dur) {
      var ph = PH[i];
      if (t >= acc + ph.dur) continue;
      var tau = (t - acc) / ph.dur;
      if (ph.write) drawWrite(ph.write, t - acc);
      else if (ph.hold) drawWrite(ph.hold, words[ph.hold].pen.dur + t - acc);
      else drawMove(ph, tau);
      return true;
    }
    return false;
  }
  function frame(now) {
    if (render((now - start) / 1000)) { requestAnimationFrame(frame); return; }
    if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    seal.classList.remove("playing");
    void seal.offsetWidth;  // restart the lattice's turn from where the threads left it
    seal.classList.add("lat-turning");
    playing = false;
  }
  function play() {
    if (playing) return;
    playing = true;
    if (!shapes) prepare();
    // the lattice may be turning: the threads start from where it is now
    var tf = getComputedStyle(lattices[0]).transform, mx = /matrix\(([^,]+),\s*([^,]+)/.exec(tf || "");
    theta = mx ? Math.atan2(+mx[2], +mx[1]) : 0;
    seal.classList.remove("lat-turning");
    var size = seal.getBoundingClientRect().width, dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.height = Math.round(size * dpr);
    dev = 100 / canvas.width;
    canvas.setAttribute("aria-hidden", "true");
    seal.appendChild(canvas);
    ctx = canvas.getContext("2d");
    var cs = getComputedStyle(document.documentElement);
    ink = cs.getPropertyValue("--ink").trim() || "#1a1816";
    tint = ink;
    if (STOPS.length) {  // the same radial gradient as build.seal's, in this theme's stance colors
      tint = ctx.createRadialGradient(50, 50, 0, 50, 50, 50);
      STOPS.forEach(function (s) { tint.addColorStop(Math.max(0, Math.min(1, s[0])), cs.getPropertyValue(TINT[s[1]]).trim() || ink); });
    }
    seal.classList.add("playing");
    requestAnimationFrame(function (now) { start = now; frame(now); });
  }

  seal.classList.add("can-play");
  seal.addEventListener("click", play);
  seal.addEventListener("mouseenter", play);
  if (document.hidden) document.addEventListener("visibilitychange", function once() { document.removeEventListener("visibilitychange", once); setTimeout(play, 500); });
  else setTimeout(play, 500);
})();
