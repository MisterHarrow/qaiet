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
