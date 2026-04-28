/**
 * Painel de registro em tempo real: consome eventos já tratados em sra_process_runtime.js (receive → SRALiveLog.onSse).
 */
(function () {
  "use strict";

  var MAX_LINES = 450;
  var bodyEl = null;
  var statusEl = null;
  var paused = false;

  function pad2(n) {
    return (n < 10 ? "0" : "") + n;
  }

  function nowClock() {
    var d = new Date();
    return (
      pad2(d.getHours()) +
      ":" +
      pad2(d.getMinutes()) +
      ":" +
      pad2(d.getSeconds())
    );
  }

  function esc(value) {
    var s = String(value == null ? "" : value);
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function trimLine(s, max) {
    var t = String(s || "");
    if (t.length <= max) return t;
    return t.slice(0, max - 1) + "…";
  }

  function appendHtml(html) {
    if (!bodyEl || paused) return;
    var row = document.createElement("div");
    row.className = "sra-live-log-line";
    row.innerHTML = html;
    bodyEl.appendChild(row);
    while (bodyEl.children.length > MAX_LINES) {
      bodyEl.removeChild(bodyEl.firstChild);
    }
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  function formatEvent(ev) {
    var ts = (ev.ts && String(ev.ts).slice(11, 19)) || nowClock();
    var kind = ev.kind || "—";
    var lvl = (ev.level || "info").toUpperCase();
    var title = trimLine(ev.title, 120);
    var msg = trimLine(ev.message, 2000);
    var d = ev.data || {};
    var extra = "";
    if (d.subtarefa && String(d.subtarefa).trim()) {
      extra += " · " + trimLine(d.subtarefa, 160);
    }
    if (d.tarefa && String(d.tarefa).trim() && kind !== "server_log") {
      extra = " [" + trimLine(d.tarefa, 80) + "]" + extra;
    }
    var lvlKey = esc(String(ev.level || "info").toLowerCase());
    var line =
      '<span class="sra-live-log-ts">' +
      esc(ts) +
      '</span> <span class="sra-live-log-kind">' +
      esc(kind) +
      '</span> <span class="sra-live-log-lvl sra-live-log-lvl--' +
      lvlKey +
      '">' +
      esc(lvl) +
      '</span> <span class="sra-live-log-title">' +
      esc(title) +
      "</span>";
    if (msg || extra) {
      var tailMsg = esc(extra + (msg ? (extra ? " — " : ": ") + msg : ""));
      line += '<span class="sra-live-log-msg">' + tailMsg + "</span>";
    }
    return line;
  }

  function onSse(ev) {
    if (!bodyEl) return;
    if (statusEl) {
      statusEl.textContent = paused ? "Em pausa" : "A receber…";
    }
    appendHtml(formatEvent(ev));
  }

  function wireToolbar() {
    bodyEl = document.getElementById("sra-live-log-body");
    statusEl = document.getElementById("sra-live-log-status");
    if (!bodyEl) return;
    var clr = document.getElementById("sra-live-log-clear");
    var pau = document.getElementById("sra-live-log-pause");
    if (clr && !clr.dataset.sraWired) {
      clr.dataset.sraWired = "1";
      clr.addEventListener("click", function () {
        bodyEl.innerHTML = "";
      });
    }
    if (pau && !pau.dataset.sraWired) {
      pau.dataset.sraWired = "1";
      pau.addEventListener("click", function () {
        paused = !paused;
        pau.textContent = paused ? "Retomar" : "Pausar";
        if (statusEl) statusEl.textContent = paused ? "Em pausa" : "A receber…";
      });
    }
  }

  function init() {
    wireToolbar();
  }

  window.SRALiveLog = {
    onSse: onSse,
    init: init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
