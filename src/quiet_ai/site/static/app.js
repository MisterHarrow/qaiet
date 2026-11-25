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

// The narrative seal, on a narrative's page: the lattice's threads twist into a cord, which unwinds into the day
// count, then "day", then "narrative", winding back into the cord between words. On the way back the two halves of the
// lattice are still turning against each other and slow until they lock in place. The letters are cut from the
// headline serif: each word is set on a hidden canvas, its distance field gives the outline and an inline (the way
// engraved type is cut), and those curves are shared out among the threads. The day ring (SVG) never moves; only the
// lattice and the count step aside while the canvas draws the threads. It plays once when the page opens and again
// when the seal is clicked. Without JS, or when the reader asks for reduced motion, it rests.
(function () {
  var seal = document.querySelector(".seal.big[data-k]");
  if (!seal || !window.requestAnimationFrame || document.hidden) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var canvas = document.createElement("canvas");
  if (!canvas.getContext) return;
  var K = +seal.getAttribute("data-k"), M = +seal.getAttribute("data-m"), DAYS = seal.getAttribute("data-days");
  var R0 = 29, AMP = 7.5, NT = 72, P = 44, G = 200;  // must match build.seal; threads; points per thread; field grid

  function clamp(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

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
  // The signed distance (in seal units, negative inside) to `text` set in the headline serif, fitted to boxW x boxH.
  function textField(text, family, boxW, boxH) {
    var R = G * 2, S = R + 1, c = document.createElement("canvas");
    c.width = c.height = S;
    var x = c.getContext("2d", { willReadFrequently: true }), font = function (px) { return "500 " + px + "px " + family; };
    x.font = font(200);
    var m = x.measureText(text);
    var k = Math.min(boxW / (m.actualBoundingBoxLeft + m.actualBoundingBoxRight), boxH / (m.actualBoundingBoxAscent + m.actualBoundingBoxDescent)) * R / 100;
    x.font = font(200 * k);
    m = x.measureText(text);
    x.fillText(text, R / 2 + 0.5 - (m.actualBoundingBoxRight - m.actualBoundingBoxLeft) / 2, R / 2 + 0.5 + (m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2);
    var a = x.getImageData(0, 0, S, S).data, N = S * S, fin = new Float64Array(N), fout = new Float64Array(N), p;
    for (p = 0; p < N; p++) { var ins = a[p * 4 + 3] > 127; fin[p] = ins ? 0 : 1e20; fout[p] = ins ? 1e20 : 0; }
    edt(fin, S); edt(fout, S);
    var Gs = G + 1, out = new Float32Array(Gs * Gs);
    for (var j = 0; j < Gs; j++) for (var i = 0; i < Gs; i++) {
      p = 2 * j * S + 2 * i;
      out[j * Gs + i] = (fin[p] > 0 ? Math.sqrt(fin[p]) - 0.5 : 0.5 - Math.sqrt(fout[p])) * 100 / R;
    }
    return out;
  }
  // The closed curves where the field equals L (marching squares, joined through shared cell edges).
  function contours(F, L) {
    var S = G + 1, u = 100 / G, pos = {}, adj = {};
    function edge(e) { pos[e[0]] = [e[1], e[2]]; }
    function link(a, b) { edge(a); edge(b); (adj[a[0]] = adj[a[0]] || []).push(b[0]); (adj[b[0]] = adj[b[0]] || []).push(a[0]); }
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
    return out.filter(function (c) { return c.len >= 1.2; });
  }
  function curve(pts, closed) {
    var p = closed ? pts.concat([pts[0]]) : pts, cum = [0];
    for (var i = 1; i < p.length; i++) cum.push(cum[i - 1] + Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]));
    return { pts: p, cum: cum, len: cum[cum.length - 1] };
  }
  function at(c, d) {
    d = ((d % c.len) + c.len) % c.len;
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
  function word(text, family, boxW, boxH, levels) {
    var F = textField(text, family, boxW, boxH), cs = [];
    levels.forEach(function (L) { cs = cs.concat(contours(F, L)); });
    return order(share(cs)).segs;
  }
  // The cord between shapes: three strands twisted round the middle, turning slowly.
  function cord(r, psi) {
    var th = -Math.PI / 2 + 2 * Math.PI * (r + 0.5) / NT + psi, span = 6 * Math.PI / NT, ph = 2 * Math.PI * (r % 3) / 3, out = [];
    for (var i = 0; i < P; i++) {
      var a = th - span / 2 + span * i / (P - 1), rad = 30 + 2.4 * Math.sin(K * (a - psi) + ph);
      out.push([50 + rad * Math.cos(a), 50 + rad * Math.sin(a)]);
    }
    return out;
  }

  // The timeline in seconds: each change of shape, then a pause to read; the last change slows to rest.
  var SEQ = [
    { from: "rest", to: "n", dur: 1.5 }, { hold: "n", dur: 0.85 },
    { from: "n", to: "day", dur: 1.25 }, { hold: "day", dur: 0.7 },
    { from: "day", to: "narrative", dur: 1.25 }, { hold: "narrative", dur: 1.05 },
    { from: "narrative", to: "rest", dur: 3, last: true }
  ];
  var shapes = null, signs, playing = false, start = 0, ctx, ink, dev;

  function prepare() {
    var family = getComputedStyle(document.documentElement).getPropertyValue("--serif").trim() || "serif";
    var rest = lattice();
    signs = rest.signs;
    shapes = {
      rest: rest.segs,
      n: word(DAYS, family, DAYS.length > 1 ? 58 : 46, 54, [0, -1.4, -2.8, -4.2, -5.6]),
      day: word("day", family, 60, 36, [0, -1, -2]),
      narrative: word("narrative", family, 72, 28, [0, -0.7])
    };
  }
  function draw(threads, alpha) {
    ctx.setTransform(canvas.width / 100, 0, 0, canvas.width / 100, 0, 0);
    ctx.clearRect(0, 0, 100, 100);
    ctx.beginPath();
    threads.forEach(function (s) { ctx.moveTo(s[0][0], s[0][1]); for (var i = 1; i < s.length; i++) ctx.lineTo(s[i][0], s[i][1]); });
    ctx.strokeStyle = ink; ctx.globalAlpha = alpha; ctx.lineWidth = 1.1 * dev; ctx.lineJoin = "round"; ctx.stroke();
  }
  function frame(now) {
    var t = (now - start) / 1000, i = 0, acc = 0;
    while (i < SEQ.length && t >= acc + SEQ[i].dur) acc += SEQ[i++].dur;
    if (i === SEQ.length) return finish();
    var st = SEQ[i], tau = (t - acc) / st.dur;
    if (st.hold) { draw(shapes[st.hold], 0.85); requestAnimationFrame(frame); return; }
    if (st.last && tau > 0.6) seal.classList.add("settling");
    var psi = 0.45 * ease(tau), phi = st.last ? 0.75 * Math.pow(1 - tau, 2.2) : 0, out = [];
    for (var r = 0; r < NT; r++) {
      var A = shapes[st.from][r], B = shapes[st.to][r], C = cord(r, psi);
      if (st.last && phi) {  // the lattice, still turning, each half its own way
        var cs = Math.cos(signs[r] * phi), sn = Math.sin(signs[r] * phi);
        B = B.map(function (p) { var x = p[0] - 50, y = p[1] - 50; return [50 + x * cs - y * sn, 50 + x * sn + y * cs]; });
      }
      var p = clamp((tau - 0.3 * r / NT) / 0.7), from, to, q;
      if (p < 0.45) { from = A; to = C; q = ease(p / 0.45); }
      else if (p < 0.55) { from = C; to = C; q = 0; }
      else { from = C; to = B; q = ease((p - 0.55) / 0.45); }
      var pts = [];
      for (var j = 0; j < P; j++) pts.push([lerp(from[j][0], to[j][0], q), lerp(from[j][1], to[j][1], q)]);
      out.push(pts);
    }
    var lat = 0.62;  // the resting lattice's opacity on the narrative's page (style.css)
    draw(out, st.from === "rest" ? lerp(lat, 0.85, tau) : st.last ? lerp(0.85, lat, clamp((tau - 0.5) / 0.5)) : 0.85);
    requestAnimationFrame(frame);
  }
  function finish() {
    seal.classList.remove("playing", "settling");
    if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    playing = false;
  }
  function play() {
    if (playing) return;
    playing = true;
    if (!shapes) prepare();
    var size = seal.getBoundingClientRect().width, dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.height = Math.round(size * dpr);
    dev = 100 / canvas.width;
    canvas.setAttribute("aria-hidden", "true");
    seal.insertBefore(canvas, seal.querySelector(".seal-cap"));
    ctx = canvas.getContext("2d");
    ink = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#1a1816";
    draw(shapes.rest, 0.62);
    seal.classList.add("playing");
    requestAnimationFrame(function (now) { start = now; frame(now); });
  }

  seal.classList.add("can-play");
  seal.addEventListener("click", play);
  setTimeout(play, 500);
})();
