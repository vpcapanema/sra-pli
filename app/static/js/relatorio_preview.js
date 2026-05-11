(function () {
  var root = document.documentElement;
  var context =
    document.body && document.body.dataset.previewContext
      ? document.body.dataset.previewContext
      : "default";
  var label = document.querySelector('[data-sra-preview="zoom-label"]');
  var STORAGE_KEY = "sraPreviewZoom:" + context;
  var MIN = 0.4,
    MAX = 1.6,
    STEP = 0.1;
  function clamp(v) {
    return Math.max(MIN, Math.min(MAX, v));
  }
  function apply(z) {
    z = clamp(z);
    root.style.setProperty("--sra-preview-zoom", z.toFixed(2));
    if (label) label.textContent = Math.round(z * 100) + "%";
    try {
      localStorage.setItem(STORAGE_KEY, z.toFixed(2));
    } catch (e) {}
  }
  function currentZoom() {
    var v = parseFloat(root.style.getPropertyValue("--sra-preview-zoom")) || 1;
    return v;
  }
  function fitWidth() {
    // largura util disponivel (descontando padding do body)
    var avail = window.innerWidth - 80; // padding fixo para evitar getComputedStyle
    // 210mm em px: 1mm = 96/25.4 px
    var a4Px = (210 * 96) / 25.4;
    apply(avail / a4Px);
  }
  function paginatePreviewContent() {
    var rootEl = document.querySelector(".preview-root");
    var firstSheet = document.querySelector(
      '[data-sra-content-source="secoes"]',
    );
    var sourceBody = document.querySelector("[data-sra-paginate-source]");
    var tpl = document.getElementById("sra-preview-sheet-template");
    if (
      !rootEl ||
      !firstSheet ||
      !sourceBody ||
      !tpl ||
      sourceBody.dataset.paginated === "1"
    )
      return;
    sourceBody.dataset.paginated = "1";
    var nodes = Array.from(sourceBody.childNodes).filter(function (n) {
      return n.nodeType !== Node.TEXT_NODE || n.textContent.trim();
    });
    sourceBody.innerHTML = "";
    var pageNo = 4;
    function setPageNumber(sheet, n) {
      var target = sheet.querySelector(".sheet-ftr-right");
      if (target) target.textContent = String(n);
    }
    function newSheet() {
      var sheet = tpl.content.firstElementChild.cloneNode(true);
      setPageNumber(sheet, ++pageNo);
      rootEl.insertBefore(sheet, firstSheet.nextSibling);
      firstSheet = sheet;
      return sheet.querySelector(".sheet-body");
    }
    setPageNumber(firstSheet, pageNo);
    var body = sourceBody;
    nodes.forEach(function (node) {
      body.appendChild(node);
      if (
        body.scrollHeight > body.clientHeight + 1 &&
        body.childNodes.length > 1
      ) {
        body.removeChild(node);
        body = newSheet();
        body.appendChild(node);
      }
    });
    var assinaturaPage = document.querySelector("[data-sra-assinaturas-page]");
    if (assinaturaPage) assinaturaPage.textContent = String(pageNo + 1);
  }
  // Adicionar debounce para evitar execução excessiva
  var paginateTimeout;
  function schedulePaginate() {
    if (paginateTimeout) clearTimeout(paginateTimeout);
    paginateTimeout = setTimeout(function () {
      requestAnimationFrame(paginatePreviewContent);
    }, 100);
  }
  schedulePaginate();
  // Restaura ou define zoom inicial
  var saved = null;
  try {
    saved = parseFloat(localStorage.getItem(STORAGE_KEY));
  } catch (e) {}
  if (saved && !isNaN(saved)) {
    apply(saved);
  } else {
    // Primeira abertura: se viewport menor que A4, ajusta para caber
    var a4Px = (210 * 96) / 25.4;
    if (window.innerWidth < a4Px + 40) fitWidth();
    else apply(1);
  }
  // Reposiciona na ancora da secao apos aplicar o zoom
  function scrollToHash() {
    var hash = (location.hash || "").trim();
    if (!hash || hash.length < 2) return;
    var el = document.getElementById(hash.slice(1));
    if (!el) return;
    try {
      el.scrollIntoView({ block: "start", behavior: "auto" });
    } catch (e) {
      el.scrollIntoView();
    }
  }
  if (location.hash) {
    // Simplificar rAF aninhado
    setTimeout(function () {
      requestAnimationFrame(scrollToHash);
    }, 150);
  }
  window.addEventListener("hashchange", scrollToHash);
  document.querySelectorAll("[data-sra-preview]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var action = btn.getAttribute("data-sra-preview");
      if (action === "zoom-in") apply(currentZoom() + STEP);
      else if (action === "zoom-out") apply(currentZoom() - STEP);
      else if (action === "fit-width") fitWidth();
      else if (action === "fit-100") apply(1);
      else if (action === "print") window.print();
      else if (action === "load-preview") {
        var previewRoot = document.getElementById("preview-root");
        if (previewRoot) {
          previewRoot.setAttribute("data-preview-loaded", "true");
          var placeholder = document.getElementById("preview-placeholder");
          if (placeholder) placeholder.classList.add("hidden");
        }
      }
    });
  });
  // Atalhos de teclado: Ctrl + / - / 0
  document.addEventListener("keydown", function (e) {
    if (!(e.ctrlKey || e.metaKey)) return;
    if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      apply(currentZoom() + STEP);
    } else if (e.key === "-") {
      e.preventDefault();
      apply(currentZoom() - STEP);
    } else if (e.key === "0") {
      e.preventDefault();
      apply(1);
    }
  });
  // Reaplica fit-width quando a janela muda de tamanho com debounce
  var lastFitWidth = false;
  var resizeTimeout;
  document
    .querySelector('[data-sra-preview="fit-width"]')
    .addEventListener("click", function () {
      lastFitWidth = true;
    });
  document.querySelectorAll("[data-sra-preview]").forEach(function (btn) {
    if (btn.getAttribute("data-sra-preview") !== "fit-width") {
      btn.addEventListener("click", function () {
        lastFitWidth = false;
      });
    }
  });
  window.addEventListener("resize", function () {
    if (resizeTimeout) clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(function () {
      if (lastFitWidth) fitWidth();
    }, 150);
  });
})();
