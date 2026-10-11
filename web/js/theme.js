/* Light / dark. Sync script: sets data-theme before first paint, then adds a text toggle. */
(function () {
  var KEY = "vr-theme";
  var root = document.documentElement;
  var dark = window.matchMedia("(prefers-color-scheme: dark)");
  function saved() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function effective() { var t = root.getAttribute("data-theme"); return t || (dark.matches ? "dark" : "light"); }
  function announce() { window.dispatchEvent(new Event("themechange")); }
  var initial = saved();
  if (initial === "light" || initial === "dark") root.setAttribute("data-theme", initial);
  dark.addEventListener("change", function () { if (!root.getAttribute("data-theme")) announce(); });

  function build() {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theme-toggle";
    function label() { var next = effective() === "dark" ? "Light" : "Dark"; btn.textContent = next; btn.setAttribute("aria-label", "Switch to " + next.toLowerCase() + " theme"); }
    btn.addEventListener("click", function () {
      var next = effective() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
      label();
      announce();
    });
    window.addEventListener("themechange", label);
    label();
    var host = document.querySelector(".board-inner");
    if (host) host.appendChild(btn); else { btn.classList.add("floating"); document.body.appendChild(btn); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build); else build();
})();
