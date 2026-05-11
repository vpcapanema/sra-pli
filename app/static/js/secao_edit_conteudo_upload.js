// ---- Filtros de coluna: lista de valores dinâmica + toggle ----
(function () {
  window._tblFilters = {
    blocos: { indice: "", titulo: "", tipo: "", classe: "" },
    edit: { sec: "", "edit-tipo": "", "edit-classe": "" },
  };
  var COL_MAP = {
    indice: {
      tbl: ".blocos-table-wrap .blocos-table",
      col: 1,
      grp: "blocos",
      key: "indice",
    },
    titulo: {
      tbl: ".blocos-table-wrap .blocos-table",
      col: 2,
      grp: "blocos",
      key: "titulo",
    },
    tipo: {
      tbl: ".blocos-table-wrap .blocos-table",
      col: 3,
      grp: "blocos",
      key: "tipo",
    },
    classe: {
      tbl: ".blocos-table-wrap .blocos-table",
      col: 4,
      grp: "blocos",
      key: "classe",
    },
    sec: { tbl: ".edit-bloco-tabela", col: 0, grp: "edit", key: "sec" },
    "edit-tipo": {
      tbl: ".edit-bloco-tabela",
      col: 1,
      grp: "edit",
      key: "edit-tipo",
    },
    "edit-classe": {
      tbl: ".edit-bloco-tabela",
      col: 2,
      grp: "edit",
      key: "edit-classe",
    },
  };
  function getUniqueVals(tblSel, colIdx) {
    var tbl = document.querySelector(tblSel);
    if (!tbl) return [];
    var seen = {};
    tbl.querySelectorAll("tbody tr").forEach(function (row) {
      var cell = row.querySelectorAll("td")[colIdx];
      if (cell) {
        var v = cell.textContent.trim();
        if (v) seen[v] = true;
      }
    });
    return Object.keys(seen).sort();
  }
  function populateList(listEl, vals, activeVal) {
    listEl.innerHTML = "";
    [""].concat(vals).forEach(function (v) {
      var li = document.createElement("li");
      li.className = "th-filter-item" + (v === activeVal ? " active" : "");
      li.textContent = v === "" ? "(Todos)" : v;
      li.dataset.val = v;
      listEl.appendChild(li);
    });
  }
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".th-filter-btn");
    if (btn) {
      var col = btn.dataset.col;
      var drop = document.getElementById("th-drop-" + col);
      document
        .querySelectorAll(".th-filter-dropdown.open")
        .forEach(function (d) {
          if (d !== drop) d.classList.remove("open");
        });
      if (drop) {
        if (!drop.classList.contains("open")) {
          var cfg = COL_MAP[col];
          if (cfg) {
            var listEl = drop.querySelector(".th-filter-list");
            if (listEl)
              populateList(
                listEl,
                getUniqueVals(cfg.tbl, cfg.col),
                window._tblFilters[cfg.grp][cfg.key] || "",
              );
          }
          drop.classList.add("open");
        } else {
          drop.classList.remove("open");
        }
      }
      ev.stopPropagation();
      return;
    }
    var li = ev.target.closest(".th-filter-item");
    if (li) {
      var drop = li.closest(".th-filter-dropdown");
      if (!drop) return;
      var col = drop.id.replace("th-drop-", "");
      var cfg = COL_MAP[col];
      if (!cfg) return;
      window._tblFilters[cfg.grp][cfg.key] = li.dataset.val;
      li.closest(".th-filter-list")
        .querySelectorAll(".th-filter-item")
        .forEach(function (x) {
          x.classList.toggle("active", x.dataset.val === li.dataset.val);
        });
      drop.classList.remove("open");
      document.dispatchEvent(
        new CustomEvent("tbl-filter-change", { detail: { grp: cfg.grp } }),
      );
      ev.stopPropagation();
      return;
    }
    if (!ev.target.closest(".th-filter-dropdown")) {
      document
        .querySelectorAll(".th-filter-dropdown.open")
        .forEach(function (d) {
          d.classList.remove("open");
        });
    }
  });
})();

(function () {
  /* ======= BLOCOS-TABLE: filtro + paginação + collapse ======= */
  var ssHdr = document.getElementById("ss-blocos-hdr");
  var ssToggle = document.getElementById("ss-blocos-toggle");
  var ssBlocos = document.getElementById("ss-blocos");
  if (ssHdr && ssToggle && ssBlocos) {
    var sbBody = ssBlocos.querySelector(".sb2");
    ssHdr.addEventListener("click", function (ev) {
      if (ev.target.closest("input, select, button") && ev.target !== ssToggle)
        return;
      var open = ssToggle.getAttribute("aria-expanded") !== "false";
      ssToggle.setAttribute("aria-expanded", String(!open));
      ssToggle.classList.toggle("collapsed", open);
      if (sbBody) sbBody.style.display = open ? "none" : "";
    });
  }

  (function () {
    var PG = 10;
    var tbl = document.querySelector(".blocos-table-wrap .blocos-table");
    if (!tbl) return;
    var allRows = Array.from(tbl.querySelectorAll("tbody tr"));
    var pagInfo = document.getElementById("blocos-pag-info");
    var pagBtns = document.getElementById("blocos-pag-btns");
    var curPage = 1;
    function getVisible() {
      var f = window._tblFilters.blocos;
      var vi = f.indice.toLowerCase();
      var vt = f.titulo.toLowerCase();
      var tp = f.tipo.toLowerCase();
      var cl = f.classe.toLowerCase();
      return allRows.filter(function (row) {
        var cells = row.querySelectorAll("td");
        var indice = cells[1] ? cells[1].textContent.trim().toLowerCase() : "";
        var titulo = cells[2] ? cells[2].textContent.trim().toLowerCase() : "";
        var tipo = cells[3] ? cells[3].textContent.trim().toLowerCase() : "";
        var classe = cells[4] ? cells[4].textContent.trim().toLowerCase() : "";
        return (
          (!vi || indice.includes(vi)) &&
          (!vt || titulo.includes(vt)) &&
          (!tp || tipo.includes(tp)) &&
          (!cl || classe.includes(cl))
        );
      });
    }
    function renderPage() {
      var visible = getVisible();
      var total = visible.length;
      var pages = Math.max(1, Math.ceil(total / PG));
      if (curPage > pages) curPage = 1;
      allRows.forEach(function (r) {
        r.style.display = "none";
      });
      var start = (curPage - 1) * PG;
      visible.slice(start, start + PG).forEach(function (r) {
        r.style.display = "";
      });
      if (pagInfo) {
        var showing = Math.min(PG, total - start);
        pagInfo.textContent =
          showing + "/" + total + " reg · " + curPage + "/" + pages + " pág";
      }
      if (pagBtns) {
        pagBtns.innerHTML = "";
        for (var p = 1; p <= pages; p++) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "blocos-pag-btn" + (p === curPage ? " active" : "");
          btn.textContent = p;
          btn.dataset.p = p;
          pagBtns.appendChild(btn);
        }
      }
    }
    document.addEventListener("tbl-filter-change", function (ev) {
      if (ev.detail.grp === "blocos") {
        curPage = 1;
        renderPage();
      }
    });
    if (pagBtns)
      pagBtns.addEventListener("click", function (ev) {
        var btn = ev.target.closest(".blocos-pag-btn");
        if (btn) {
          curPage = Number(btn.dataset.p);
          renderPage();
        }
      });
    renderPage();
  })();

  /* ======= EDIT-BLOCO-TABELA: filtro + paginação ======= */
  (function () {
    var editPG = 10;
    var editPage = 1;
    var editAllRows = [];
    var pagInfo = document.getElementById("edit-blocos-pag-info");
    var pagBtns = document.getElementById("edit-blocos-pag-btns");
    var tblBody = document.getElementById("edit-bloco-tabela-body");
    if (!tblBody) return;
    function refresh() {
      editAllRows = Array.from(tblBody.querySelectorAll("tr"));
      renderEditPage();
    }
    function getEditVisible() {
      var f = window._tblFilters.edit;
      var vs = f.sec.toLowerCase();
      var vt = f["edit-tipo"].toLowerCase();
      var vc = f["edit-classe"].toLowerCase();
      return editAllRows.filter(function (row) {
        var cells = row.querySelectorAll("td");
        var sec = cells[0] ? cells[0].textContent.trim().toLowerCase() : "";
        var tipo = cells[1] ? cells[1].textContent.trim().toLowerCase() : "";
        var classe = cells[2] ? cells[2].textContent.trim().toLowerCase() : "";
        return (
          (!vs || sec.includes(vs)) &&
          (!vt || tipo.includes(vt)) &&
          (!vc || classe.includes(vc))
        );
      });
    }
    function renderEditPage() {
      var visible = getEditVisible();
      var total = visible.length;
      var pages = Math.max(1, Math.ceil(total / editPG));
      if (editPage > pages) editPage = 1;
      editAllRows.forEach(function (r) {
        r.style.display = "none";
      });
      var start = (editPage - 1) * editPG;
      visible.slice(start, start + editPG).forEach(function (r) {
        r.style.display = "";
      });
      if (pagInfo) {
        var editShowing = Math.min(editPG, total - start);
        pagInfo.textContent =
          editShowing +
          "/" +
          total +
          " reg · " +
          editPage +
          "/" +
          pages +
          " pág";
      }
      if (pagBtns) {
        pagBtns.innerHTML = "";
        for (var p = 1; p <= pages; p++) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "blocos-pag-btn" + (p === editPage ? " active" : "");
          btn.textContent = p;
          btn.dataset.p = p;
          pagBtns.appendChild(btn);
        }
      }
    }
    document.addEventListener("tbl-filter-change", function (ev) {
      if (ev.detail.grp === "edit") {
        editPage = 1;
        renderEditPage();
      }
    });
    if (pagBtns)
      pagBtns.addEventListener("click", function (ev) {
        var btn = ev.target.closest(".blocos-pag-btn");
        if (btn) {
          editPage = Number(btn.dataset.p);
          renderEditPage();
        }
      });
    if (typeof MutationObserver !== "undefined") {
      new MutationObserver(refresh).observe(tblBody, { childList: true });
    }
  })();
})();

(function () {
  var node = document.getElementById("upload-coord-expect");
  var secSel = document.getElementById("upload-sec-selector");
  var respSel = document.getElementById("sel-sec-responsavel");
  var stSel = document.getElementById("sel-sec-status");
  var wSec = document.getElementById("ucr-wrap-sec");
  var wResp = document.getElementById("ucr-wrap-resp");
  var wSt = document.getElementById("ucr-wrap-st");
  var btn = document.getElementById("upload-coord-confirm");
  if (
    !node ||
    !secSel ||
    !respSel ||
    !stSel ||
    !wSec ||
    !wResp ||
    !wSt ||
    !btn
  ) {
    return;
  }
  var expect;
  try {
    expect = JSON.parse(node.textContent || "{}");
  } catch (e) {
    return;
  }

  function numVal(s) {
    var n = parseInt(String(s || "").trim(), 10);
    return Number.isFinite(n) ? n : NaN;
  }

  function respOk() {
    var raw = String(respSel.value || "").trim();
    if (expect.userRole === "autor") {
      return raw !== "" && numVal(raw) === expect.userId;
    }
    if (
      expect.expectedResponsavelId === null ||
      expect.expectedResponsavelId === undefined
    ) {
      return raw === "";
    }
    return numVal(raw) === Number(expect.expectedResponsavelId);
  }

  function statusOk() {
    return String(stSel.value || "") === String(expect.expectedStatus || "");
  }

  function paint() {
    var sOk = numVal(secSel.value) === expect.pageSecId;
    var rOk = respOk();
    var tOk = statusOk();
    wSec.classList.toggle("ucr-field-ok", sOk);
    wSec.classList.toggle("ucr-field-bad", !sOk);
    wResp.classList.toggle("ucr-field-ok", rOk);
    wResp.classList.toggle("ucr-field-bad", !rOk);
    wSt.classList.toggle("ucr-field-ok", tOk);
    wSt.classList.toggle("ucr-field-bad", !tOk);
  }

  function wire(el) {
    if (el) {
      el.addEventListener("change", paint);
      el.addEventListener("input", paint);
    }
  }
  wire(respSel);
  wire(stSel);
  secSel.addEventListener("change", function () {
    var id = String(secSel.value || "").trim();
    if (!id) {
      paint();
      return;
    }
    if (numVal(id) !== expect.pageSecId) {
      window.location.href =
        "/relatorios/" + expect.relId + "/secoes/" + id + "/upload-conteudo";
      return;
    }
    paint();
  });
  paint();

  async function errMsg(resp) {
    var ct = (resp.headers.get("content-type") || "").toLowerCase();
    if (ct.indexOf("json") >= 0) {
      try {
        var j = await resp.json();
        if (j && j.detail) {
          return typeof j.detail === "string"
            ? j.detail
            : JSON.stringify(j.detail);
        }
      } catch (e2) {
        /* ignore */
      }
    }
    return "Pedido recusado (" + resp.status + ").";
  }

  btn.addEventListener("click", async function () {
    if (btn.disabled) {
      return;
    }
    var secId = String(expect.pageSecId);
    var secTemUpload =
      respSel && respSel.getAttribute("data-sec-tem-upload") === "1";
    if (secTemUpload && !String(respSel.value || "").trim()) {
      window.alert(
        "Selecione um responsável: esta seção já tem conteúdo inserido pelo autor.",
      );
      return;
    }
    btn.disabled = true;
    try {
      var fdResp = new FormData();
      fdResp.append("responsavel_id", String(respSel.value || "").trim());
      fdResp.append("retorno", "upload");
      var r1 = await fetch(
        "/relatorios/" + expect.relId + "/secoes/" + secId + "/responsavel",
        {
          method: "POST",
          body: fdResp,
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        },
      );
      if (!r1.ok) {
        throw new Error(await errMsg(r1));
      }
      var fdSt = new FormData();
      fdSt.append("status", String(stSel.value || "").trim());
      fdSt.append("retorno", "upload");
      var r2 = await fetch(
        "/relatorios/" + expect.relId + "/secoes/" + secId + "/status",
        {
          method: "POST",
          body: fdSt,
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        },
      );
      if (!r2.ok) {
        throw new Error(await errMsg(r2));
      }
      window.location.href =
        "/relatorios/" + expect.relId + "/secoes/" + secId + "/upload-conteudo";
    } catch (err) {
      window.alert(err.message || "Não foi possível confirmar.");
    } finally {
      btn.disabled = false;
    }
  });
})();

