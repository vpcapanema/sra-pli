/**
 * Complementos SRA: modal de confirmação reutilizável e integração com GET /processos/fluxo-confirmacao/{chave}.
 * Depende dos elementos sra-cpl-confirm* em base.html.
 */
(function () {
  "use strict";

  var PENDING = null;
  /** Atributo HTML para o segundo passo do submit (evita reabrir o modal). */
  var SKIP = "data-sra-confirm-skip";

  function byId(id) {
    return document.getElementById(id);
  }

  function setText(id, value) {
    var el = byId(id);
    if (el) el.textContent = value != null ? String(value) : "";
  }

  function setLeadSourceLine(value) {
    var el = byId("sra-cpl-confirm-lead-source");
    if (!el) {
      return;
    }
    var t = value != null ? String(value).trim() : "";
    if (!t) {
      el.textContent = "";
      el.classList.add("is-hidden");
      el.setAttribute("aria-hidden", "true");
      return;
    }
    el.textContent = "";
    var s = document.createElement("strong");
    s.textContent = t;
    el.appendChild(s);
    el.classList.remove("is-hidden");
    el.setAttribute("aria-hidden", "false");
  }

  /** Resumo legível da fonte de sumário (dashboard — novo relatório). */
  function relatorioCriarSourceLine(form) {
    var r = form.querySelector('input[name="fonte_secoes"]:checked');
    if (!r) {
      return "";
    }
    if (r.value === "upload") {
      var fin = form.querySelector('input[name="pdf_upload"]');
      var f = fin && fin.files && fin.files[0];
      return f ? f.name : "Nenhum arquivo de upload selecionado";
    }
    if (r.value === "pdf_disponivel") {
      var sel = form.querySelector('select[name="pdf_disponivel"]');
      if (!sel) {
        return "";
      }
      var opt = sel.options[sel.selectedIndex];
      if (!opt || !String(opt.value || "").trim()) {
        return "Nenhum relatório entregue selecionado";
      }
      return (opt.text || opt.value).trim();
    }
    return "";
  }

  function setDetailVisible(show) {
    var wrap = byId("sra-cpl-confirm-detail-wrap");
    var d = byId("sra-cpl-confirm-detail");
    if (!wrap) return;
    wrap.classList.toggle("is-hidden", !show);
    wrap.setAttribute("aria-hidden", show ? "false" : "true");
    if (d && !show) d.textContent = "";
  }

  function abrirComPayload(payload) {
    var p = payload || {};
    setText("sra-cpl-confirm-title", p.title || "Confirmar");
    setText("sra-cpl-confirm-lead", p.lead || "");
    if (Object.prototype.hasOwnProperty.call(p, "source_line")) {
      setLeadSourceLine(p.source_line);
    } else {
      setLeadSourceLine("");
    }
    setText("sra-cpl-confirm-detail", p.detail || "");
    setText("sra-cpl-ask", p.ask || "Deseja continuar?");
    setDetailVisible(Boolean(p.show_detail) && (p.detail || "").trim().length > 0);
    var w = byId("sra-cpl-confirm");
    if (w) w.classList.remove("is-hidden");
  }

  function fecharConfirm() {
    var w = byId("sra-cpl-confirm");
    if (w) w.classList.add("is-hidden");
  }

  function mergePayload(base, ov) {
    if (!ov) return base;
    var out = {};
    out.title = ov.title || base.title;
    out.lead = ov.lead || base.lead;
    out.detail = ov.detail != null && String(ov.detail).length ? ov.detail : base.detail;
    out.ask = ov.ask || base.ask;
    var sd = ov.show_detail;
    if (sd === true || sd === false) {
      out.show_detail = sd;
    } else {
      out.show_detail = base.show_detail;
    }
    if ((out.detail || "").trim().length > 0) {
      out.show_detail = true;
    }
    if (Object.prototype.hasOwnProperty.call(ov, "source_line")) {
      out.source_line = ov.source_line;
    } else if (base && Object.prototype.hasOwnProperty.call(base, "source_line")) {
      out.source_line = base.source_line;
    }
    return out;
  }

  function carregarChave(chave) {
    return fetch("/processos/fluxo-confirmacao/" + encodeURIComponent(chave), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }).then(function (r) {
      if (!r.ok) return Promise.reject(new Error("Fluxo desconhecido"));
      return r.json();
    });
  }

  function confirmarComChave(chave, override) {
    return carregarChave(chave)
      .then(function (j) {
        return abrirDireto(mergePayload(j, override));
      })
      .catch(function () {
        return abrirDireto(
          mergePayload(
            {
              title: "Confirmar",
              lead: "Não foi possível carregar o texto deste passo. Deseja continuar?",
              ask: "Continuar?",
              show_detail: false,
            },
            override
          )
        );
      });
  }

  function abrirDireto(p) {
    return new Promise(function (resolve) {
      PENDING = { resolve: resolve };
      abrirComPayload(p);
    });
  }

  function onCancel() {
    fecharConfirm();
    if (PENDING) {
      PENDING.resolve(false);
      PENDING = null;
    }
  }

  function onOk() {
    fecharConfirm();
    if (PENDING) {
      PENDING.resolve(true);
      PENDING = null;
    }
  }

  function initBotoesModal() {
    var ok = byId("sra-cpl-confirm-ok");
    var c = byId("sra-cpl-confirm-cancel");
    if (ok && !ok.dataset.sraWired) {
      ok.dataset.sraWired = "1";
      ok.addEventListener("click", onOk);
    }
    if (c && !c.dataset.sraWired) {
      c.dataset.sraWired = "1";
      c.addEventListener("click", onCancel);
    }
    var wrap = byId("sra-cpl-confirm");
    if (wrap && !wrap.dataset.sraWired) {
      wrap.dataset.sraWired = "1";
      wrap.addEventListener("click", function (e) {
        if (e.target === wrap) onCancel();
      });
    }
  }

  function initDataConfirmForms() {
    document.querySelectorAll("form[data-sra-confirm]").forEach(function (form) {
      if (form.dataset.sraWired) return;
      form.dataset.sraWired = "1";
      form.addEventListener("submit", function (e) {
        if (form.getAttribute(SKIP) === "1" || form.dataset.sraConfirmSkip === "1") {
          form.removeAttribute(SKIP);
          return;
        }
        var ch = form.getAttribute("data-sra-confirm");
        if (!ch) return;
        e.preventDefault();
        var ov = {
          title: form.getAttribute("data-sra-title"),
          lead: form.getAttribute("data-sra-lead"),
          detail: form.getAttribute("data-sra-detail"),
          ask: form.getAttribute("data-sra-ask"),
        };
        if (ch === "relatorio_criar") {
          ov.source_line = relatorioCriarSourceLine(form);
        }
        Object.keys(ov).forEach(function (k) {
          if (k === "source_line") {
            return;
          }
          if (ov[k] == null || ov[k] === "") {
            delete ov[k];
          }
        });
        confirmarComChave(ch, ov).then(function (sim) {
          if (!sim) return;
          if (form.getAttribute("data-sra-iniciar-acompanhamento") === "1" && window.SRAProcess && typeof window.SRAProcess.openTrackPendente === "function") {
            window.SRAProcess.openTrackPendente({ chave: ch });
          }
          form.setAttribute(SKIP, "1");
          if (form.requestSubmit) form.requestSubmit();
          else form.submit();
        });
      });
    });
  }

  function init() {
    initBotoesModal();
    initDataConfirmForms();
  }

  window.SRAComplementos = {
    init: init,
    carregarChave: carregarChave,
    confirmarComChave: confirmarComChave,
    abrirDireto: abrirDireto,
    fecharConfirm: fecharConfirm,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
