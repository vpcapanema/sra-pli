(function () {
  var selects = document.querySelectorAll(".sumario-responsavel-select");
  if (!selects.length) return;
  function msgErro(resp) {
    return resp
      .json()
      .then(function (j) {
        return j && j.detail ? j.detail : "Falha ao atualizar responsável.";
      })
      .catch(function () {
        return "Falha ao atualizar responsável.";
      });
  }
  function aliasNome(nome) {
    var raw = (nome || "").trim();
    if (!raw || raw === "—") return "—";
    var partes = raw.split(/\s+/).filter(Boolean);
    if (partes.length <= 1) return raw;
    var primeiro = partes[0];
    var conectores = {
      da: true,
      de: true,
      do: true,
      das: true,
      dos: true,
      e: true,
    };
    var ultimo = "";
    for (var i = partes.length - 1; i > 0; i -= 1) {
      if (!conectores[partes[i].toLowerCase()]) {
        ultimo = partes[i];
        break;
      }
    }
    return ultimo && ultimo !== primeiro ? primeiro + " " + ultimo : primeiro;
  }
  Array.prototype.forEach.call(selects, function (sel) {
    var picker = sel.closest(".responsavel-picker");
    var display = picker ? picker.querySelector(".responsavel-display") : null;
    sel.dataset.valorOriginal = sel.value || "";
    if (display) {
      display.title = display.textContent.trim();
      display.textContent = aliasNome(display.textContent);
      display.addEventListener("click", function () {
        var open = !picker.classList.contains("is-open");
        picker.classList.toggle("is-open", open);
        display.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) sel.focus();
      });
    }
    sel.addEventListener("change", function () {
      var fd = new FormData();
      fd.append("responsavel_id", sel.value || "");
      fd.append("retorno", "sumario");
      sel.disabled = true;
      fetch(
        "/relatorios/" +
          sel.getAttribute("data-rel-id") +
          "/secoes/" +
          sel.getAttribute("data-sec-id") +
          "/responsavel",
        {
          method: "POST",
          body: fd,
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        },
      )
        .then(function (resp) {
          if (!resp.ok) {
            return msgErro(resp).then(function (msg) {
              throw new Error(msg);
            });
          }
          sel.dataset.valorOriginal = sel.value || "";
          if (display) {
            var nomeSelecionado =
              sel.options[sel.selectedIndex] &&
              sel.options[sel.selectedIndex].text
                ? sel.options[sel.selectedIndex].text
                : "—";
            display.title = nomeSelecionado;
            display.textContent = aliasNome(nomeSelecionado);
            picker.classList.remove("is-open");
            display.setAttribute("aria-expanded", "false");
          }
        })
        .catch(function (err) {
          sel.value = sel.dataset.valorOriginal || "";
          window.alert(err.message || "Falha ao atualizar responsável.");
        })
        .finally(function () {
          sel.disabled = false;
        });
    });
  });
})();

(function () {
  var rows = Array.prototype.slice.call(
    document.querySelectorAll("[data-sumario-row]"),
  );
  if (!rows.length) return;

  function level(row) {
    return parseInt(row.getAttribute("data-sumario-nivel") || "1", 10);
  }

  function numero(row) {
    return row.getAttribute("data-sumario-numero") || "";
  }

  function isDescendant(row, parentNumber) {
    return numero(row).indexOf(parentNumber + ".") === 0;
  }

  function directChild(row, parentNumber, parentLevel) {
    return isDescendant(row, parentNumber) && level(row) === parentLevel + 1;
  }

  function setExpanded(row, expanded) {
    var btn = row.querySelector(".sumario-toggle");
    row.dataset.sumarioExpanded = expanded ? "1" : "0";
    if (btn) {
      btn.textContent = expanded ? "▾" : "▸";
      btn.setAttribute("aria-expanded", expanded ? "true" : "false");
      btn.setAttribute(
        "aria-label",
        (expanded ? "Recolher seção " : "Expandir seção ") + numero(row),
      );
    }
  }

  function refreshVisibility() {
    rows.forEach(function (row) {
      if (level(row) === 1) {
        row.classList.remove("is-hidden");
        return;
      }
      var visible = false;
      for (var i = rows.indexOf(row) - 1; i >= 0; i -= 1) {
        var candidate = rows[i];
        if (level(candidate) >= level(row)) continue;
        if (directChild(row, numero(candidate), level(candidate))) {
          visible =
            candidate.dataset.sumarioExpanded === "1" &&
            !candidate.classList.contains("is-hidden");
          break;
        }
      }
      row.classList.toggle("is-hidden", !visible);
    });
  }

  rows.forEach(function (row) {
    setExpanded(row, false);
    var btn = row.querySelector(".sumario-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var expanded = row.dataset.sumarioExpanded !== "1";
      setExpanded(row, expanded);
      if (!expanded) {
        rows.forEach(function (candidate) {
          if (candidate !== row && isDescendant(candidate, numero(row))) {
            setExpanded(candidate, false);
          }
        });
      }
      refreshVisibility();
    });
  });
  refreshVisibility();
})();