(function () {
  var inner = document.getElementById("preview-zoom-inner");
  var frame = document.getElementById("preview-frame");
  var reloadBtn = document.getElementById("btn-preview-reload");
  var zIn = document.getElementById("preview-zoom-in");
  var zOut = document.getElementById("preview-zoom-out");
  var secSelector = document.getElementById("upload-sec-selector");
  if (!inner || !frame) return;
  var scale = 1;
  var minS = 0.5;
  var maxS = 2;
  var step = 0.1;

  function applyZoom() {
    scale = Math.round(Math.max(minS, Math.min(maxS, scale)) * 100) / 100;
    var useZoom =
      typeof CSS !== "undefined" && CSS.supports && CSS.supports("zoom", "1");
    if (useZoom) {
      inner.style.zoom = String(scale);
      inner.style.transform = "";
      inner.style.width = "";
    } else {
      inner.style.zoom = "";
      inner.style.transform = "scale(" + scale + ")";
      inner.style.transformOrigin = "top left";
      inner.style.width = 100 / scale + "%";
    }
  }

  function getSubtreeIds(secaoId) {
    if (!secSelector) return [secaoId];
    var selectedOpt = secSelector.querySelector('option[value="' + secaoId + '"]');
    var selectedNum = selectedOpt ? (selectedOpt.dataset.numero || "") : "";
    if (!selectedNum) return [secaoId];
    var ids = [];
    secSelector.querySelectorAll("option").forEach(function (opt) {
      var num = opt.dataset.numero || "";
      if (num === selectedNum || num.indexOf(selectedNum + ".") === 0) {
        ids.push(opt.value);
      }
    });
    return ids.length ? ids : [secaoId];
  }

  function buildPreviewUrl(secaoId, bustCache) {
    var base = (frame.dataset.src || "").split("#")[0];
    var url = new URL(base, window.location.origin);
    url.searchParams.delete("secao_ids");
    getSubtreeIds(secaoId).forEach(function (id) {
      url.searchParams.append("secao_ids", id);
    });
    if (bustCache) url.searchParams.set("t", Date.now());
    var selectedOpt = secSelector ? secSelector.querySelector('option[value="' + secaoId + '"]') : null;
    var num = selectedOpt ? (selectedOpt.dataset.numero || "") : "";
    var anchor = num ? "#sec-" + num.replace(/\./g, "-") : "";
    return url.toString() + anchor;
  }

  function updatePreviewForSecao(secaoId) {
    frame.src = buildPreviewUrl(secaoId, false);
  }

  if (secSelector) {
    secSelector.addEventListener("change", function () {
      updatePreviewForSecao(secSelector.value);
    });
  }

  frame.addEventListener("load", function () {
    applyZoom();
  });

  if (reloadBtn && frame.dataset.src) {
    reloadBtn.addEventListener("click", function () {
      var secId = secSelector ? secSelector.value : "";
      frame.src = buildPreviewUrl(secId, true);
    });
  }

  // Preview de blocos individuais
  var previewBtns = document.querySelectorAll(".preview-bloco-btn");
  if (previewBtns.length > 0) {
    previewBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var blocoId = btn.dataset.blocoId;
        if (!blocoId) return;
        var base = frame.dataset.src;
        var url = new URL(base, window.location.origin);
        url.searchParams.set("bloco_ids", blocoId);
        url.searchParams.set("t", Date.now());
        frame.src = url.toString();
      });
    });
  }
  if (zIn)
    zIn.addEventListener("click", function () {
      scale += step;
      applyZoom();
    });
  if (zOut)
    zOut.addEventListener("click", function () {
      scale -= step;
      applyZoom();
    });

  // Ajustar zoom automaticamente ao carregar
  if (frame.complete) {
    applyZoom();
  }
})();

// Botões de verificação de seção
(function () {
  var btnVerificarIndices = document.getElementById(
    "btn-verificar-indices-sec",
  );
  var btnVerificarReferencias = document.getElementById(
    "btn-verificar-referencias-sec",
  );
  var secSelector = document.getElementById("upload-sec-selector");

  function openVerificacaoModal(title) {
    var modal = document.getElementById("modal-verificacao-sec");
    var titleEl = document.getElementById("verificacao-sec-title");
    var loading = document.getElementById("verificacao-sec-loading");
    var results = document.getElementById("verificacao-sec-results");
    var empty = document.getElementById("verificacao-sec-empty");
    var summary = document.getElementById("verificacao-sec-summary");
    var list = document.getElementById("verificacao-sec-list");

    titleEl.textContent = title;
    loading.style.display = "";
    results.style.display = "none";
    empty.style.display = "none";
    modal.style.display = "";

    return { modal, loading, results, empty, summary, list };
  }

  function verificarIndicesSec() {
    var secId = secSelector ? secSelector.value : "";
    if (!secId) return;

    var { modal, loading, results, empty, summary, list } =
      openVerificacaoModal("Verificar Índices da Seção");

    fetch("/relatorios/" + REL_ID + "/secoes/" + secId + "/verificar-indices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        loading.style.display = "none";
        if (data.ok) {
          if (data.total === 0) {
            empty.style.display = "";
          } else {
            results.style.display = "";
            summary.textContent = "Encontrados " + data.total + " problema(s)";
            list.innerHTML = "";
            data.problemas.forEach(function (p) {
              var item = document.createElement("div");
              item.className =
                "rev-verificacao-item rev-verificacao-item--" + p.tipo;
              item.innerHTML =
                '<div class="rev-verificacao-item__title">' +
                p.titulo +
                "</div>" +
                '<div class="rev-verificacao-item__desc">' +
                p.desc +
                "</div>";
              list.appendChild(item);
            });
          }
        }
      })
      .catch(function (err) {
        loading.style.display = "none";
        summary.textContent = "Erro ao verificar: " + err.message;
        results.style.display = "";
      });
  }

  function verificarReferenciasSec() {
    var secId = secSelector ? secSelector.value : "";
    if (!secId) return;

    var { modal, loading, results, empty, summary, list } =
      openVerificacaoModal("Verificar Referências da Seção");

    fetch(
      "/relatorios/" + REL_ID + "/secoes/" + secId + "/verificar-referencias",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      },
    )
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        loading.style.display = "none";
        if (data.ok) {
          if (data.total === 0) {
            empty.style.display = "";
          } else {
            results.style.display = "";
            summary.textContent = "Encontrados " + data.total + " problema(s)";
            list.innerHTML = "";
            data.problemas.forEach(function (p) {
              var item = document.createElement("div");
              item.className =
                "rev-verificacao-item rev-verificacao-item--" + p.tipo;
              item.innerHTML =
                '<div class="rev-verificacao-item__title">' +
                p.titulo +
                "</div>" +
                '<div class="rev-verificacao-item__desc">' +
                p.desc +
                "</div>";
              list.appendChild(item);
            });
          }
        }
      })
      .catch(function (err) {
        loading.style.display = "none";
        summary.textContent = "Erro ao verificar: " + err.message;
        results.style.display = "";
      });
  }

  if (btnVerificarIndices) {
    btnVerificarIndices.addEventListener("click", verificarIndicesSec);
  }

  if (btnVerificarReferencias) {
    btnVerificarReferencias.addEventListener("click", verificarReferenciasSec);
  }

  // Fechar modal ao clicar no overlay
  document.addEventListener("click", function (ev) {
    var overlay = ev.target.closest(".rev-modal__overlay");
    if (overlay) {
      var modal = overlay.closest(".rev-modal");
      if (modal) modal.style.display = "none";
    }
    var closeBtn = ev.target.closest(".rev-modal__close");
    if (closeBtn) {
      var modal = closeBtn.closest(".rev-modal");
      if (modal) modal.style.display = "none";
    }
    var actionBtn = ev.target.closest('[data-action="close-modal"]');
    if (actionBtn) {
      var modal = actionBtn.closest(".rev-modal");
      if (modal) modal.style.display = "none";
    }
  });
})();

(function () {
  const frame = document.getElementById("preview-frame");
  const list = document.getElementById("import-list");
  if (!frame || !list) return;

  let rafPending = false;
  let suppressUntil = 0;
  let lastAnchor = "";

  function getFrameDoc() {
    try {
      return (
        frame.contentDocument ||
        (frame.contentWindow && frame.contentWindow.document) ||
        null
      );
    } catch (err) {
      return null;
    }
  }

  function anchorFromNumero(numero) {
    const n = String(numero == null ? "" : numero).trim();
    if (!n) return "";
    return "sec-" + n.replace(/\./g, "-");
  }

  function numeroSecaoFromEl(el) {
    if (!el) return "";
    const section = el.closest(".import-secao");
    if (!section) return "";
    const numInput = section.querySelector(".import-secao-num");
    const fromInput = numInput ? String(numInput.value || "").trim() : "";
    if (fromInput) return fromInput;
    const key = section.getAttribute("data-key") || "";
    if (!key || key === "__atual__") return "";
    return key;
  }

  function scrollFrameTo(anchorId, behavior) {
    if (!anchorId) return;
    const doc = getFrameDoc();
    if (!doc) return;
    const target = doc.getElementById(anchorId);
    if (!target) return;
    try {
      target.scrollIntoView({
        behavior: behavior || "smooth",
        block: "start",
        inline: "nearest",
      });
    } catch (err) {
      target.scrollIntoView();
    }
  }

  function secaoMaisVisivelNoImportList() {
    const secs = list.querySelectorAll(".import-secao");
    if (!secs.length) return "";
    const listRect = list.getBoundingClientRect();
    const refY = listRect.top + 12;
    let melhor = null;
    let melhorDist = Infinity;
    secs.forEach((sec) => {
      const hdr = sec.querySelector(".import-secao-hdr");
      const ref = hdr || sec;
      const r = ref.getBoundingClientRect();
      if (r.bottom < listRect.top - 4) return;
      if (r.top > listRect.bottom + 4) return;
      const dist = Math.abs(r.top - refY);
      if (dist < melhorDist) {
        melhorDist = dist;
        melhor = sec;
      }
    });
    if (!melhor) return "";
    const numInput = melhor.querySelector(".import-secao-num");
    const fromInput = numInput ? String(numInput.value || "").trim() : "";
    if (fromInput) return fromInput;
    const key = melhor.getAttribute("data-key") || "";
    if (!key || key === "__atual__") return "";
    return key;
  }

  function syncFromScroll() {
    if (Date.now() < suppressUntil) return;
    const numero = secaoMaisVisivelNoImportList();
    const anchor = anchorFromNumero(numero);
    if (!anchor || anchor === lastAnchor) return;
    lastAnchor = anchor;
    scrollFrameTo(anchor, "smooth");
  }

  function onScroll() {
    if (rafPending) return;
    rafPending = true;
    window.requestAnimationFrame(() => {
      rafPending = false;
      syncFromScroll();
    });
  }

  list.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("scroll", onScroll, {
    passive: true,
    capture: true,
  });

  list.addEventListener(
    "click",
    (ev) => {
      const t = ev.target;
      if (!t) return;
      const ignorar = t.closest(
        "input, select, textarea, .import-secao-toggle, .import-secao-bulk-btn, .import-tx-tool, .import-raw-close, .import-raw, .seg-chip[data-seg-toggle]",
      );
      if (ignorar) return;
      const card = t.closest(".import-card");
      const hdr = t.closest(".import-secao-hdr");
      const ref = card || hdr;
      if (!ref) return;
      const numero = numeroSecaoFromEl(ref);
      const anchor = anchorFromNumero(numero);
      if (!anchor) return;
      suppressUntil = Date.now() + 600;
      lastAnchor = anchor;
      scrollFrameTo(anchor, "smooth");
    },
    true,
  );

  frame.addEventListener("load", () => {
    lastAnchor = "";
    setTimeout(syncFromScroll, 120);
  });

  setTimeout(syncFromScroll, 300);
})();

const SECAO_EDIT_DATA = document.currentScript
  ? document.currentScript.dataset
  : {};
function parseJsonValue(raw, fallback) {
  if (raw === undefined || raw === "") return fallback;
  try {
    return JSON.parse(raw);
  } catch (err) {
    return fallback;
  }
}
function readSecaoEditData(name, fallback) {
  return parseJsonValue(SECAO_EDIT_DATA[name], fallback);
}

