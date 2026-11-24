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
