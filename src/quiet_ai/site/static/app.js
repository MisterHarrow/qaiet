// Track highlight: optional overlay. Without JS the buttons stay hidden and every story shows.
(function () {
  var nav = document.querySelector(".filters");
  if (!nav) return;
  nav.hidden = false;
  var buttons = nav.querySelectorAll("button");
  var stories = document.querySelectorAll(".story");
  function apply(track) {
    buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.track === track)); });
    stories.forEach(function (s) { s.classList.toggle("match", s.dataset.track === track); });
    if (track) document.body.dataset.highlight = track; else delete document.body.dataset.highlight;
  }
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      apply(document.body.dataset.highlight === b.dataset.track ? null : b.dataset.track);
    });
  });
})();