(function () {
  const form = document.getElementById("form-add-bloco");
  if (!form) return;
  const tipoIn = document.getElementById("add-bloco-tipo");
  const tituloHidden = document.getElementById("add-bloco-titulo");
  const ta = document.getElementById("add-bloco-conteudo");
  const quillWrap = document.getElementById("add-bloco-quill");
  let editTabBtn = null;
  const relId = readSecaoEditData("relId", 0);
  const secNumero = String(readSecaoEditData("secNumero", ""));
  const secTop = secNumero.split(".")[0];
  const figBase = readSecaoEditData("figBase", 0);
  const tabBase = readSecaoEditData("tabBase", 0);
  const figGlobalBase = readSecaoEditData("figGlobalBase", 0);
  const tabGlobalBase = readSecaoEditData("tabGlobalBase", 0);
  function _countTaFig() {
    return (ta.value.match(/\[\[FIGURA:/g) || []).length;
  }
  function _countTaTab() {
    const op = (ta.value.match(/\[\[TABELA(?::|\||\]\])/g) || []).length;
    const cl = (ta.value.match(/\[\[\/TABELA\]\]/g) || []).length;
    return cl;
  }
  function nextFigIdx(estilo) {
    const n = (estilo === "C" ? figGlobalBase : figBase) + _countTaFig() + 1;
    return estilo === "C" ? String(n) : secTop + "." + n;
  }
  function nextTabIdx(estilo) {
    const n = (estilo === "C" ? tabGlobalBase : tabBase) + _countTaTab() + 1;
    return estilo === "C" ? String(n) : secTop + "." + n;
  }
  function _figEst() {
    const s = document.getElementById("fig-est");
    return s ? s.value : "R";
  }
  function _figPos() {
    const s = document.getElementById("fig-pos");
    return s ? s.value : "I";
  }
  function _tabEst() {
    const s = document.getElementById("tab-est");
    return s ? s.value : "R";
  }
  function _tabPos() {
    const s = document.getElementById("tab-pos");
    return s ? s.value : "S";
  }
  function _atualizaExemplos() {
    const fr = document.getElementById("fig-opt-R");
    if (fr)
      fr.textContent =
        "Por seção (Ex: FIGURA " +
        (secTop + "." + (figBase + _countTaFig() + 1)) +
        ")";
    const fc = document.getElementById("fig-opt-C");
    if (fc)
      fc.textContent =
        "Sequencial (Ex: FIGURA " + (figGlobalBase + _countTaFig() + 1) + ")";
    const tr = document.getElementById("tab-opt-R");
    if (tr)
      tr.textContent =
        "Por seção (Ex: TABELA " +
        (secTop + "." + (tabBase + _countTaTab() + 1)) +
        ")";
    const tc = document.getElementById("tab-opt-C");
    if (tc)
      tc.textContent =
        "Sequencial (Ex: TABELA " + (tabGlobalBase + _countTaTab() + 1) + ")";
  }
  window.atualizaExemplosBloco = _atualizaExemplos;
  const RICH_MARK = "<!--SRA_RICH-->\n";
  function syncQuillToTextarea() {
    const q = window._sraQuill;
    if (!q || !ta) return;
    let html = "";
    if (typeof q.getSemanticHTML === "function") {
      html = q.getSemanticHTML();
    } else {
      html = q.root.innerHTML;
    }
    ta.value = RICH_MARK + html;
  }
  window.syncSraQuillToTa = syncQuillToTextarea;
  function loadQuillContent(raw) {
    const q = window._sraQuill;
    if (!q) {
      ta.value = raw || "";
      return;
    }
    const s = raw || "";
    if (s.startsWith("<!--SRA_RICH-->")) {
      const nl = s.indexOf("\n");
      const html = nl === -1 ? "" : s.slice(nl + 1);
      try {
        const delta = q.clipboard.convert({ html: html || "<p><br></p>" });
        q.setContents(delta, "silent");
      } catch (e1) {
        q.setText(html.replace(/<[^>]+>/g, ""));
      }
    } else {
      q.setContents([], "silent");
      q.setText(s);
    }
    syncQuillToTextarea();
  }
  window.loadSraQuillContent = loadQuillContent;
  if (typeof Quill !== "undefined" && quillWrap) {
    window._sraQuill = new Quill("#add-bloco-quill", {
      theme: "snow",
      modules: {
        toolbar: [
          [{ header: [2, 3, 4, 5, 6, false] }],
          ["bold", "italic", "underline", "strike"],
          ["blockquote"],
          [{ list: "ordered" }, { list: "bullet" }],
          [{ script: "sub" }, { script: "super" }],
          [{ indent: "-1" }, { indent: "+1" }],
          [{ align: [] }],
          ["link", "image"],
          ["clean"],
        ],
      },
    });
    window._sraQuill.on("text-change", () => {
      syncQuillToTextarea();
      _atualizaExemplos();
      if (typeof updateStatus === "function") updateStatus();
    });
    loadQuillContent("");
  } else if (ta) {
    ta.classList.remove("is-offscreen");
    ta.rows = 14;
    ta.removeAttribute("aria-hidden");
    ta.removeAttribute("tabindex");
    ta.placeholder =
      "Conteúdo do bloco. Carregue com rede para o editor Quill (formatado).";
  }
  form.addEventListener("submit", () => {
    syncQuillToTextarea();
  });
  function syncTitulo() {}

  let lastCursor = { start: 0, end: 0 };
  if (!window._sraQuill) {
    ta.addEventListener("blur", () => {
      lastCursor = { start: ta.selectionStart, end: ta.selectionEnd };
    });
    ta.addEventListener("keyup", () => {
      lastCursor = { start: ta.selectionStart, end: ta.selectionEnd };
    });
    ta.addEventListener("mouseup", () => {
      lastCursor = { start: ta.selectionStart, end: ta.selectionEnd };
    });
  }

  function insertText(text, opts) {
    opts = opts || {};
    const q = window._sraQuill;
    if (q) {
      let range = q.getSelection(true);
      let idx = range ? range.index : Math.max(0, q.getLength() - 1);
      if (opts.blockLine && idx > 0) {
        q.insertText(idx, "\n", "user");
        idx += 1;
      }
      q.insertText(idx, text, "user");
      q.setSelection(idx + text.length, 0, "silent");
      syncQuillToTextarea();
      _atualizaExemplos();
      return;
    }
    const pos =
      document.activeElement === ta
        ? { start: ta.selectionStart, end: ta.selectionEnd }
        : lastCursor;
    let before = ta.value.slice(0, pos.start);
    let after = ta.value.slice(pos.end);
    if (opts.blockLine) {
      if (before.length && !before.endsWith("\n")) before += "\n";
      if (after.length && !after.startsWith("\n")) text = text + "\n";
    }
    ta.value = before + text + after;
    const newPos = before.length + text.length;
    ta.focus();
    ta.selectionStart = ta.selectionEnd = newPos;
    lastCursor = { start: newPos, end: newPos };
  }

  function insertAtCursor(prefix, perLine) {
    const q = window._sraQuill;
    if (q) {
      const range = q.getSelection(true);
      const start = range ? range.index : 0;
      const end = range ? range.index + range.length : start;
      const sel = q.getText(start, end - start);
      let inserted;
      if (perLine && sel) {
        inserted = sel
          .split("\n")
          .map((l) => (l ? prefix + l : l))
          .join("\n");
      } else {
        inserted = prefix + sel;
      }
      q.deleteText(start, end - start, "user");
      q.insertText(start, inserted, "user");
      q.setSelection(start + inserted.length, 0, "silent");
      syncQuillToTextarea();
      _atualizaExemplos();
      return;
    }
    const start = ta.selectionStart,
      end = ta.selectionEnd;
    const before = ta.value.slice(0, start),
      sel = ta.value.slice(start, end),
      after = ta.value.slice(end);
    let inserted;
    if (perLine && sel) {
      inserted = sel
        .split("\n")
        .map((l) => (l ? prefix + l : l))
        .join("\n");
    } else {
      inserted = prefix + sel;
    }
    ta.value = before + inserted + after;
    ta.focus();
    ta.selectionStart = start + prefix.length;
    ta.selectionEnd = start + inserted.length;
  }
  function wrapMarkdown(before, after) {
    const q = window._sraQuill;
    if (q) {
      const range = q.getSelection(true);
      if (!range || range.length === 0) {
        if (before === "**") q.format("bold", true);
        if (before === "_") q.format("italic", true);
        return;
      }
      if (before === "**")
        q.formatText(range.index, range.length, "bold", true);
      else if (before === "_")
        q.formatText(range.index, range.length, "italic", true);
      syncQuillToTextarea();
      return;
    }
    const endMark = after === undefined || after === null ? before : after;
    const start = ta.selectionStart,
      end = ta.selectionEnd;
    const sel = ta.value.slice(start, end);
    const ins = before + sel + endMark;
    ta.value = ta.value.slice(0, start) + ins + ta.value.slice(end);
    ta.focus();
    ta.selectionStart = start + before.length;
    ta.selectionEnd = start + before.length + sel.length;
  }
  document.querySelectorAll(".bloco-toolbar button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const act = btn.dataset.act;
      if (act === "titulo") {
        if (window._sraQuill) window._sraQuill.format("header", 2);
        else insertAtCursor("# ");
        tipoIn.value = "texto";
      } else if (act === "subtitulo") {
        if (window._sraQuill) window._sraQuill.format("header", 3);
        else insertAtCursor("## ");
        tipoIn.value = "texto";
      } else if (act === "paragrafo") {
        if (window._sraQuill) window._sraQuill.format("header", false);
        tipoIn.value = "texto";
      } else if (act === "lista") {
        tipoIn.value = "lista";
        if (window._sraQuill) window._sraQuill.format("list", "bullet");
        else insertAtCursor("- ", true);
      } else if (act === "bullet") {
        if (window._sraQuill) window._sraQuill.format("list", "bullet");
        else insertAtCursor("- ", true);
      } else if (act === "wrap-bold") {
        wrapMarkdown("**", "**");
        tipoIn.value = "texto";
      } else if (act === "wrap-italic") {
        wrapMarkdown("_", "_");
        tipoIn.value = "texto";
      }
    });
  });

  const figSel = document.getElementById("ins-fig-sel");
  const figPrev = document.getElementById("ins-fig-preview");
  const figImg = document.getElementById("ins-fig-img");
  const figLeg = document.getElementById("ins-fig-leg");
  const figBtn = document.getElementById("ins-fig-btn");
  figSel.addEventListener("change", () => {
    if (figSel.value) {
      figImg.src = "/figuras/" + figSel.value;
      figPrev.classList.remove("is-hidden");
    } else {
      figPrev.classList.add("is-hidden");
      figImg.removeAttribute("src");
    }
  });
  figBtn.addEventListener("click", () => {
    if (!figSel.value) {
      alert("Selecione uma figura ou faça upload primeiro.");
      return;
    }
    const leg = (figLeg.value || "").trim().replace(/\|/g, "/");
    if (!leg) {
      alert("Informe a legenda da figura antes de inserir.");
      figLeg.focus();
      return;
    }
    const est = _figEst();
    const pos = _figPos();
    const idx = nextFigIdx(est);
    const marker =
      "[[FIGURA:" + idx + "|" + figSel.value + "|" + pos + "|" + leg + "]]";
    insertText(marker, { blockLine: true });
    figLeg.value = "";
    _atualizaExemplos();
  });

  const tabRows = document.getElementById("ins-tab-rows");
  const tabCols = document.getElementById("ins-tab-cols");
  const tabLeg = document.getElementById("ins-tab-leg");
  const tabBtn = document.getElementById("ins-tab-btn");
  editTabBtn = document.getElementById("edit-tab-btn");
  tabBtn.addEventListener("click", () => {
    const r = Math.max(1, Math.min(50, parseInt(tabRows.value, 10) || 1));
    const c = Math.max(1, Math.min(12, parseInt(tabCols.value, 10) || 1));
    const leg = (tabLeg.value || "").trim();
    if (!leg) {
      alert("Informe a legenda da tabela antes de criar.");
      tabLeg.focus();
      return;
    }
    const headers = Array.from({ length: c }, (_, i) => "Cabeçalho " + (i + 1));
    const rowsArr = Array.from({ length: r }, () =>
      Array.from({ length: c }, () => ""),
    );
    const est = _tabEst();
    const pos = _tabPos();
    openTableEditor({
      legenda: leg,
      headers,
      rows: rowsArr,
      mode: "insert",
      idx: nextTabIdx(est),
      pos,
    });
  });
  if (editTabBtn)
    editTabBtn.addEventListener("click", () => {
      const found = findTableMarkerAtCursor();
      if (!found) {
        alert("Posicione o cursor dentro de uma tabela existente para editar.");
        return;
      }
      openTableEditor({
        legenda: found.legenda,
        headers: found.headers,
        rows: found.rows,
        mode: "replace",
        range: found.range,
        idx: found.idx,
        pos: found.pos,
      });
    });

  form.addEventListener("submit", () => {
    syncTitulo();
  });

  initEditBlocoFlow();

  const upBtn = document.getElementById("ins-fig-upload-btn");
  const upFile = document.getElementById("ins-fig-upload-file");
  if (upBtn && upFile) {
    upBtn.addEventListener("click", () => upFile.click());
    upFile.addEventListener("change", async () => {
      const file = upFile.files && upFile.files[0];
      if (!file) return;
      const leg = (figLeg.value || "").trim();
      if (!leg) {
        alert("Informe a legenda da figura antes de fazer upload.");
        figLeg.focus();
        upFile.value = "";
        return;
      }
      const fd = new FormData();
      fd.append("arquivo", file);
      if (leg) fd.append("legenda", leg);
      upBtn.disabled = true;
      const oldTxt = upBtn.textContent;
      upBtn.textContent = "Enviando…";
      try {
        const r = await fetch("/relatorios/" + relId + "/figuras", {
          method: "POST",
          body: fd,
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        const opt = document.createElement("option");
        opt.value = data.id;
        opt.textContent = "#" + data.id + " " + (data.nome || "figura");
        figSel.appendChild(opt);
        figSel.value = String(data.id);
        figSel.dispatchEvent(new Event("change"));
        const legEsc = leg.replace(/\|/g, "/");
        const est = _figEst();
        const pos = _figPos();
        const idx = nextFigIdx(est);
        insertText(
          "[[FIGURA:" + idx + "|" + data.id + "|" + pos + "|" + legEsc + "]]",
          { blockLine: true },
        );
        figLeg.value = "";
        _atualizaExemplos();
      } catch (e) {
        alert("Falha no upload: " + e.message);
      } finally {
        upBtn.disabled = false;
        upBtn.textContent = oldTxt;
        upFile.value = "";
      }
    });
  }

  const tabModal = document.getElementById("tab-editor");
  const tabModalLeg = document.getElementById("tab-editor-leg");
  const tabModalTbl = document.getElementById("tab-editor-table");
  const tabModalThead = tabModalTbl.querySelector("thead");
  const tabModalTbody = tabModalTbl.querySelector("tbody");
  const tabModalClose = document.getElementById("tab-editor-close");
  const tabModalCancel = document.getElementById("tab-editor-cancel");
  const tabModalConfirm = document.getElementById("tab-editor-confirm");
  let _tabState = null;

  function _renderEditorTable() {
    if (!_tabState) return;
    const { headers, rows } = _tabState;
    tabModalThead.innerHTML = "";
    const trh = document.createElement("tr");
    headers.forEach((h, ci) => {
      const th = document.createElement("th");
      th.contentEditable = "true";
      th.spellcheck = false;
      th.textContent = h;
      th.dataset.col = ci;
      th.addEventListener("input", () => {
        _tabState.headers[ci] = th.textContent;
      });
      th.addEventListener("keydown", _onCellKey);
      trh.appendChild(th);
    });
    tabModalThead.appendChild(trh);
    tabModalTbody.innerHTML = "";
    rows.forEach((r, ri) => {
      const tr = document.createElement("tr");
      r.forEach((v, ci) => {
        const td = document.createElement("td");
        td.contentEditable = "true";
        td.spellcheck = false;
        td.textContent = v;
        td.dataset.row = ri;
        td.dataset.col = ci;
        td.addEventListener("input", () => {
          _tabState.rows[ri][ci] = td.textContent;
        });
        td.addEventListener("keydown", _onCellKey);
        tr.appendChild(td);
      });
      tabModalTbody.appendChild(tr);
    });
  }
  function _onCellKey(e) {
    if (e.key === "Tab") {
      e.preventDefault();
      const cell = e.currentTarget;
      const row = cell.parentElement;
      const cells = Array.from(row.children);
      const idx = cells.indexOf(cell);
      const allRows = [
        tabModalThead.querySelector("tr"),
        ...Array.from(tabModalTbody.querySelectorAll("tr")),
      ];
      const rowIdx = allRows.indexOf(row);
      let nextRowIdx = rowIdx,
        nextIdx = idx + (e.shiftKey ? -1 : 1);
      if (nextIdx >= cells.length) {
        nextIdx = 0;
        nextRowIdx++;
      }
      if (nextIdx < 0) {
        nextIdx = cells.length - 1;
        nextRowIdx--;
      }
      const target = allRows[nextRowIdx]?.children[nextIdx];
      if (target) {
        target.focus();
        document.getSelection().selectAllChildren(target);
      }
    }
  }
  function openTableEditor(opts) {
    _tabState = {
      mode: opts.mode || "insert",
      range: opts.range || null,
      idx: opts.idx || nextTabIdx(_tabEst()),
      pos: opts.pos || _tabPos(),
      headers: opts.headers.slice(),
      rows: opts.rows.map((r) => r.slice()),
    };
    tabModalLeg.value = opts.legenda || "";
    _renderEditorTable();
    tabModal.classList.remove("is-hidden");
    setTimeout(() => {
      tabModalThead.querySelector("th")?.focus();
    }, 30);
  }
  function closeTableEditor() {
    tabModal.classList.add("is-hidden");
    _tabState = null;
  }
  tabModalClose.addEventListener("click", closeTableEditor);
  tabModalCancel.addEventListener("click", closeTableEditor);
  tabModal.addEventListener("click", (e) => {
    if (e.target === tabModal) closeTableEditor();
  });

  document.querySelectorAll("[data-tab-act]").forEach((b) =>
    b.addEventListener("click", () => {
      if (!_tabState) return;
      const act = b.dataset.tabAct;
      const cols = _tabState.headers.length;
      if (act === "add-row")
        _tabState.rows.push(Array.from({ length: cols }, () => ""));
      else if (act === "del-row") {
        if (_tabState.rows.length > 1) _tabState.rows.pop();
      } else if (act === "add-col") {
        _tabState.headers.push("Cabeçalho " + (cols + 1));
        _tabState.rows.forEach((r) => r.push(""));
      } else if (act === "del-col") {
        if (cols > 1) {
          _tabState.headers.pop();
          _tabState.rows.forEach((r) => r.pop());
        }
      }
      _renderEditorTable();
    }),
  );

  function _serializeTabela(state, legenda) {
    const esc = (s) =>
      String(s == null ? "" : s)
        .replace(/\|/g, "/")
        .replace(/\n/g, " ")
        .trim();
    const head = state.headers.map(esc).join(" | ");
    const sep = state.headers.map(() => "---").join(" | ");
    const body = state.rows.map((r) => r.map(esc).join(" | ")).join("\n");
    const leg = (legenda || "").replace(/\|/g, "/").trim();
    const idx = state.idx || nextTabIdx(_tabEst());
    const pos = state.pos || _tabPos();
    return (
      "[[TABELA:" +
      idx +
      "|" +
      pos +
      "|" +
      leg +
      "]]\n" +
      head +
      "\n" +
      sep +
      "\n" +
      body +
      "\n[[/TABELA]]"
    );
  }

  tabModalConfirm.addEventListener("click", () => {
    if (!_tabState) return;
    const marker = _serializeTabela(_tabState, tabModalLeg.value);
    if (_tabState.mode === "replace" && _tabState.range) {
      const q = window._sraQuill;
      if (q) {
        const delLen = _tabState.range.end - _tabState.range.start;
        q.deleteText(_tabState.range.start, delLen, "user");
        q.insertText(_tabState.range.start, marker, "user");
        q.setSelection(_tabState.range.start + marker.length, 0, "silent");
        syncQuillToTextarea();
      } else {
        const before = ta.value.slice(0, _tabState.range.start);
        const after = ta.value.slice(_tabState.range.end);
        ta.value = before + marker + after;
        const newPos = before.length + marker.length;
        ta.focus();
        ta.selectionStart = ta.selectionEnd = newPos;
        lastCursor = { start: newPos, end: newPos };
      }
    } else {
      insertText(marker, { blockLine: true });
      tabLeg.value = "";
    }
    closeTableEditor();
    updateStatus();
  });

  function findTableMarkerAtCursor() {
    const q = window._sraQuill;
    const val = q ? q.getText(0, Math.max(0, q.getLength())) : ta.value || "";
    let pos = 0;
    if (q) {
      const sel = q.getSelection(true);
      pos = sel ? sel.index : 0;
    } else {
      pos = ta.selectionStart || 0;
    }
    const reOpen =
      /\[\[TABELA(?::([^\|\]]+))?(?:\|([^\|\]]+))?(?:\|([^\]]*))?\]\]/g;
    const reClose = /\[\[\/TABELA\]\]/g;
    let m,
      lastOpen = null;
    while ((m = reOpen.exec(val)) !== null) {
      if (m.index <= pos) lastOpen = m;
      else break;
    }
    if (!lastOpen) return null;
    reClose.lastIndex = lastOpen.index;
    const mc = reClose.exec(val);
    if (!mc) return null;
    if (pos > mc.index + mc[0].length) return null;
    const start = lastOpen.index;
    const end = mc.index + mc[0].length;
    const inner = val.slice(lastOpen.index + lastOpen[0].length, mc.index);
    let posFlag = "S",
      legenda = "";
    if (lastOpen[2] === "S" || lastOpen[2] === "I") {
      posFlag = lastOpen[2];
      legenda = lastOpen[3] || "";
    } else if (lastOpen[2] != null) {
      legenda = lastOpen[2];
    } else if (lastOpen[3] != null) {
      legenda = lastOpen[3];
    }
    const linhas = inner
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .filter((l) => !/^-{2,}(\s*\|\s*-{2,})*$/.test(l))
      .filter((l) => !/^\+[-=+\s]+\+?$/.test(l));
    const splitCells = (ln) => {
      let s = ln;
      if (s.startsWith("|")) s = s.slice(1);
      if (s.endsWith("|")) s = s.slice(0, -1);
      return s.split("|").map((c) => c.trim());
    };
    if (!linhas.length) return null;
    const headers = splitCells(linhas[0]);
    const rows = linhas
      .slice(1)
      .map(splitCells)
      .map((r) => {
        while (r.length < headers.length) r.push("");
        return r.slice(0, headers.length);
      });
    return {
      range: { start, end },
      idx: lastOpen[1] || "",
      pos: posFlag,
      legenda,
      headers,
      rows: rows.length
        ? rows
        : [Array.from({ length: headers.length }, () => "")],
    };
  }

  const bsTag = document.getElementById("bs-tag");
  const bsInfo = document.getElementById("bs-info");
  const CLASS_LABEL = {
    titulo: "Título",
    subtitulo: "Subtítulo",
    paragrafo: "Parágrafo",
    lista: "Item de lista",
    figura: "Figura",
    tabela: "Tabela",
    vazio: "Linha vazia",
  };
  function classifyLine(line, ctx) {
    if (ctx && ctx.insideTabela) return "tabela";
    const s = line || "";
    const t = s.trim();
    if (!t) return "vazio";
    if (/^#\s+/.test(t)) return "titulo";
    if (/^##\s+/.test(t)) return "subtitulo";
    if (/^-\s+/.test(t)) return "lista";
    if (/^\[\[FIGURA:/.test(t)) return "figura";
    if (/^\[\[TABELA(\||\]\])/.test(t) || /^\[\[\/TABELA\]\]/.test(t))
      return "tabela";
    if (/^[+|]/.test(t) && /[+|]$/.test(t)) return "tabela";
    return "paragrafo";
  }
  function updateStatus() {
    if (!bsTag || !bsInfo) return;
    if (window._sraQuill) {
      const q = window._sraQuill;
      const charCount = Math.max(0, q.getLength() - 1);
      bsTag.dataset.cls = "paragrafo";
      bsTag.textContent = "Editor formatado";
      bsInfo.textContent =
        charCount + " caractere" + (charCount === 1 ? "" : "s") + " (Quill)";
      const val = ta.value || "";
      if (editTabBtn) editTabBtn.disabled = !/\[\[TABELA(:|\||\]\])/.test(val);
      return;
    }
    const val = ta.value || "";
    const pos = ta.selectionStart || 0;
    const before = val.slice(0, pos);
    const lastOpen = before.lastIndexOf("[[TABELA");
    const lastClose = before.lastIndexOf("[[/TABELA]]");
    const insideTabela = lastOpen > lastClose;
    const lineStart = before.lastIndexOf("\n") + 1;
    const lineEnd = val.indexOf("\n", pos);
    const line = val.slice(lineStart, lineEnd === -1 ? val.length : lineEnd);
    const lineNum = (before.match(/\n/g) || []).length + 1;
    const colNum = pos - lineStart + 1;
    const cls = classifyLine(line, { insideTabela });
    bsTag.dataset.cls = cls;
    bsTag.textContent = CLASS_LABEL[cls] || cls;
    bsInfo.textContent = "linha " + lineNum + ", coluna " + colNum;
    if (editTabBtn) editTabBtn.disabled = !/\[\[TABELA(:|\||\]\])/.test(val);
  }
  if (!window._sraQuill) {
    ["keyup", "mouseup", "click", "focus", "input", "select"].forEach((ev) =>
      ta.addEventListener(ev, updateStatus),
    );
    ta.addEventListener("input", _atualizaExemplos);
    document.addEventListener("selectionchange", () => {
      if (document.activeElement === ta) updateStatus();
    });
  } else {
    ta.addEventListener("input", _atualizaExemplos);
  }
  updateStatus();
  _atualizaExemplos();
})();

function editarBloco(id, titulo, tipo, conteudo, secIdBloco) {
  document.getElementById("add-bloco-titulo").value = titulo || "";
  document.getElementById("add-bloco-tipo").value = tipo || "texto";
  document.getElementById("add-bloco-conteudo").value = conteudo || "";
  if (window.loadSraQuillContent) window.loadSraQuillContent(conteudo || "");
  const editorSubsec = document.getElementById("add-bloco-editor-subsec");
  if (editorSubsec) editorSubsec.classList.remove("is-hidden");
  const wrapEc = document.getElementById("edit-bloco-controls");
  const relIdEc = wrapEc ? wrapEc.dataset.relId : readSecaoEditData("relId", 0);
  const selEc = document.getElementById("sec-nav");
  let sid = secIdBloco != null && secIdBloco !== "" ? Number(secIdBloco) : NaN;
  if (
    !Number.isFinite(sid) &&
    selEc &&
    selEc.value !== "__todas_confirmadas__"
  ) {
    sid = Number(selEc.value);
  }
  if (!Number.isFinite(sid)) {
    sid = Number(
      wrapEc && wrapEc.dataset.secAtual
        ? wrapEc.dataset.secAtual
        : readSecaoEditData("secId", 0),
    );
  }
  const frm = document.getElementById("form-add-bloco");
  frm.action =
    "/relatorios/" + relIdEc + "/secoes/" + sid + "/blocos/" + id + "/editar";

  const submitBtn = frm.querySelector('button[type="submit"]');
  if (submitBtn) submitBtn.textContent = "Salvar bloco editado";

  let cancelBtn = document.getElementById("btn-cancel-edit");
  if (!cancelBtn) {
    cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.id = "btn-cancel-edit";
    cancelBtn.className = "secondary btn-cancel";
    cancelBtn.textContent = "Cancelar edição";
    cancelBtn.onclick = function () {
      const w = document.getElementById("edit-bloco-controls");
      const r = w ? w.dataset.relId : readSecaoEditData("relId", 0);
      const sn = document.getElementById("sec-nav");
      let rs =
        sn && sn.value !== "__todas_confirmadas__" ? Number(sn.value) : NaN;
      if (!Number.isFinite(rs)) {
        rs = Number(
          w && w.dataset.secAtual
            ? w.dataset.secAtual
            : readSecaoEditData("secId", 0),
        );
      }
      frm.action = "/relatorios/" + r + "/secoes/" + rs + "/blocos";
      submitBtn.textContent = "Inserir novo bloco";
      const opt =
        sn && sn.selectedIndex >= 0 ? sn.options[sn.selectedIndex] : null;
      document.getElementById("add-bloco-titulo").value = opt
        ? opt.text.trim()
        : "{{ sec.numero }} – {{ sec.titulo }}";
      document.getElementById("add-bloco-tipo").value = "texto";
      document.getElementById("add-bloco-conteudo").value = "";
      if (window.loadSraQuillContent) window.loadSraQuillContent("");
      const editorSubsec = document.getElementById("add-bloco-editor-subsec");
      if (editorSubsec) editorSubsec.classList.add("is-hidden");
      if (window.atualizaExemplosBloco) window.atualizaExemplosBloco();
      this.remove();
    };
    submitBtn.parentNode.insertBefore(cancelBtn, submitBtn.nextSibling);
  }
  const _quillFocus = document.getElementById("add-bloco-quill");
  if (window._sraQuill && _quillFocus) {
    _quillFocus.scrollIntoView({ behavior: "smooth", block: "center" });
    window._sraQuill.focus();
  } else {
    document
      .getElementById("add-bloco-conteudo")
      .scrollIntoView({ behavior: "smooth", block: "center" });
    document.getElementById("add-bloco-conteudo").focus();
  }
  if (window.atualizaExemplosBloco) window.atualizaExemplosBloco();
}

document.querySelectorAll(".edit-bloco-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    editarBloco(
      Number(btn.dataset.blocoId),
      parseJsonValue(btn.dataset.blocoTitulo, ""),
      parseJsonValue(btn.dataset.blocoTipo, "texto"),
      parseJsonValue(btn.dataset.blocoConteudo, ""),
    );
  });
});