(function () {
  var inner = document.getElementById("rel-sum-preview-zoom-inner");
  var frame = document.getElementById("preview-frame");
  var reloadBtn = document.getElementById("rel-sum-btn-preview-reload");
  var zIn = document.getElementById("rel-sum-preview-zoom-in");
  var zOut = document.getElementById("rel-sum-preview-zoom-out");
  var fullscreenBtn = document.getElementById("rel-sum-btn-preview-fullscreen");
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
  if (reloadBtn && frame.dataset.src) {
    reloadBtn.addEventListener("click", function () {
      var base = frame.dataset.src;
      frame.src =
        base + (base.indexOf("?") >= 0 ? "&" : "?") + "t=" + Date.now();
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
  if (fullscreenBtn) {
    fullscreenBtn.addEventListener("click", function () {
      var previewSection = document.getElementById("ss-preview");
      if (!document.fullscreenElement) {
        previewSection.requestFullscreen().catch(function (err) {
          console.error("Erro ao ativar tela cheia:", err);
        });
      } else {
        document.exitFullscreen();
      }
    });
  }
  applyZoom();
})();
(function () {
  var botoes = document.querySelectorAll(
    "button.btn-add-sub[data-add-sub-pai]",
  );
  if (!botoes.length) return;
  function coletarNumeros(tbody) {
    var nums = [];
    var alvos = tbody.querySelectorAll(
      "tr:not(.row-nova-sub) td:first-child strong",
    );
    Array.prototype.forEach.call(alvos, function (el) {
      var t = (el.textContent || "").trim();
      if (t) nums.push(t);
    });
    return nums;
  }
  function calcularSugestoes(secaoNumero, todos) {
    var partes = secaoNumero.split(".");
    var nivelClicado = partes.length;
    var opcoes = [];
    var prefChild = secaoNumero + ".";
    var maxFilho = 0;
    todos.forEach(function (num) {
      var ps = num.split(".");
      if (ps.length === nivelClicado + 1 && num.indexOf(prefChild) === 0) {
        var w = parseInt(ps[ps.length - 1], 10);
        if (!isNaN(w) && w > maxFilho) maxFilho = w;
      }
    });
    opcoes.push({
      modo: "child",
      numero: prefChild + (maxFilho + 1),
      nivel: nivelClicado + 1,
      rotulo: "subseção",
    });
    for (var k = nivelClicado; k >= 1; k--) {
      var ult = parseInt(partes[k - 1], 10);
      if (isNaN(ult)) continue;
      var prefixoK = partes.slice(0, k - 1).join(".");
      var num = (prefixoK ? prefixoK + "." : "") + (ult + 1);
      var rotulo;
      if (k === nivelClicado) rotulo = "mesma hierarquia";
      else if (k === 1) rotulo = "novo capítulo";
      else rotulo = "nível " + k;
      opcoes.push({
        modo: "sibling",
        numero: num,
        nivel: k,
        rotulo: rotulo,
      });
    }
    return opcoes;
  }
  function montarLinha(relId, paiId, opcoes) {
    var tr = document.createElement("tr");
    tr.setAttribute("data-pai-id", paiId);
    var tdNum = document.createElement("td");
    var sel = document.createElement("select");
    sel.className = "sub-modo";
    sel.title = "Selecione o índice da nova seção";
    sel.setAttribute("aria-label", "Índice da nova seção");
    opcoes.forEach(function (op) {
      var o = document.createElement("option");
      o.value = op.modo + ":" + op.numero;
      o.dataset.modo = op.modo;
      o.dataset.numero = op.numero;
      o.dataset.nivel = String(op.nivel);
      o.textContent = op.numero + " — " + op.rotulo;
      sel.appendChild(o);
    });
    tdNum.appendChild(sel);
    var tdTit = document.createElement("td");
    var input = document.createElement("input");
    input.type = "text";
    input.required = true;
    input.placeholder = "Título da nova seção";
    input.maxLength = 200;
    input.className = "sub-titulo";
    input.setAttribute("aria-label", "Título da nova seção");
    tdTit.appendChild(input);
    var tdResp = document.createElement("td");
    var tdBlk = document.createElement("td");
    var tdSt = document.createElement("td");
    var tdAct = document.createElement("td");
    var btnOk = document.createElement("button");
    btnOk.type = "button";
    btnOk.className = "link-quiet";
    btnOk.title = "Confirmar inclusão da seção";
    btnOk.setAttribute("aria-label", "Confirmar inclusão da seção");
    btnOk.textContent = "✔";
    var btnCancel = document.createElement("button");
    btnCancel.type = "button";
    btnCancel.className = "link-danger";
    btnCancel.setAttribute("data-cancelar-nova-sub", "");
    btnCancel.title = "Cancelar inclusão";
    btnCancel.setAttribute("aria-label", "Cancelar inclusão da seção");
    btnCancel.textContent = "✕";
    tdAct.appendChild(btnOk);
    tdAct.appendChild(document.createTextNode(" "));
    tdAct.appendChild(btnCancel);
    tr.appendChild(tdNum);
    tr.appendChild(tdTit);
    tr.appendChild(tdResp);
    tr.appendChild(tdBlk);
    tr.appendChild(tdSt);
    tr.appendChild(tdAct);
    function aplicarNivel() {
      var op = sel.options[sel.selectedIndex];
      var n = parseInt(op && op.dataset.nivel, 10);
      if (isNaN(n)) n = 1;
      tr.className = "row-nova-sub lvl-" + n;
    }
    aplicarNivel();
    sel.addEventListener("change", aplicarNivel);
    function submeter() {
      var titulo = input.value.trim();
      if (!titulo) {
        input.focus();
        return;
      }
      var op = sel.options[sel.selectedIndex];
      if (!op) return;
      var modo = op.dataset.modo;
      var numero = op.dataset.numero;
      var f = document.createElement("form");
      f.method = "post";
      f.style.display = "none";
      if (modo === "sibling") {
        f.action = "/relatorios/" + relId + "/secoes";
        var inN = document.createElement("input");
        inN.type = "hidden";
        inN.name = "numero";
        inN.value = numero;
        f.appendChild(inN);
      } else {
        f.action = "/relatorios/" + relId + "/secoes/" + paiId + "/subsecao";
      }
      var inT = document.createElement("input");
      inT.type = "hidden";
      inT.name = "titulo";
      inT.value = titulo;
      f.appendChild(inT);
      document.body.appendChild(f);
      f.submit();
    }
    btnOk.addEventListener("click", submeter);
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        submeter();
      }
    });
    return { tr: tr, input: input };
  }
  Array.prototype.forEach.call(botoes, function (btn) {
    btn.addEventListener("click", function () {
      var paiId = btn.getAttribute("data-add-sub-pai");
      var relId = btn.getAttribute("data-add-sub-rel");
      var trAtual = btn.closest("tr");
      if (!trAtual || !trAtual.parentNode) return;
      var seguinte = trAtual.nextElementSibling;
      if (
        seguinte &&
        seguinte.classList.contains("row-nova-sub") &&
        seguinte.getAttribute("data-pai-id") === paiId
      ) {
        var jaInp = seguinte.querySelector("input.sub-titulo");
        if (jaInp) jaInp.focus();
        return;
      }
      var strongPai = trAtual.querySelector("td:first-child strong");
      var paiNumero = strongPai ? (strongPai.textContent || "").trim() : "";
      if (!paiNumero) return;
      var todos = coletarNumeros(trAtual.parentNode);
      var opcoes = calcularSugestoes(paiNumero, todos);
      var nova = montarLinha(relId, paiId, opcoes);
      trAtual.parentNode.insertBefore(nova.tr, trAtual.nextSibling);
      nova.input.focus();
    });
  });
  document.addEventListener("click", function (ev) {
    var alvo = ev.target;
    if (alvo && alvo.matches && alvo.matches("[data-cancelar-nova-sub]")) {
      var tr = alvo.closest("tr.row-nova-sub");
      if (tr && tr.parentNode) tr.parentNode.removeChild(tr);
    }
  });
})();
