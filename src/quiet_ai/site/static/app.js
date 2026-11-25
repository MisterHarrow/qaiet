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

// The narrative seal, on a narrative's page: its strings let go of the circle and spell the day count, then
// "day", then "narrative", then wind back into the seal, slowing until it rests. It plays once when the page
// opens and again when the seal is clicked. Without JS, or when the reader asks for reduced motion, it rests.
(function () {
  var seal = document.querySelector(".seal.big[data-k]");
  if (!seal || !window.requestAnimationFrame || document.hidden) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var canvas = document.createElement("canvas");
  if (!canvas.getContext) return;
  var K = +seal.getAttribute("data-k"), M = +seal.getAttribute("data-m"), DAYS = seal.getAttribute("data-days");
  var R0 = 29, AMP = 7.5, P = 40, N = 2 * M * 4, C = 50;

  // A monoline alphabet for the strings, y up: x-height 1, ascenders and figures 1.5, descenders -0.5.
  // ["M", x, y] moves, ["L", x, y] draws a line, ["E", cx, cy, rx, ry, from, to] an elliptical arc (degrees).
  var BOWL = ["E", 0.42, 0.5, 0.42, 0.5, 0, 360];
  var G = {
    "0": [1, [[["E", 0.5, 0.75, 0.5, 0.75, 90, 450]]]],
    "1": [0.62, [[["M", 0.1, 1.22], ["L", 0.46, 1.5], ["L", 0.46, 0]]]],
    "2": [0.96, [[["E", 0.48, 1.07, 0.44, 0.43, 165, -40], ["L", 0, 0], ["L", 0.96, 0]]]],
    "3": [0.94, [[["E", 0.47, 1.13, 0.4, 0.37, 155, -90]], [["E", 0.47, 0.4, 0.47, 0.4, 90, -150]]]],
    "4": [1, [[["M", 0.72, 0], ["L", 0.72, 1.5], ["L", 0, 0.42], ["L", 1, 0.42]]]],
    "5": [0.94, [[["M", 0.9, 1.5], ["L", 0.14, 1.5], ["L", 0.08, 0.86], ["E", 0.47, 0.47, 0.47, 0.47, 125, -145]]]],
    "6": [0.96, [[["M", 0.8, 1.5], ["L", 0.16, 0.7], ["E", 0.48, 0.48, 0.48, 0.48, 150, 510]]]],
    "7": [0.96, [[["M", 0, 1.5], ["L", 0.96, 1.5], ["L", 0.3, 0]]]],
    "8": [0.96, [[["E", 0.48, 1.13, 0.37, 0.37, -90, 270]], [["E", 0.48, 0.41, 0.45, 0.41, 90, 450]]]],
    "9": [0.96, [[["M", 0.16, 0], ["L", 0.8, 0.8], ["E", 0.48, 1.02, 0.48, 0.48, -30, 330]]]],
    a: [0.84, [[BOWL], [["M", 0.84, 1], ["L", 0.84, 0]]]],
    d: [0.84, [[BOWL], [["M", 0.84, 1.5], ["L", 0.84, 0]]]],
    e: [0.84, [[["M", 0, 0.5], ["L", 0.84, 0.5], ["E", 0.42, 0.5, 0.42, 0.5, 0, 318]]]],
    i: [0, [[["M", 0, 0], ["L", 0, 1]], [["M", 0, 1.3], ["L", 0, 1.4]]]],
    n: [0.72, [[["M", 0, 0], ["L", 0, 1]], [["M", 0, 0.56], ["E", 0.36, 0.6, 0.36, 0.4, 180, 0], ["L", 0.72, 0]]]],
    r: [0.52, [[["M", 0, 0], ["L", 0, 1]], [["M", 0, 0.56], ["E", 0.36, 0.6, 0.36, 0.4, 180, 55]]]],
    t: [0.5, [[["M", 0.2, 1.36], ["L", 0.2, 0]], [["M", 0, 1], ["L", 0.5, 1]]]],
    v: [0.8, [[["M", 0, 1], ["L", 0.4, 0], ["L", 0.8, 1]]]],
    y: [0.84, [[["M", 0, 1], ["L", 0.42, 0]], [["M", 0.84, 1], ["L", 0.22, -0.5]]]]
  };

  function dense(stroke) {  // a stroke as closely spaced points
    var pts = [], cur = null;
    function lineTo(x, y) {
      if (!cur) { pts.push([x, y]); cur = [x, y]; return; }
      var n = Math.max(1, Math.ceil(Math.hypot(x - cur[0], y - cur[1]) / 0.02));
      for (var i = 1; i <= n; i++) pts.push([cur[0] + (x - cur[0]) * i / n, cur[1] + (y - cur[1]) * i / n]);
      cur = [x, y];
    }
    stroke.forEach(function (c) {
      if (c[0] === "M") { cur = null; lineTo(c[1], c[2]); }
      else if (c[0] === "L") lineTo(c[1], c[2]);
      else {
        var n = Math.max(2, Math.ceil(Math.abs(c[6] - c[5]) / 3));
        for (var i = 0; i <= n; i++) {
          var a = (c[5] + (c[6] - c[5]) * i / n) * Math.PI / 180;
          lineTo(c[1] + c[3] * Math.cos(a), c[2] + c[4] * Math.sin(a));
        }
      }
    });
    return pts;
  }
  function lengths(pts) { var L = [0]; for (var i = 1; i < pts.length; i++) L.push(L[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])); return L; }
  function along(pts, L, d) {  // the point at distance d along a polyline
    var i = 1;
    while (i < pts.length - 1 && L[i] < d) i++;
    var f = L[i] > L[i - 1] ? (d - L[i - 1]) / (L[i] - L[i - 1]) : 0;
    f = Math.max(0, Math.min(1, f));
    return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f];
  }
  function thread(pts, L, d0, d1, offset) {  // P points from d0 to d1 along the stroke, shifted sideways by offset
    var out = [];
    for (var i = 0; i < P; i++) {
      var d = d0 + (d1 - d0) * i / (P - 1), p = along(pts, L, d), q = along(pts, L, Math.min(L[L.length - 1], d + 0.3)), o = along(pts, L, Math.max(0, d - 0.3));
      var tx = q[0] - o[0], ty = q[1] - o[1], tl = Math.hypot(tx, ty) || 1;
      out.push([p[0] - ty / tl * offset, p[1] + tx / tl * offset]);
    }
    return out;
  }

  // A word as N strings: each stroke gets threads in proportion to its length, in bands of up to three
  // parallel threads, so letters read as fine engraving. Laid out to fit inside the seal's ring.
  function spell(word) {
    var figures = /^[0-9]+$/.test(word), track = 0.26, x = 0, strokes = [];
    word.split("").forEach(function (ch, i) {
      var g = G[ch];
      if (!g) return;
      g[1].forEach(function (st) { strokes.push(dense(st).map(function (p) { return [p[0] + x, p[1]]; })); });
      x += g[0] + (i < word.length - 1 ? track : 0);
    });
    var s = Math.min(78 / Math.max(x, 0.1), figures ? 60 / 1.5 : 21), mid = figures ? 0.75 : 0.5;
    strokes = strokes.map(function (st) { return st.map(function (p) { return [C + (p[0] - x / 2) * s, C - (p[1] - mid) * s]; }); });
    var lens = strokes.map(function (st) { return lengths(st); });
    var total = lens.reduce(function (a, L) { return a + L[L.length - 1]; }, 0);
    var share = lens.map(function (L) { return N * L[L.length - 1] / total; });
    var count = share.map(function (v) { return Math.max(1, Math.floor(v)); });
    var left = N - count.reduce(function (a, b) { return a + b; }, 0);
    var order = share.map(function (v, i) { return i; }).sort(function (a, b) { return (share[b] - count[b]) - (share[a] - count[a]); });
    for (var j = 0; left > 0; j++, left--) count[order[j % order.length]]++;
    for (j = 0; left < 0; j++) { var k = order[order.length - 1 - (j % order.length)]; if (count[k] > 1) { count[k]--; left++; } }
    var out = [];
    strokes.forEach(function (st, si) {
      var L = lens[si], len = L[L.length - 1], t = count[si], bands = Math.ceil(t / 3), piece = len / bands;
      for (var b = 0; b < bands; b++) {
        var c = Math.floor(t / bands) + (b < t % bands ? 1 : 0);  // threads in this band, side by side
        var d0 = Math.max(0, (b - 0.12) * piece), d1 = Math.min(len, (b + 1.12) * piece);
        for (var q = 0; q < c; q++) out.push(thread(st, L, d0, d1, (q - (c - 1) / 2) * 0.75));
      }
    });
    return sortByX(out.slice(0, N));
  }

  // The seal itself as N strings: each lattice curve (as build.seal draws it) cut into four.
  function circle() {
    var out = [];
    [1, -1].forEach(function (sign) {
      for (var j = 0; j < M; j++) {
        var rot = sign * j * Math.PI / (M * K);
        for (var q = 0; q < 4; q++) {
          var s = [];
          for (var i = 0; i < P; i++) {
            var t = (q + i / (P - 1)) * Math.PI / 2, r = R0 + AMP * Math.sin(K * t);
            s.push([C + r * Math.cos(t + rot), C + r * Math.sin(t + rot)]);
          }
          out.push(s);
        }
      }
    });
    return sortByX(out);
  }
  function sortByX(list) { return list.sort(function (a, b) { return a[P >> 1][0] - b[P >> 1][0]; }); }

  function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function settle(t) { return 1 - Math.pow(1 - t, 5); }
  function rot(p, a) { var dx = p[0] - C, dy = p[1] - C, c = Math.cos(a), s = Math.sin(a); return [C + dx * c - dy * s, C + dx * s + dy * c]; }

  var ring = circle();
  var words = [spell(DAYS), spell("day"), spell("narrative")];
  // The timeline (ms): each move, then a pause to read. The last move winds back and slows to rest.
  var steps = [
    { from: ring, to: words[0], at: 350, dur: 1100, swirl: 0.6 },
    { from: words[0], to: words[1], at: 2250, dur: 950, swirl: 0.35 },
    { from: words[1], to: words[2], at: 3950, dur: 950, swirl: 0.35 },
    { from: words[2], to: ring, at: 6100, dur: 2600, swirl: 0, home: true }
  ];
  var END = 8700, SETTLE_AT = 6900;
  var playing = false, start = 0, ctx, size, ink;

  function draw(strings, text) {
    var dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr * size / 100, 0, 0, dpr * size / 100, 0, 0);
    ctx.clearRect(0, 0, 100, 100);
    ctx.strokeStyle = ink;
    ctx.globalAlpha = 0.62 + 0.24 * text;
    ctx.lineWidth = 0.3 + 0.16 * text;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    strings.forEach(function (s) {
      ctx.moveTo(s[0][0], s[0][1]);
      for (var i = 1; i < s.length - 1; i++) ctx.quadraticCurveTo(s[i][0], s[i][1], (s[i][0] + s[i + 1][0]) / 2, (s[i][1] + s[i + 1][1]) / 2);
      ctx.lineTo(s[s.length - 1][0], s[s.length - 1][1]);
    });
    ctx.stroke();
  }

  function frame(now) {
    var t = now - start, strings = null, text = 1;
    for (var k = steps.length - 1; k >= 0; k--) {
      var st = steps[k];
      if (t < st.at) continue;
      var u = Math.min(1, (t - st.at) / st.dur);
      strings = st.from.map(function (a, i) {
        var b = st.to[i], lag = 0.28 * i / (N - 1), v = Math.max(0, Math.min(1, (u - lag) / (1 - 0.28))), e = st.home ? settle(v) : ease(v);
        var spin = st.home ? 0.9 * Math.sin(Math.PI * settle(u)) : st.swirl * Math.sin(Math.PI * e) * (i % 2 ? 1 : -1);
        return a.map(function (p, j) { return rot([p[0] + (b[j][0] - p[0]) * e, p[1] + (b[j][1] - p[1]) * e], spin); });
      });
      text = k === 0 ? ease(u) : st.home ? 1 - settle(u) : 1;
      break;
    }
    if (!strings) { strings = ring; text = 0; }
    draw(strings, text);
    if (t >= SETTLE_AT) seal.classList.add("settling");
    if (t < END) { requestAnimationFrame(frame); return; }
    seal.classList.remove("playing", "settling");
    canvas.remove();
    playing = false;
  }

  function play() {
    if (playing) return;
    playing = true;
    size = seal.getBoundingClientRect().width;
    var dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    canvas.setAttribute("aria-hidden", "true");
    seal.insertBefore(canvas, seal.querySelector(".seal-cap"));
    ctx = canvas.getContext("2d");
    ink = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#1a1816";
    draw(ring, 0);
    seal.classList.add("playing");
    requestAnimationFrame(function (now) { start = now; frame(now); });
  }

  seal.classList.add("can-play");
  seal.addEventListener("click", play);
  setTimeout(play, 500);
})();