let _blocoIdEmEdicao = null;
function initEditBlocoFlow() {
  const wrap = document.getElementById("edit-bloco-controls");
  if (!wrap) return;
  const relId = wrap.dataset.relId;
  const sel = document.getElementById("sec-nav");
  const btnCarregar = document.getElementById("btn-edit-carregar");
  const btnSalvar = document.getElementById("btn-edit-salvar");
  const btnConfirmar = document.getElementById("btn-edit-confirmar");
  const btnSalvarTodos = document.getElementById("btn-edit-salvar-todos");
  const status = document.getElementById("edit-bloco-status");
  const tabelaWrap = document.getElementById("edit-bloco-tabela-wrap");
  const tabelaBody = document.getElementById("edit-bloco-tabela-body");
  const tabelaTit = document.getElementById("edit-bloco-tabela-titulo");
  const tabelaMeta = document.getElementById("edit-bloco-tabela-meta");
  const taConteudo = document.getElementById("add-bloco-conteudo");
  const inpTitulo = document.getElementById("add-bloco-titulo");
  const inpTipo = document.getElementById("add-bloco-tipo");
  const formAdd = document.getElementById("form-add-bloco");
  let _ultimosBlocosCarregados = [];

  function setStatus(msg, kind) {
    status.textContent = msg || "";
    status.dataset.kind = kind || "";
  }
  function localKey(id) {
    return "sra:rascunho:bloco:" + id;
  }
  function temRascunho(id) {
    return !!window.localStorage.getItem(localKey(id));
  }
  function lerRascunho(id) {
    const raw = window.localStorage.getItem(localKey(id));
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }
  function escHtml(s) {
    return String(s == null ? "" : s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  }
  let refMapas = null;
  function resolverRefs(texto, mapas) {
    if (!texto || texto.indexOf("[[REF:") === -1) return texto || "";
    const fig = (mapas && mapas.figuras) || {};
    const tab = (mapas && mapas.tabelas) || {};
    const sec = (mapas && mapas.secoes) || {};
    return texto.replace(
      /\[\[REF:(figura|tabela|secao)\|(\d+)\]\]/g,
      function (full, tipo, id) {
        const k = String(id);
        if (tipo === "figura" && fig[k]) return "Figura " + fig[k];
        if (tipo === "tabela" && tab[k]) return "Tabela " + tab[k];
        if (tipo === "secao" && sec[k]) return "Seção " + sec[k];
        return full;
      },
    );
  }
  function resumoBloco(b) {
    let cont = (b.conteudo || "").replace(/\s+/g, " ").trim();
    cont = resolverRefs(cont, refMapas);
    return cont.length <= 80 ? cont || "—" : cont.slice(0, 77) + "…";
  }
  function tipoLabel(b) {
    const t = (b.tipo || "").toLowerCase();
    if (t === "figura") return "Figura";
    if (t === "tabela") return "Tabela";
    if (t === "lista") return "Lista";
    const c = (b.conteudo || "").trim();
    if (c.startsWith("## ")) return "Subtítulo";
    if (c.startsWith("# ")) return "Título";
    return "Parágrafo";
  }
  function classeLabel(b) {
    var tipo = (b.tipo || "").toLowerCase();
    var conteudo = String(b.conteudo || "").trim();
    if (tipo === "texto") {
      if (conteudo.startsWith("# ")) return "Título";
      if (conteudo.startsWith("## ")) return "Subtítulo";
      return "Parágrafo";
    }
    if (tipo === "lista") return "Lista";
    if (tipo === "figura") return "Figura";
    if (tipo === "tabela") return "Tabela";
    return "—";
  }
  function renderRow(b, secNumero) {
    const draft = temRascunho(b.id);
    const upd = b.updated_at ? new Date(b.updated_at).toLocaleString() : "—";
    const podeEditarLinha = b.pode_editar !== false;
    const numCol =
      b.secao_numero != null && String(b.secao_numero) !== ""
        ? b.secao_numero
        : secNumero;
    const payload = encodeURIComponent(
      JSON.stringify({
        id: b.id,
        secao_id: b.secao_id,
        titulo: b.titulo || "",
        tipo: b.tipo || "texto",
        conteudo: b.conteudo || "",
      }),
    );
    let acaoCell;
    if (!podeEditarLinha) {
      acaoCell =
        '<span class="locked-lbl" title="Status do relatório não permite edição">Sem permissão</span>';
    } else if (b.bloqueado) {
      acaoCell =
        '<span class="locked-lbl modo-edicao-tag" title="Coordenador em modo edição: alterações permitidas">Modo edição</span>' +
        '<button type="button" class="bloco-action btn-row-edit" data-payload="' +
        payload +
        '" title="Editar este bloco no editor abaixo" aria-label="Editar bloco">✎</button>';
    } else {
      acaoCell =
        '<button type="button" class="bloco-action btn-row-edit" data-payload="' +
        payload +
        '" title="Editar este bloco no editor abaixo" aria-label="Editar bloco">✎</button>';
    }
    return (
      '<tr data-bloco-id="' +
      b.id +
      '"' +
      (podeEditarLinha ? "" : ' class="row-readonly"') +
      ">" +
      "<td>" +
      escHtml(numCol) +
      "</td>" +
      "<td>" +
      escHtml(tipoLabel(b)) +
      "</td>" +
      "<td>" +
      escHtml(classeLabel(b)) +
      "</td>" +
      '<td title="' +
      escHtml(resolverRefs(b.conteudo || "", refMapas)) +
      '">' +
      escHtml(resumoBloco(b)) +
      "</td>" +
      "<td>" +
      escHtml(upd) +
      "</td>" +
      "<td>" +
      (draft ? '<span class="badge-draft">rascunho</span>' : "—") +
      "</td>" +
      "<td>" +
      acaoCell +
      "</td>" +
      "</tr>"
    );
  }

  let _podeEditarSecao = true;
  let _motivoBloqueio = "";

  function syncFormActionNovoBloco() {
    if (!formAdd || !sel) return;
    const v = sel.value;
    if (v === "__todas_confirmadas__") return;
    if (formAdd.action.indexOf("/editar") !== -1) return;
    const n = Number(v);
    if (!Number.isFinite(n)) return;
    formAdd.action = "/relatorios/" + relId + "/secoes/" + n + "/blocos";
    const opt = sel.options[sel.selectedIndex];
    if (opt && inpTitulo) inpTitulo.value = opt.text.trim();
  }

  function syncExcluirConfirmadosBtn() {
    const bx = document.getElementById("btn-edit-excluir-confirmados");
    if (!bx) return;
    const onTodas = sel.value === "__todas_confirmadas__";
    bx.classList.toggle("is-hidden", !onTodas);
  }

  async function carregar() {
    const rawVal = sel.value;
    const isTodas = rawVal === "__todas_confirmadas__";
    const secId = isTodas ? null : Number(rawVal);
    if (!isTodas && !Number.isFinite(secId)) return;
    const secOpt = sel.options[sel.selectedIndex];
    const secLabel = secOpt ? secOpt.text : "";
    setStatus("Carregando blocos…", "working");
    try {
      const url = isTodas
        ? "/relatorios/" + relId + "/blocos-confirmados.json"
        : "/relatorios/" + relId + "/secoes/" + secId + "/blocos.json";
      const r = await fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (r.status === 403) {
        setStatus("Sem permissão para aceder a estes dados.", "danger");
        return;
      }
      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();
      refMapas = data.ref_mapas || null;
      const blocos = data.blocos || [];
      _ultimosBlocosCarregados = blocos.slice();
      const secNumero = (data.secao && data.secao.numero) || "";
      _podeEditarSecao = data.pode_editar_secao !== false;
      _motivoBloqueio = data.motivo_bloqueio || "";
      if (!isTodas && Number.isFinite(secId)) {
        wrap.dataset.secAtual = String(secId);
      }
      tabelaTit.textContent = isTodas
        ? "Blocos confirmados (todas as seções)"
        : "Blocos da seção " + secLabel + " (com subsecções)";
      const totalEditaveis = blocos.filter(
        (b) => b.pode_editar !== false,
      ).length;
      tabelaMeta.textContent =
        blocos.length +
        " bloco(s)" +
        (_podeEditarSecao ? " · " + totalEditaveis + " editáveis" : "");
      tabelaBody.innerHTML = blocos.length
        ? blocos.map((b) => renderRow(b, secNumero)).join("")
        : '<tr><td colspan="6" class="empty-row">' +
          (isTodas
            ? "Nenhum bloco confirmado no relatório."
            : "Nenhum bloco nesta seção.") +
          "</td></tr>";
      tabelaWrap.classList.remove("is-hidden");
      tabelaBody.querySelectorAll(".btn-row-edit").forEach((btn) => {
        btn.addEventListener("click", () => {
          let p;
          try {
            p = JSON.parse(decodeURIComponent(btn.dataset.payload));
          } catch (e) {
            setStatus("Erro ao ler bloco: " + e.message, "danger");
            return;
          }
          const draft = lerRascunho(p.id);
          editarBloco(
            p.id,
            p.titulo,
            p.tipo,
            draft ? draft.conteudo : p.conteudo,
            p.secao_id,
          );
          _blocoIdEmEdicao = p.id;
          btnSalvar.disabled = false;
          btnConfirmar.disabled = false;
          if (draft)
            setStatus(
              "Rascunho local de " +
                new Date(draft.ts).toLocaleString() +
                " carregado.",
              "info",
            );
          else setStatus("Bloco #" + p.id + " carregado para edição.", "info");
        });
      });
      syncExcluirConfirmadosBtn();
      if (!_podeEditarSecao) {
        setStatus(
          _motivoBloqueio ||
            "Edição não permitida no status atual do relatório.",
          "warn",
        );
      } else {
        setStatus(blocos.length + " bloco(s) carregados.", "ok");
      }
    } catch (e) {
      setStatus("Falha ao carregar: " + e.message, "danger");
    }
  }

  function parseEditTarget() {
    if (!formAdd) return null;
    const m = formAdd.action.match(
      /\/relatorios\/(\d+)\/secoes\/(\d+)\/blocos\/(\d+)\/editar(?:\?|$|\/|#)/,
    );
    if (!m) return null;
    return {
      relId: Number(m[1]),
      secaoId: Number(m[2]),
      blocoId: Number(m[3]),
    };
  }

  function salvar() {
    if (!_blocoIdEmEdicao) {
      setStatus("Carregue um bloco no editor antes de salvar.", "warn");
      return;
    }
    const payload = {
      id: _blocoIdEmEdicao,
      titulo: inpTitulo.value || "",
      tipo: inpTipo.value || "texto",
      conteudo: taConteudo.value || "",
      ts: Date.now(),
    };
    const pe = parseEditTarget();
    if (pe) payload.secao_id = pe.secaoId;
    try {
      window.localStorage.setItem(
        localKey(_blocoIdEmEdicao),
        JSON.stringify(payload),
      );
      setStatus(
        "Rascunho salvo localmente às " + new Date().toLocaleTimeString() + ".",
        "ok",
      );
    } catch (e) {
      setStatus("Falha ao salvar localmente: " + e.message, "danger");
    }
  }

  async function salvarTodosRascunhosNoServidor() {
    if (!_podeEditarSecao) {
      setStatus(
        _motivoBloqueio || "Edição não permitida no status atual do relatório.",
        "warn",
      );
      return;
    }
    if (
      _blocoIdEmEdicao &&
      formAdd &&
      formAdd.action.indexOf("/editar") !== -1
    ) {
      const flush = {
        id: _blocoIdEmEdicao,
        titulo: inpTitulo.value || "",
        tipo: inpTipo.value || "texto",
        conteudo: taConteudo.value || "",
        ts: Date.now(),
      };
      const pe0 = parseEditTarget();
      if (pe0) flush.secao_id = pe0.secaoId;
      try {
        window.localStorage.setItem(
          localKey(_blocoIdEmEdicao),
          JSON.stringify(flush),
        );
      } catch (e) {
        setStatus(
          "Falha ao sincronizar o editor atual: " + e.message,
          "danger",
        );
        return;
      }
    }
    const mapa = {};
    _ultimosBlocosCarregados.forEach(function (b) {
      mapa[b.id] = b;
    });
    const pendentes = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (!k || k.indexOf("sra:rascunho:bloco:") !== 0) continue;
      let d;
      try {
        d = JSON.parse(window.localStorage.getItem(k));
      } catch (e2) {
        continue;
      }
      if (!d || !d.id) continue;
      let sid = d.secao_id;
      if (!Number.isFinite(Number(sid))) {
        const mb = mapa[d.id];
        if (mb) sid = mb.secao_id;
      }
      sid = Number(sid);
      if (!Number.isFinite(sid)) continue;
      const mb = mapa[d.id];
      if (mb && mb.pode_editar === false) continue;
      const tipo = (d.tipo || "texto").toLowerCase();
      if ((tipo === "figura" || tipo === "tabela") && !mb) {
        continue;
      }
      pendentes.push({ draft: d, secId: sid, meta: mb || null });
    }
    if (!pendentes.length) {
      setStatus(
        "Nenhum rascunho local pendente para enviar ao servidor.",
        "info",
      );
      return;
    }
    setStatus(
      "A gravar " + pendentes.length + " rascunho(s) no servidor…",
      "working",
    );
    let ok = 0;
    for (let p = 0; p < pendentes.length; p++) {
      const item = pendentes[p];
      const d = item.draft;
      const fd = new FormData();
      fd.append("titulo", d.titulo || "");
      fd.append("conteudo", d.conteudo || "");
      const meta = item.meta;
      fd.append("legenda", meta && meta.legenda ? meta.legenda : "");
      fd.append("fonte", meta && meta.fonte ? meta.fonte : "");
      fd.append(
        "figura_id",
        meta && meta.figura_id != null && String(meta.figura_id).trim() !== ""
          ? String(meta.figura_id)
          : "",
      );
      const url =
        "/relatorios/" +
        relId +
        "/secoes/" +
        item.secId +
        "/blocos/" +
        d.id +
        "/editar";
      const r = await fetch(url, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });
      if (!r.ok) {
        setStatus(
          "Falha ao gravar bloco #" + d.id + " (HTTP " + r.status + ").",
          "danger",
        );
        return;
      }
      window.localStorage.removeItem(localKey(d.id));
      ok++;
    }
    setStatus(
      ok +
        " bloco(s) gravados no servidor. Rascunhos locais correspondentes foram removidos.",
      "ok",
    );
  }

  async function confirmar() {
    if (!_blocoIdEmEdicao) {
      setStatus("Carregue um bloco antes de confirmar.", "warn");
      return;
    }
    const pe = parseEditTarget();
    if (!pe) {
      setStatus("Não foi possível determinar o alvo de edição.", "danger");
      return;
    }
    salvar();
    const draft = lerRascunho(_blocoIdEmEdicao);
    const titulo = draft ? draft.titulo : inpTitulo.value || "";
    const conteudo = draft ? draft.conteudo : taConteudo.value || "";
    const fd = new FormData();
    fd.append("titulo", titulo);
    fd.append("conteudo", conteudo);
    fd.append("legenda", "");
    fd.append("fonte", "");
    fd.append("figura_id", "");
    const url =
      "/relatorios/" +
      pe.relId +
      "/secoes/" +
      pe.secaoId +
      "/blocos/" +
      pe.blocoId +
      "/editar";
    setStatus("Enviando bloco #" + pe.blocoId + " ao servidor…", "working");
    try {
      const r = await fetch(url, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });
      if (!r.ok) {
        setStatus(
          "Falha ao confirmar bloco #" +
            pe.blocoId +
            " (HTTP " +
            r.status +
            ").",
          "danger",
        );
        return;
      }
      window.localStorage.removeItem(localKey(_blocoIdEmEdicao));
      setStatus(
        "Bloco #" + pe.blocoId + " enviado ao servidor com sucesso.",
        "ok",
      );
      _blocoIdEmEdicao = null;
      btnSalvar.disabled = true;
      btnConfirmar.disabled = true;
    } catch (e) {
      setStatus("Falha ao confirmar: " + e.message, "danger");
    }
  }

  if (formAdd) {
    formAdd.addEventListener("submit", (e) => {
      const isEdit = formAdd.action.indexOf("/editar") !== -1;
      if (isEdit) {
        e.preventDefault();
        salvar();
        return;
      }
    });
  }

  btnCarregar.addEventListener("click", carregar);
  btnSalvar.addEventListener("click", salvar);
  btnConfirmar.addEventListener("click", confirmar);
  if (btnSalvarTodos) {
    btnSalvarTodos.addEventListener("click", function () {
      salvarTodosRascunhosNoServidor();
    });
  }
  window.SRA_salvarTodosRascunhos = salvarTodosRascunhosNoServidor;
  sel.addEventListener("change", () => {
    syncFormActionNovoBloco();
    syncExcluirConfirmadosBtn();
  });
  syncFormActionNovoBloco();
  syncExcluirConfirmadosBtn();

  const btnExcluirConf = document.getElementById(
    "btn-edit-excluir-confirmados",
  );
  if (btnExcluirConf) {
    btnExcluirConf.addEventListener("click", async () => {
      if (sel.value !== "__todas_confirmadas__") return;
      if (
        !window.confirm(
          "Remover todos os blocos confirmados (bloqueados) deste relatório? Esta ação não pode ser desfeita.",
        )
      )
        return;
      setStatus("A excluir…", "working");
      try {
        const r = await fetch(
          "/relatorios/" + relId + "/blocos/excluir-todos-confirmados",
          {
            method: "POST",
            credentials: "same-origin",
            headers: { Accept: "application/json" },
          },
        );
        let data = {};
        try {
          data = await r.json();
        } catch (e1) {
          data = {};
        }
        if (!r.ok) {
          const d = data.detail;
          const msg =
            typeof d === "string"
              ? d
              : Array.isArray(d)
                ? d.map((x) => x.msg || x).join("; ")
                : "HTTP " + r.status;
          throw new Error(msg || "HTTP " + r.status);
        }
        setStatus(
          (data.removidos || 0) + " bloco(s) confirmado(s) removido(s).",
          "ok",
        );
        await carregar();
      } catch (e) {
        setStatus("Falha: " + e.message, "danger");
      }
    });
  }
}

