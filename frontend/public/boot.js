// If the app has not started after 12 seconds (slow or broken network),
// replace "Loading…" with a clear message and a retry button.
setTimeout(function () {
  if (window.__appStarted) return;
  var el = document.getElementById("boot");
  if (!el) return;
  el.textContent = "";
  var p = document.createElement("p");
  p.textContent = "The quiz did not load. Your connection may be slow.";
  var b = document.createElement("button");
  b.textContent = "Try again";
  b.addEventListener("click", function () { location.reload(); });
  el.appendChild(p);
  el.appendChild(b);
}, 12000);