(function () {
  const checks = Array.from(document.querySelectorAll(".bloco-select"));
  const enabledChecks = checks.filter((check) => !check.disabled);
  const selectAll = document.getElementById("bulk-select-all");
  const count = document.getElementById("bulk-count");
  const buttons = Array.from(document.querySelectorAll("[data-bulk-submit]"));
  const forms = [
    document.getElementById("bulk-aprovar-form"),
    document.getElementById("bulk-excluir-form"),
    document.getElementById("bulk-desbloquear-form"),
  ].filter(Boolean);
  if (!selectAll || !count) return;
  if (!enabledChecks.length) {
    count.textContent = "0 selecionados";
    return;
  }

  function selectedIds() {
    return enabledChecks
      .filter((check) => check.checked)
      .map((check) => check.value);
  }

  function syncBulkState() {
    const ids = selectedIds();
    count.textContent =
      ids.length + (ids.length === 1 ? " selecionado" : " selecionados");
    buttons.forEach((button) => {
      // Botão de desbloquear nunca fica desabilitado
      if (button.form && button.form.id === "bulk-desbloquear-form") {
        button.disabled = false;
      } else {
        button.disabled = !ids.length;
      }
    });
    selectAll.checked = ids.length > 0 && ids.length === enabledChecks.length;
    selectAll.indeterminate =
      ids.length > 0 && ids.length < enabledChecks.length;
  }

  function fillForm(form, ids) {
    form.querySelectorAll(".bulk-hidden-id").forEach((input) => input.remove());
    ids.forEach((id) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "bloco_ids";
      input.value = id;
      input.className = "bulk-hidden-id";
      form.appendChild(input);
    });
  }

  selectAll.addEventListener("change", () => {
    enabledChecks.forEach((check) => {
      check.checked = selectAll.checked;
    });
    syncBulkState();
  });
  enabledChecks.forEach((check) =>
    check.addEventListener("change", syncBulkState),
  );
  forms.forEach((form) => {
    form.addEventListener("submit", async (ev) => {
      const ids = selectedIds();
      if (!ids.length) {
        ev.preventDefault();
        alert("Selecione ao menos um bloco.");
        return;
      }
      const chaveLote =
        form.id === "bulk-excluir-form"
          ? "blocos_lote_excluir"
          : form.id === "bulk-desbloquear-form"
            ? "blocos_lote_desbloquear"
            : "blocos_lote_aprovar";
      ev.preventDefault();
      const ok = window.SRAComplementos
        ? await window.SRAComplementos.confirmarComChave(chaveLote)
        : form.id === "bulk-excluir-form"
          ? window.confirm(
              "Deletar definitivamente " +
                ids.length +
                " bloco(s) selecionado(s)?",
            )
          : window.confirm(
              "Bloquear " +
                ids.length +
                " bloco(s) selecionado(s) para revisão?",
            );
      if (!ok) return;

      // Usar URLSearchParams para enviar dados de formulário
      const params = new URLSearchParams();
      ids.forEach((id) => params.append("bloco_ids", id));

      fetch(form.action, {
        method: "POST",
        body: params,
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      })
        .then((response) => {
          if (response.ok) {
            window.location.reload();
          } else {
            alert("Erro ao processar a solicitação.");
          }
        })
        .catch((error) => {
          console.error("Erro:", error);
          alert("Erro ao processar a solicitação.");
        });
    });
  });
  syncBulkState();
})();

// =====================================================================
// Importação de conteúdo — Opção B (lista hierárquica com cards por tipo)
// =====================================================================
(function () {
  const form = document.getElementById("form-importar-conteudo");
  if (!form) return;
  const fileIn = document.getElementById("import-arquivo");
  const status = document.getElementById("import-status");
  const review = document.getElementById("import-review");
  const list = document.getElementById("import-list");
  const summary = document.getElementById("import-summary");
  const confirmBtn = document.getElementById("import-confirm");
  const allOnBtn = document.getElementById("import-all-on");
  const allOffBtn = document.getElementById("import-all-off");
  const syncIdxBtn = document.getElementById("import-sync-indices");
  const syncIdxLabel = syncIdxBtn ? syncIdxBtn.textContent : "";
  const SECAO_FALLBACK_NUM = readSecaoEditData("secNumero", "");
  const SECAO_FALLBACK_TIT = readSecaoEditData("secTitulo", "");

  let existingSectionNumbers = new Set();
  try {
    const raw = list.dataset.secoesExistentes || "[]";
    JSON.parse(raw).forEach((n) =>
      existingSectionNumbers.add(String(n).trim()),
    );
  } catch (e) {
    /* ignora */
  }

  let importBlocks = [];
  let importAnaliseEmCurso = false;
  let importConfirmEmCurso = false;
  const figBasePage = Number(readSecaoEditData("figBase", 0)) || 0;
  const tabBasePage = Number(readSecaoEditData("tabBase", 0)) || 0;
  const curSecStr = String(SECAO_FALLBACK_NUM || "").trim();
  const uploadPageRelId = Number(readSecaoEditData("relId", 0));
  const uploadPageSecId = Number(readSecaoEditData("secId", 0));

  const TIPO_LABEL = {
    texto: "TEXTO",
    lista: "LISTA",
    figura: "FIGURA",
    tabela: "TABELA",
  };
  const SUBTIPO_LABEL = {
    titulo: "Título",
    subtitulo: "Subtítulo",
    paragrafo: "Parágrafo",
    lista: "Lista",
  };

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function domIdSuffix(keyStr) {
    const s = String(keyStr == null ? "" : keyStr).replace(
      /[^a-zA-Z0-9_-]/g,
      "_",
    );
    return s || "secao";
  }

  function confidenceClass(c) {
    const n = Number(c || 0);
    if (n >= 0.85) return "good";
    if (n >= 0.7) return "mid";
    return "low";
  }

  function acaoSecao(numero) {
    const n = String(numero || "").trim();
    if (!n) return "usar";
    return existingSectionNumbers.has(n) ? "usar" : "criar";
  }

  function acaoLabel(acao) {
    if (acao === "criar") return "CRIAR seção";
    if (acao === "renomear") return "renomear seção";
    return "usar seção";
  }

  function segmentosDetalhados(subtipos, conteudoBruto) {
    const linhas = String(conteudoBruto || "").split(/\r?\n/);
    const out = [];
    let li = 0;
    const totalLinhas = linhas.length;
    const avancarVazias = () => {
      while (li < totalLinhas && !linhas[li].trim()) li++;
    };
    const consumirLinha = () => {
      if (li < totalLinhas) {
        const v = linhas[li];
        li++;
        return v;
      }
      return "";
    };
    (subtipos || []).forEach((s) => {
      const kind = s.kind || "paragrafo";
      const count = Math.max(1, Number(s.count || 1));
      const previews = [];
      avancarVazias();
      if (kind === "titulo") {
        const l = consumirLinha();
        previews.push(l.replace(/^#\s+/, "").trim());
      } else if (kind === "subtitulo") {
        const l = consumirLinha();
        previews.push(l.replace(/^##\s+/, "").trim());
      } else if (kind === "lista") {
        const itens = [];
        for (let k = 0; k < count && li < totalLinhas; k++) {
          avancarVazias();
          const l = consumirLinha();
          if (l.trim()) itens.push(l.trim());
        }
        itens.forEach((t) => previews.push(t));
      } else {
        for (let k = 0; k < count && li < totalLinhas; k++) {
          avancarVazias();
          const buf = [];
          while (li < totalLinhas && linhas[li].trim()) {
            buf.push(linhas[li].trim());
            li++;
          }
          if (buf.length) previews.push(buf.join(" "));
        }
      }
      if (!previews.length && s.preview) previews.push(String(s.preview));
      out.push({ kind, count, previews });
    });
    return out;
  }

  function renderSubtipos(subtipos, conteudoBruto) {
    if (!Array.isArray(subtipos) || !subtipos.length) {
      return '<div class="import-segs-empty">sem segmentos detectados</div>';
    }
    const detalhados = segmentosDetalhados(subtipos, conteudoBruto);
    const items = detalhados
      .map((s) => {
        const kind = s.kind;
        const label = SUBTIPO_LABEL[kind] || kind;
        const count = s.count;
        const suffix =
          kind === "lista" && count > 1
            ? " (" + count + " itens)"
            : kind === "paragrafo" && count > 1
              ? " (" + count + ")"
              : "";
        const previewsHtml = (s.previews || [])
          .map((p) => '<li class="seg-preview-item">' + esc(p || "") + "</li>")
          .join("");
        return (
          '<li class="seg-item" data-kind="' +
          esc(kind) +
          '">' +
          '<div class="seg-row seg-row-chip">' +
          '<button type="button" class="seg-chip seg-chip-' +
          esc(kind) +
          '" data-seg-toggle="1" title="Clique para editar o texto bruto">' +
          esc(label + suffix) +
          "</button>" +
          "</div>" +
          '<div class="seg-row seg-row-preview">' +
          '<ul class="seg-preview-list">' +
          previewsHtml +
          "</ul>" +
          "</div>" +
          "</li>"
        );
      })
      .join("");
    return '<ul class="import-segs">' + items + "</ul>";
  }

  function renderTabelaPreview(prev) {
    if (!prev || !Array.isArray(prev.headers) || !prev.headers.length) {
      return '<div class="import-tab-empty">tabela vazia</div>';
    }
    const thead =
      "<thead><tr>" +
      prev.headers.map((h) => "<th>" + esc(h) + "</th>").join("") +
      "</tr></thead>";
    const tbody =
      "<tbody>" +
      prev.rows
        .map(
          (r) =>
            "<tr>" + r.map((c) => "<td>" + esc(c) + "</td>").join("") + "</tr>",
        )
        .join("") +
      "</tbody>";
    const info =
      (prev.total_rows || prev.rows.length) +
      " linha(s) × " +
      (prev.total_cols || prev.headers.length) +
      " coluna(s)" +
      (prev.truncated_rows || prev.truncated_cols ? " · prévia truncada" : "");
    return (
      '<table class="import-mini-tbl">' +
      thead +
      tbody +
      "</table>" +
      '<small class="import-tab-info">' +
      esc(info) +
      "</small>"
    );
  }

  var CLASSE_OPS = {
    texto: [
      { value: "paragrafo", label: "Parágrafo" },
      { value: "subtitulo", label: "Subtítulo (H2)" },
      { value: "titulo", label: "Título (H1)" },
    ],
    lista: [{ value: "lista", label: "Lista" }],
  };

  function deduceClasse(b) {
    if (b.subtipos && b.subtipos.length === 1)
      return b.subtipos[0].kind || "paragrafo";
    var c = String(b.conteudo || "").trim();
    if (c.startsWith("## ")) return "subtitulo";
    if (c.startsWith("# ")) return "titulo";
    if ((b.tipo || "") === "lista") return "lista";
    return "paragrafo";
  }

  function classeSelectBadge(i, b) {
    var tipo = (b.tipo || "texto").toLowerCase();
    var ops = CLASSE_OPS[tipo];
    if (!ops) return "";
    var atual = b.classe || deduceClasse(b);
    if (!b.classe) b.classe = atual;
    var opts = ops
      .map(function (o) {
        return (
          '<option value="' +
          o.value +
          '"' +
          (o.value === atual ? " selected" : "") +
          ">" +
          o.label +
          "</option>"
        );
      })
      .join("");
    return (
      '<select id="import-classe-sel-' +
      i +
      '" name="import-classe-sel-' +
      i +
      '"' +
      ' class="import-classe-sel" data-i="' +
      i +
      '" data-field="classe"' +
      ' title="Classe do bloco">' +
      opts +
      "</select>"
    );
  }

  function tipoSelectBadge(i, tipoAtual) {
    const opts = ["texto", "lista", "figura", "tabela"]
      .map((t) => {
        return (
          '<option value="' +
          t +
          '"' +
          (t === tipoAtual ? " selected" : "") +
          ">" +
          (TIPO_LABEL[t][0] + TIPO_LABEL[t].slice(1).toLowerCase()) +
          "</option>"
        );
      })
      .join("");
    return (
      '<select id="import-tipo-sel-' +
      i +
      '" name="import-tipo-sel-' +
      i +
      '" class="import-tipo-badge import-tipo-sel" data-tipo="' +
      esc(tipoAtual) +
      '" data-i="' +
      i +
      '" data-field="tipo" title="Tipo identificado pelo sistema — clique para alterar">' +
      opts +
      "</select>"
    );
  }

  function renderCardHeader(b, i) {
    const tipo = (b.tipo || "texto").toLowerCase();
    const conf = Number(b.confianca || 0);
    const confPct = Math.round(conf * 100);
    const confCls = confidenceClass(conf);
    const checked = b.selecionado !== false ? "checked" : "";
    const motivo = b.motivo || "";
    const confTip =
      "Nível de confiança: estimativa (0–100%) de que o sistema classificou corretamente o tipo deste bloco com base na análise do arquivo. " +
      "Faixas: ≥85% (alto) · 70–84% (médio) · <70% (baixo — revise antes de importar)." +
      (motivo ? "\nMotivo: " + motivo : "");
    return (
      '<header class="import-card-hdr" data-tipo="' +
      esc(tipo) +
      '">' +
      '<input type="checkbox" id="import-card-check-' +
      i +
      '" name="import-card-check-' +
      i +
      '" class="import-card-check" data-i="' +
      i +
      '" data-field="selecionado" ' +
      checked +
      ">" +
      tipoSelectBadge(i, tipo) +
      classeSelectBadge(i, b) +
      '<span class="import-conf-wrap">' +
      '<span class="import-conf-lbl" tabindex="0" data-conf-tip="' +
      esc(confTip) +
      '" title="' +
      esc(confTip) +
      '">Nível de confiança</span>' +
      '<span class="import-conf import-conf-' +
      confCls +
      '" tabindex="0" data-conf-tip="' +
      esc(confTip) +
      '" title="' +
      esc(confTip) +
      '">' +
      confPct +
      "%</span>" +
      "</span>" +
      "</header>"
    );
  }

  function renderSubsecaoProposal(b, i) {
    var secNumAtual = String(b.secao_numero || "").trim();
    var tituloSub = String(b.conteudo || "")
      .trim()
      .replace(/^##\s*/, "");
    var indiceSug = (function () {
      if (!secNumAtual) return "?";
      var prefixo = secNumAtual + ".";
      var maxFilho = 0;
      existingSectionNumbers.forEach(function (n) {
        if (n.startsWith(prefixo)) {
          var resto = n.slice(prefixo.length);
          if (!/\./.test(resto)) {
            var num = parseInt(resto, 10);
            if (!isNaN(num) && num > maxFilho) maxFilho = num;
          }
        }
      });
      return prefixo + (maxFilho + 1);
    })();
    return (
      '<div class="subsec-proposal" data-i="' +
      i +
      '">' +
      '<span class="subsec-proposal-icon">⤵</span>' +
      '<strong class="subsec-proposal-title">Proposta de nova subseção</strong>' +
      '<div class="subsec-proposal-fields">' +
      '<label class="mini-label">Índice</label>' +
      '<input type="text" id="subsec-num-' +
      i +
      '" name="subsec-num-' +
      i +
      '" class="subsec-proposal-num" data-i="' +
      i +
      '" value="' +
      esc(indiceSug) +
      '" placeholder="ex.: 2.1.1">' +
      '<label class="mini-label">Título</label>' +
      '<input type="text" id="subsec-titulo-' +
      i +
      '" name="subsec-titulo-' +
      i +
      '" class="subsec-proposal-titulo" data-i="' +
      i +
      '" value="' +
      esc(tituloSub) +
      '" placeholder="Título da subseção">' +
      "</div>" +
      '<p class="subsec-proposal-hint">Este bloco foi identificado como subtítulo. ' +
      "Confirme ou ajuste o índice e o título para criar automaticamente a subseção ao importar.</p>" +
      "</div>"
    );
  }

  function renderTextoCard(b, i) {
    return (
      '<article class="import-card import-card-texto" data-i="' +
      i +
      '">' +
      renderCardHeader(b, i) +
      ((b.classe || deduceClasse(b)) === "subtitulo"
        ? renderSubsecaoProposal(b, i)
        : "") +
      '<div class="import-card-body">' +
      '<div class="import-segs-view">' +
      renderSubtipos(b.subtipos, b.conteudo) +
      "</div>" +
      '<div class="import-raw is-hidden" data-raw-mode="1">' +
      '<div class="import-raw-tb" role="toolbar" aria-label="Ferramentas de listas (texto)">' +
      '<span class="import-raw-tb-hint">Listas e níveis (só o texto, não a estrutura de seções):</span>' +
      '<button type="button" class="secondary-mini import-tx-tool" data-import-tx-tool="bullet" title="Itens com marcador">• Marcadores</button>' +
      '<button type="button" class="secondary-mini import-tx-tool" data-import-tx-tool="ol1" title="Numeração 1. 2. 3.">1. 2. 3.</button>' +
      '<button type="button" class="secondary-mini import-tx-tool" data-import-tx-tool="ola" title="a) b) c)">a) b) c)</button>' +
      '<button type="button" class="secondary-mini import-tx-tool" data-import-tx-tool="oli" title="i. ii. iii. (romano)">i. ii. iii.</button>' +
      '<button type="button" class="secondary-mini import-tx-tool" data-import-tx-tool="indent" title="Aumentar nível (2 espaços)">Nível +</button>' +
      '<button type="button" class="secondary-mini import-tx-tool" data-import-tx-tool="outdent" title="Diminuir nível">Nível −</button>' +
      '<button type="button" class="secondary-mini import-raw-close" data-raw-close="1" title="Salvar alterações e voltar aos segmentos">✓ Salvar e fechar</button>' +
      "</div>" +
      '<textarea id="import-raw-ta-' +
      i +
      '" name="import-raw-ta-' +
      i +
      '" class="import-raw-ta" data-i="' +
      i +
      '" data-field="conteudo" rows="6">' +
      esc(b.conteudo || "") +
      "</textarea>" +
      "</div>" +
      "</div>" +
      "</article>"
    );
  }

  function sugestaoIndiceFigTab(tipo, prefixo, ord) {
    const t = (tipo || "").toLowerCase();
    if (t === "figura") return "Figura " + prefixo + "." + ord;
    if (t === "tabela") return "Tabela " + prefixo + "." + ord;
    return "";
  }

  function prefixoHierarquiaSec(numeroAlvo) {
    const n = String(numeroAlvo == null ? "" : numeroAlvo).trim();
    return (n || curSecStr || "1").split(".")[0] || "1";
  }

  function renderFiguraCard(b, i, indiceSug) {
    const hasImg = b.image_b64 && b.image_mime;
    const idxRow = indiceSug
      ? '<div class="import-meta-row">' +
        '<label class="mini-label" for="imp-fig-' +
        i +
        '-idx">Índice</label>' +
        '<input id="imp-fig-' +
        i +
        '-idx" type="text" class="import-indice-readonly" readonly tabindex="-1" ' +
        ' value="' +
        esc(indiceSug) +
        '" title="Sugestão: numeração por capítulo (primeiro nível do índice da seção) e ordem no lote, somando o que já existe nesta seção."></div>'
      : "";
    const mimeSub = esc(String(b.image_mime || "").split("/")[1] || "img");
    let thumb;
    if (hasImg) {
      const dataUrl =
        "data:" +
        String(b.image_mime || "").trim() +
        ";base64," +
        String(b.image_b64 || "");
      thumb =
        '<img src="' +
        esc(dataUrl) +
        '" alt="Pré-visualização da figura detectada" class="fig-thumb" loading="lazy" decoding="async" />' +
        '<span class="import-fig-thumb-ready-mime">' +
        mimeSub +
        "</span>";
    } else {
      thumb =
        '<div class="import-fig-placeholder">Sem imagem<br><small>preencha após importar</small></div>';
    }
    return (
      '<article class="import-card import-card-figura" data-i="' +
      i +
      '">' +
      renderCardHeader(b, i) +
      '<div class="import-card-body import-card-2col import-card-2col-reverse">' +
      '<div class="import-meta-fields">' +
      idxRow +
      '<div class="import-meta-row">' +
      '<label class="mini-label" for="imp-fig-' +
      i +
      '-leg">Legenda</label>' +
      '<textarea id="imp-fig-' +
      i +
      '-leg" rows="1" class="import-meta-textarea auto-grow" data-i="' +
      i +
      '" data-field="legenda" placeholder="ex.: Vista aérea da obra">' +
      esc(b.legenda || "") +
      "</textarea>" +
      "</div>" +
      '<div class="import-meta-row">' +
      '<label class="mini-label" for="imp-fig-' +
      i +
      '-fonte">Fonte</label>' +
      '<input id="imp-fig-' +
      i +
      '-fonte" type="text" data-i="' +
      i +
      '" data-field="fonte" value="' +
      esc(b.fonte || "") +
      '" placeholder="ex.: Concremat 2025">' +
      "</div>" +
      "</div>" +
      '<div class="import-fig-thumb">' +
      thumb +
      "</div>" +
      "</div>" +
      "</article>"
    );
  }

  function renderTabelaCard(b, i, indiceSug) {
    const idxRow = indiceSug
      ? '<div class="import-meta-row">' +
        '<label class="mini-label" for="imp-tab-' +
        i +
        '-idx">Índice</label>' +
        '<input id="imp-tab-' +
        i +
        '-idx" type="text" class="import-indice-readonly" readonly tabindex="-1" ' +
        ' value="' +
        esc(indiceSug) +
        '" title="Sugestão: numeração por capítulo (primeiro nível do índice da seção) e ordem no lote, somando o que já existe nesta seção."></div>'
      : "";
    return (
      '<article class="import-card import-card-tabela" data-i="' +
      i +
      '">' +
      renderCardHeader(b, i) +
      '<div class="import-card-body">' +
      '<div class="import-card-2col import-card-2col-reverse">' +
      '<div class="import-meta-fields">' +
      idxRow +
      '<div class="import-meta-row">' +
      '<label class="mini-label" for="imp-tab-' +
      i +
      '-leg">Legenda</label>' +
      '<textarea id="imp-tab-' +
      i +
      '-leg" rows="1" class="import-meta-textarea auto-grow" data-i="' +
      i +
      '" data-field="legenda" placeholder="ex.: Quantitativo de serviços">' +
      esc(b.legenda || "") +
      "</textarea>" +
      "</div>" +
      '<div class="import-meta-row">' +
      '<label class="mini-label" for="imp-tab-' +
      i +
      '-fonte">Fonte</label>' +
      '<input id="imp-tab-' +
      i +
      '-fonte" type="text" data-i="' +
      i +
      '" data-field="fonte" value="' +
      esc(b.fonte || "") +
      '" placeholder="ex.: Diário de obra">' +
      "</div>" +
      "</div>" +
      '<div class="import-tab-prev">' +
      renderTabelaPreview(b.tabela_preview) +
      "</div>" +
      "</div>" +
      '<details class="import-raw import-raw-tabela-full">' +
      "<summary>editar dados brutos da tabela</summary>" +
      '<textarea id="import-raw-ta-' +
      i +
      '" name="import-raw-ta-' +
      i +
      '" class="import-raw-ta" data-i="' +
      i +
      '" data-field="conteudo" rows="8">' +
      esc(b.conteudo || "") +
      "</textarea>" +
      "</details>" +
      "</div>" +
      "</article>"
    );
  }

  function renderCard(b, i, indiceSug) {
    const tipo = (b.tipo || "texto").toLowerCase();
    if (tipo === "figura") return renderFiguraCard(b, i, indiceSug || "");
    if (tipo === "tabela") return renderTabelaCard(b, i, indiceSug || "");
    return renderTextoCard(b, i);
  }

  function renderSecaoHeader(key, group) {
    const secId = domIdSuffix(key.key);
    const numero = key.numero || SECAO_FALLBACK_NUM;
    const titulo = key.titulo || SECAO_FALLBACK_TIT;
    const acao = acaoSecao(numero);
    const acaoLabelTxt = acaoLabel(acao);
    const indices = group.map((g) => g.idx).join(",");
    return (
      '<header class="import-secao-hdr" data-acao="' +
      esc(acao) +
      '" data-key="' +
      esc(key.key) +
      '" data-indices="' +
      esc(indices) +
      '">' +
      '<button type="button" class="import-secao-toggle" aria-expanded="true" title="Recolher/expandir seção">▾</button>' +
      '<div class="import-secao-id">' +
      '<span class="import-secao-num-lbl">SEÇÃO</span>' +
      '<input type="text" id="import-secao-num-' +
      secId +
      '" name="import-secao-num-' +
      secId +
      '" class="import-secao-num" data-key="' +
      esc(key.key) +
      '" data-section-field="secao_numero" value="' +
      esc(numero) +
      '" aria-label="Número da seção">' +
      '<input type="text" id="import-secao-titulo-' +
      secId +
      '" name="import-secao-titulo-' +
      secId +
      '" class="import-secao-titulo" data-key="' +
      esc(key.key) +
      '" data-section-field="secao_titulo" value="' +
      esc(titulo) +
      '" aria-label="Título da seção">' +
      "</div>" +
      '<span class="import-secao-badge" data-acao="' +
      esc(acao) +
      '">' +
      esc(acaoLabelTxt) +
      "</span>" +
      '<span class="import-secao-count">' +
      group.length +
      " bloco(s)</span>" +
      '<div class="import-secao-bulk">' +
      '<button type="button" class="secondary-mini import-secao-bulk-btn" data-bulk="on" data-key="' +
      esc(key.key) +
      '" title="Marcar todos desta seção">✓ todos</button>' +
      '<button type="button" class="secondary-mini import-secao-bulk-btn" data-bulk="off" data-key="' +
      esc(key.key) +
      '" title="Desmarcar todos desta seção">✗ nenhum</button>' +
      "</div>" +
      "</header>"
    );
  }

  function groupBySecao() {
    const groups = new Map();
    importBlocks.forEach((b, idx) => {
      const numero = String(b.secao_numero || "").trim();
      const key = numero || "__atual__";
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          numero,
          titulo: String(b.secao_titulo || "").trim(),
          items: [],
        });
      }
      groups.get(key).items.push({ idx, b });
    });
    return Array.from(groups.values());
  }

  function renderReview() {
    if (!importBlocks.length) {
      review.classList.add("is-hidden");
      list.innerHTML = "";
      summary.textContent = "";
      return;
    }
    review.classList.remove("is-hidden");
    const ssBlocos = document.getElementById("ss-blocos");
    if (ssBlocos) ssBlocos.classList.remove("is-hidden");
    const groups = groupBySecao();
    const html = groups
      .map((g) => {
        const secN =
          g.key === "__atual__" || !String(g.numero || "").trim()
            ? curSecStr
            : String(g.numero).trim();
        const pfx = prefixoHierarquiaSec(secN);
        const isAlvoAtual =
          g.key === "__atual__" || !g.numero || secN === curSecStr;
        let runFig = isAlvoAtual ? figBasePage : 0;
        let runTab = isAlvoAtual ? tabBasePage : 0;
        const cards = g.items
          .map(({ idx, b }) => {
            const t = (b.tipo || "texto").toLowerCase();
            if (t === "figura") {
              runFig += 1;
              return renderCard(
                b,
                idx,
                sugestaoIndiceFigTab("figura", pfx, runFig),
              );
            }
            if (t === "tabela") {
              runTab += 1;
              return renderCard(
                b,
                idx,
                sugestaoIndiceFigTab("tabela", pfx, runTab),
              );
            }
            return renderCard(b, idx, "");
          })
          .join("");
        const head = renderSecaoHeader(
          { key: g.key, numero: g.numero, titulo: g.titulo },
          g.items,
        );
        return (
          '<section class="import-secao" data-key="' +
          esc(g.key) +
          '">' +
          head +
          '<div class="import-secao-body">' +
          cards +
          "</div>" +
          "</section>"
        );
      })
      .join("");
    window.requestAnimationFrame(() => {
      list.innerHTML = html;
      updateSummary();
      list.querySelectorAll(".auto-grow").forEach((el) => {
        el.style.height = "auto";
        el.style.height = el.scrollHeight + "px";
      });
    });
  }

  function updateSummary() {
    const total = importBlocks.length;
    const sel = importBlocks.filter((b) => b.selecionado !== false).length;
    const baixos = importBlocks.filter(
      (b) => Number(b.confianca || 0) < 0.7,
    ).length;
    let txt = sel + " de " + total + " selecionado(s)";
    if (baixos) txt += " · " + baixos + " com confiança baixa";
    summary.textContent = txt;
  }

  function syncImportReviewDomToBlocks() {
    list.querySelectorAll("[data-field][data-i]").forEach((el) => {
      const idx = Number(el.dataset.i);
      if (!Number.isFinite(idx) || !importBlocks[idx]) return;
      const field = el.dataset.field;
      if (!field) return;
      importBlocks[idx][field] = el.type === "checkbox" ? el.checked : el.value;
    });
    list.querySelectorAll(".import-card-check").forEach((chk) => {
      const idx = Number(chk.dataset.i);
      if (Number.isFinite(idx) && importBlocks[idx]) {
        importBlocks[idx].selecionado = chk.checked;
      }
    });
    list
      .querySelectorAll(".import-secao-num, .import-secao-titulo")
      .forEach((el) => {
        const key = el.dataset.key;
        const sectionField = el.dataset.sectionField;
        if (!key || !sectionField) return;
        const value = el.value;
        importBlocks.forEach((b) => {
          const k = String(b.secao_numero || "").trim() || "__atual__";
          if (k === key) b[sectionField] = value;
        });
      });
  }

  function blocksPayloadForConfirm(rows) {
    return rows.map((b) => {
      const tipo = String(b.tipo || "texto")
        .trim()
        .toLowerCase();
      const out = {
        tipo,
        titulo: b.titulo != null ? String(b.titulo) : "",
        conteudo: b.conteudo != null ? String(b.conteudo) : "",
        legenda: b.legenda != null ? String(b.legenda) : "",
        fonte: b.fonte != null ? String(b.fonte) : "",
        secao_numero:
          b.secao_numero != null ? String(b.secao_numero).trim() : "",
        secao_titulo:
          b.secao_titulo != null ? String(b.secao_titulo).trim() : "",
        selecionado: b.selecionado !== false,
      };
      const sid = b.secao_id;
      if (sid !== undefined && sid !== null && sid !== "") {
        out.secao_id = sid;
      }
      if (tipo === "figura") {
        if (b.image_b64) out.image_b64 = b.image_b64;
        if (b.image_mime) out.image_mime = String(b.image_mime);
        if (b.image_name) out.image_name = String(b.image_name);
      }
      return out;
    });
  }

  list.addEventListener("input", (ev) => {
    const el = ev.target;
    if (el && el.classList && el.classList.contains("auto-grow")) {
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    }
    if (el.dataset.field) {
      const idx = Number(el.dataset.i);
      if (!Number.isFinite(idx) || !importBlocks[idx]) return;
      const v = el.type === "checkbox" ? el.checked : el.value;
      importBlocks[idx][el.dataset.field] = v;
      if (el.dataset.field === "selecionado") updateSummary();
      return;
    }
    if (el.dataset.sectionField) {
      const key = el.dataset.key;
      const field = el.dataset.sectionField;
      const value = el.value;
      importBlocks.forEach((b) => {
        const k = String(b.secao_numero || "").trim() || "__atual__";
        if (k === key) b[field] = value;
      });
      if (field === "secao_numero") {
        const acao = acaoSecao(value);
        const header = el.closest(".import-secao-hdr");
        if (header) {
          header.dataset.acao = acao;
          const badge = header.querySelector(".import-secao-badge");
          if (badge) {
            badge.dataset.acao = acao;
            badge.textContent = acaoLabel(acao);
          }
          importBlocks.forEach((b) => {
            const k = String(b.secao_numero || "").trim() || "__atual__";
            if (k === value || (key === "__atual__" && !b.secao_numero))
              b.acao_secao = acao;
          });
        }
      }
    }
  });

  list.addEventListener("change", (ev) => {
    const el = ev.target;
    if (el.dataset.field === "tipo") {
      const idx = Number(el.dataset.i);
      if (!Number.isFinite(idx) || !importBlocks[idx]) return;
      importBlocks[idx].tipo = el.value;
      renderReview();
      return;
    }
    if (el.dataset.field === "classe") {
      const idx = Number(el.dataset.i);
      if (!Number.isFinite(idx) || !importBlocks[idx]) return;
      importBlocks[idx].classe = el.value;
      const card = el.closest(".import-card");
      if (card && importBlocks[idx]) {
        const novoHtml = renderCard(importBlocks[idx], idx);
        const temp = document.createElement("div");
        temp.innerHTML = novoHtml;
        const novoCard = temp.firstElementChild;
        if (novoCard) card.replaceWith(novoCard);
      }
      return;
    }
    if (el.dataset.field === "selecionado") {
      const idx = Number(el.dataset.i);
      if (Number.isFinite(idx) && importBlocks[idx]) {
        importBlocks[idx].selecionado = el.checked;
        updateSummary();
      }
    }
  });

  list.addEventListener("click", (ev) => {
    const txTool = ev.target.closest(".import-tx-tool");
    if (txTool && list.contains(txTool) && window.sraImportTextoTool) {
      const raw = txTool.closest(".import-raw");
      const ta = raw && raw.querySelector(".import-raw-ta");
      if (ta) {
        window.sraImportTextoTool(
          ta,
          txTool.getAttribute("data-import-tx-tool"),
        );
        ta.dispatchEvent(new Event("input", { bubbles: true }));
      }
      ev.preventDefault();
      return;
    }
    const segChip = ev.target.closest(".seg-chip[data-seg-toggle]");
    if (segChip) {
      const card = segChip.closest(".import-card");
      if (card) {
        const raw = card.querySelector(".import-raw[data-raw-mode]");
        if (raw) {
          raw.classList.remove("is-hidden");
          const ta = raw.querySelector(".import-raw-ta");
          if (ta) {
            try {
              ta.focus({ preventScroll: true });
            } catch (e) {
              ta.focus();
            }
          }
        }
      }
      ev.preventDefault();
      return;
    }
    const rawClose = ev.target.closest(".import-raw-close[data-raw-close]");
    if (rawClose) {
      const card = rawClose.closest(".import-card");
      if (card) {
        const raw = card.querySelector(".import-raw[data-raw-mode]");
        if (raw) {
          const ta = raw.querySelector(".import-raw-ta");
          if (ta) {
            const idx = Number(ta.dataset.i);
            if (Number.isFinite(idx) && importBlocks[idx]) {
              importBlocks[idx].conteudo = ta.value;
            }
          }
          raw.classList.add("is-hidden");
          const i = Number(card.getAttribute("data-i"));
          if (Number.isFinite(i) && importBlocks[i]) {
            const segsView = card.querySelector(".import-segs-view");
            if (segsView) {
              segsView.innerHTML = renderSubtipos(
                importBlocks[i].subtipos,
                importBlocks[i].conteudo,
              );
            }
          }
        }
      }
      ev.preventDefault();
      return;
    }
    const toggle = ev.target.closest(".import-secao-toggle");
    if (toggle) {
      const sec = toggle.closest(".import-secao");
      if (!sec) return;
      const body = sec.querySelector(".import-secao-body");
      const open = !sec.classList.contains("is-collapsed");
      sec.classList.toggle("is-collapsed", open);
      toggle.setAttribute("aria-expanded", String(!open));
      toggle.textContent = open ? "▸" : "▾";
      if (body) body.style.display = open ? "none" : "";
      return;
    }
    const bulkBtn = ev.target.closest(".import-secao-bulk-btn");
    if (bulkBtn) {
      const value = bulkBtn.dataset.bulk === "on";
      const header = bulkBtn.closest(".import-secao-hdr");
      const indicesRaw =
        header && header.dataset.indices
          ? String(header.dataset.indices).trim()
          : "";
      if (indicesRaw) {
        indicesRaw.split(",").forEach((part) => {
          const idx = Number(String(part).trim());
          if (Number.isFinite(idx) && importBlocks[idx]) {
            importBlocks[idx].selecionado = value;
          }
        });
      } else {
        const key = bulkBtn.dataset.key;
        importBlocks.forEach((b) => {
          const k = String(b.secao_numero || "").trim() || "__atual__";
          if (k === key) b.selecionado = value;
        });
      }
      const sec = bulkBtn.closest(".import-secao");
      if (sec) {
        sec.querySelectorAll(".import-card-check").forEach((c) => {
          c.checked = value;
        });
      }
      updateSummary();
    }
  });

  if (allOnBtn)
    allOnBtn.addEventListener("click", () => {
      importBlocks.forEach((b) => {
        b.selecionado = true;
      });
      list.querySelectorAll(".import-card-check").forEach((c) => {
        c.checked = true;
      });
      updateSummary();
    });
  if (allOffBtn)
    allOffBtn.addEventListener("click", () => {
      importBlocks.forEach((b) => {
        b.selecionado = false;
      });
      list.querySelectorAll(".import-card-check").forEach((c) => {
        c.checked = false;
      });
      updateSummary();
    });

  async function sincronizarIndices() {
    if (!syncIdxBtn) return;
    const primeiro = list.querySelector(".import-secao-num");
    if (!primeiro) {
      alert("Nenhum índice de seção disponível para sincronizar.");
      return;
    }
    const base = String(primeiro.value || "").trim();
    if (!base) {
      alert("Informe o primeiro índice de seção antes de sincronizar.");
      primeiro.focus();
      return;
    }
    syncImportReviewDomToBlocks();
    syncIdxBtn.disabled = true;
    syncIdxBtn.textContent = "Sincronizando...";
    status.textContent = "Sincronizando índices...";
    status.dataset.kind = "info";
    try {
      const relId = readSecaoEditData("relId", 0);
      const secId = readSecaoEditData("secId", 0);
      const resp = await fetch(
        "/relatorios/" +
          relId +
          "/secoes/" +
          secId +
          "/importar/sincronizar-indices",
        {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            primeiro_numero: base,
            blocks: importBlocks,
          }),
        },
      );
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "Falha ao sincronizar índices.");
      }
      if (!data.blocks || !Array.isArray(data.blocks)) {
        throw new Error("Resposta inválida do servidor.");
      }
      importBlocks = data.blocks;
      renderReview();
      updateSummary();
      status.textContent = "Índices sincronizados.";
      status.dataset.kind = "success";
    } catch (err) {
      status.textContent = "Falha ao sincronizar índices.";
      status.dataset.kind = "error";
      alert(
        "Erro ao sincronizar índices: " +
          (err && err.message ? err.message : String(err)),
      );
    } finally {
      syncIdxBtn.disabled = false;
      syncIdxBtn.textContent = syncIdxLabel || "Sincronizar índices";
    }
  }

  if (syncIdxBtn)
    syncIdxBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      sincronizarIndices();
    });

  function aplicarSugestaoSecaoAtual() {
    if (!curSecStr) return;
    importBlocks = importBlocks.map((b) => {
      const n = String(b.secao_numero || "").trim();
      if (!n) return { ...b, secao_numero: curSecStr };
      return b;
    });
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (importAnaliseEmCurso) return;
    const file = fileIn.files && fileIn.files[0];
    if (!file) return;
    const submitAnalisar = form.querySelector('button[type="submit"]');
    importAnaliseEmCurso = true;
    if (submitAnalisar) submitAnalisar.disabled = true;
    try {
      if (window.SRAComplementos) {
        const go = await window.SRAComplementos.confirmarComChave(
          "importacao_assistida_analise",
        );
        if (!go) return;
      }
      const fd = new FormData();
      fd.append("arquivo", file);
      status.textContent = "Analisando...";
      try {
        const relId = readSecaoEditData("relId", 0);
        const secId = readSecaoEditData("secId", 0);
        const resp = await fetch(
          "/relatorios/" + relId + "/secoes/" + secId + "/importar/analisar",
          {
            method: "POST",
            body: fd,
            credentials: "same-origin",
            headers: { Accept: "application/json" },
          },
        );
        const data = await resp.json();
        if (!resp.ok)
          throw new Error(data.detail || "Falha ao analisar arquivo.");
        importBlocks = (data.blocks || []).map((b) => ({
          ...b,
          selecionado: true,
        }));
        aplicarSugestaoSecaoAtual();
        renderReview();
        const baixos = importBlocks.filter(
          (b) => Number(b.confianca || 0) < 0.7,
        ).length;
        status.textContent =
          importBlocks.length +
          " bloco(s) detectado(s)" +
          (baixos ? ", " + baixos + " para revisar com atenção." : ".");
      } catch (err) {
        status.textContent = err.message;
        importBlocks = [];
        renderReview();
      }
    } finally {
      importAnaliseEmCurso = false;
      if (submitAnalisar) submitAnalisar.disabled = false;
    }
  });

  confirmBtn.addEventListener("click", async () => {
    if (importConfirmEmCurso) return;
    syncImportReviewDomToBlocks();
    const selected = importBlocks.filter((b) => b.selecionado !== false);
    if (!selected.length) {
      alert("Selecione ao menos um bloco para importar.");
      return;
    }
    if (window.SRAComplementos) {
      const go = await window.SRAComplementos.confirmarComChave(
        "importacao_assistida_confirmar",
      );
      if (!go) return;
    }
    importConfirmEmCurso = true;
    confirmBtn.disabled = true;
    status.textContent = "Importando...";
    try {
      const relId = readSecaoEditData("relId", 0);
      const secId = readSecaoEditData("secId", 0);
      const respSel = document.getElementById("sel-sec-responsavel");
      const responsavelId = respSel ? respSel.value : "";
      const resp = await fetch(
        "/relatorios/" + relId + "/secoes/" + secId + "/importar/confirmar",
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({
            blocks: blocksPayloadForConfirm(selected),
            responsavel_id: responsavelId,
          }),
        },
      );
      let data = {};
      try {
        data = await resp.json();
      } catch (e2) {
        data = {};
      }
      if (!resp.ok) {
        const det = data.detail;
        const msg =
          typeof det === "string"
            ? det
            : Array.isArray(det)
              ? det.map((x) => x.msg || x).join("; ")
              : "Falha ao importar blocos.";
        throw new Error(msg || "Falha ao importar blocos.");
      }
      let msg =
        data.created +
        " bloco(s) importado(s)" +
        (data.section_changes
          ? " e " + data.section_changes + " ajuste(s) de seção."
          : ".");
      const ps = data.por_secao;
      if (Array.isArray(ps) && ps.length > 1) {
        msg +=
          " · Gravados por secção: " +
          ps
            .map((x) => (x.numero || "?") + " (" + (x.inseridos ?? 0) + ")")
            .join(", ") +
          ". Abra cada secção no menu lateral para ver a tabela dessa secção.";
      }
      status.textContent = msg;
      const destinoOutraSecao =
        Array.isArray(ps) &&
        ps.length === 1 &&
        Number(ps[0].secao_id) !== uploadPageSecId &&
        Number(data.created) > 0;
      if (destinoOutraSecao) {
        window.location.href =
          "/relatorios/" +
          uploadPageRelId +
          "/secoes/" +
          Number(ps[0].secao_id) +
          "/upload-conteudo";
        return;
      }
      window.location.reload();
    } catch (err) {
      status.textContent = err.message;
      importConfirmEmCurso = false;
      confirmBtn.disabled = false;
    }
  });
})();

// ---- Botão fullscreen preview ----
(function () {
  const btnFullscreen = document.getElementById("btn-preview-fullscreen");
  if (btnFullscreen) {
    btnFullscreen.addEventListener("click", function () {
      const frame = document.getElementById("preview-frame");
      if (frame && frame.src) {
        window.open(frame.src, "_blank");
      }
    });
  }
})();
