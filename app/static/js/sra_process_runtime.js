/**
 * Runtime do feedback de processo: SSE (/processos/eventos), modal de acompanhamento,
 * modais de fim e toasts. Complementa sra_process_ui.js (confirmacao) e sra_live_log.js.
 *
 * Os scripts carregam no <head>; nunca cachear getElementById no load — o body ainda nao existe.
 * Extensao: window.SRAProcessTrackDefaults ou SRAProcess.registerTrackDefaults({ chave: { … } }).
 */
(function () {
  "use strict";

  function el(id) {
    return document.getElementById(id);
  }

  var trackState = { lastTarefa: {}, lastGeral: {}, lastTarefaPct: {} };

  /** Evita o mesmo fim de processo duas vezes (ex.: HTML após redirect + replay SSE). */
  var omitSseFim = {};

  /** Textos por chave de fluxo (data-sra-confirm / process_key); extensível por página. */
  window.SRAProcessTrackDefaults = Object.assign(window.SRAProcessTrackDefaults || {}, {
    relatorio_criar: {
      tarefa: "Criação de relatório",
      mensagem:
        "A iniciar o processo no servidor; aguarde o avanço abaixo.",
    },
    relatorio_excluir: {
      tarefa: "Exclusão de relatório",
      mensagem:
        "A iniciar a exclusão no servidor; mapa das tabelas e etapas abaixo.",
    },
    secao_excluir: {
      tarefa: "Exclusão de subseção",
      mensagem: "A iniciar exclusão da seção e renumeração do sumário…",
    },
  });

  function esc(value) {
    var s = String(value == null ? "" : value);
    return s
      .replace(new RegExp("&", "g"), "&amp;")
      .replace(new RegExp("<", "g"), "&lt;")
      .replace(new RegExp(">", "g"), "&gt;")
      .replace(new RegExp('"', "g"), "&quot;");
  }

  function clampPct100(n) {
    var x = Math.round(Number(n));
    if (Number.isNaN(x)) {
      return 0;
    }
    return Math.max(0, Math.min(100, x));
  }

  function setOneBar(wrap, fill, pctEl, n) {
    if (!wrap || !fill || !pctEl) {
      return;
    }
    var p = clampPct100(n);
    fill.style.width = p + "%";
    pctEl.textContent = p + "%";
    wrap.setAttribute("aria-valuenow", String(p));
  }

  function mostrarModalFimProcesso(d) {
    var ids = [
      "sra-cpl-track",
      "sra-cpl-confirm",
      "sra-cpl-status-ok",
      "sra-cpl-status-partial",
      "sra-cpl-status-fail",
    ];
    ids.forEach(function (rid) {
      var w = el(rid);
      if (w) {
        w.classList.add("is-hidden");
      }
    });
    var out = d.outcome;
    if (out === "success") {
      var t = el("sra-cpl-status-ok-title");
      var m = el("sra-cpl-status-ok-message");
      var de = el("sra-cpl-status-ok-detail");
      var dw = el("sra-cpl-status-ok-detail-wrap");
      if (t) {
        t.textContent = d.titulo || "Operação concluída";
      }
      if (m) {
        m.textContent = d.mensagem || "";
      }
      var det = (d.detalhe || "").trim();
      if (de) {
        de.textContent = det;
      }
      if (dw) {
        dw.classList.toggle("is-hidden", !det);
        dw.setAttribute("aria-hidden", det ? "false" : "true");
      }
      var ok = el("sra-cpl-status-ok");
      if (ok) {
        ok.classList.remove("is-hidden");
      }
      return;
    }
    if (out === "partial") {
      var t2 = el("sra-cpl-status-partial-title");
      var m2 = el("sra-cpl-status-partial-message");
      var de2 = el("sra-cpl-status-partial-detail");
      var dw2 = el("sra-cpl-status-partial-detail-wrap");
      if (t2) {
        t2.textContent = d.titulo || "Conclusão com ressalvas";
      }
      if (m2) {
        m2.textContent = d.mensagem || "";
      }
      var det2 = (d.detalhe || "").trim();
      if (de2) {
        de2.textContent = det2;
      }
      if (dw2) {
        dw2.classList.toggle("is-hidden", !det2);
        dw2.setAttribute("aria-hidden", det2 ? "false" : "true");
      }
      var pel = el("sra-cpl-status-partial");
      if (pel) {
        pel.classList.remove("is-hidden");
      }
      return;
    }
    var tf = el("sra-cpl-status-fail-title");
    var mf = el("sra-cpl-status-fail-error");
    var deFail = el("sra-cpl-status-fail-detail");
    var h = el("sra-cpl-status-fail-hint");
    var dwf = el("sra-cpl-status-fail-detail-wrap");
    if (tf) {
      tf.textContent = d.titulo || "Operação interrompida";
    }
    if (mf) {
      mf.textContent = d.mensagem || "";
    }
    var detalheFalha = (d.detalhe || "").trim();
    if (deFail) {
      deFail.textContent = detalheFalha;
    }
    if (h) {
      h.textContent = d.recomendacao || h.textContent;
    }
    if (dwf) {
      dwf.classList.toggle("is-hidden", !detalheFalha);
      dwf.setAttribute("aria-hidden", detalheFalha ? "false" : "true");
    }
    var f = el("sra-cpl-status-fail");
    if (f) {
      f.classList.remove("is-hidden");
    }
  }

  function atualizarAcompanhamentoTratado(ev) {
    if (ev.kind === "server_log" || ev.kind === "connection") {
      return;
    }
    if (!ev.data || ev.data.channel !== "process") {
      return;
    }
    if (ev.kind !== "log" && ev.kind !== "process") {
      return;
    }
    var sraTrackWrap = el("sra-cpl-track");
    if (!sraTrackWrap) {
      return;
    }
    var elTrackTarefa = el("sra-cpl-now-tarefa");
    var elTrackSub = el("sra-cpl-now-sub");
    var elTrackSubWrap = el("sra-cpl-now-sub-wrap");
    var elTrackMsg = el("sra-cpl-now-msg");
    var elTrackHdrSub = el("sra-cpl-track-sub");
    var elBarGeral = el("sra-cpl-bar-geral");
    var elBarGeralFill = el("sra-cpl-bar-geral-fill");
    var elBarTarefa = el("sra-cpl-bar-tarefa");
    var elBarTarefaFill = el("sra-cpl-bar-tarefa-fill");
    var elPctGeral = el("sra-cpl-pct-geral");
    var elPctTarefa = el("sra-cpl-pct-tarefa");
    [
      "sra-cpl-status-ok",
      "sra-cpl-status-partial",
      "sra-cpl-status-fail",
      "sra-cpl-confirm",
    ].forEach(function (rid) {
      var w = el(rid);
      if (w) {
        w.classList.add("is-hidden");
      }
    });
    sraTrackWrap.classList.remove("is-hidden");
    var d = ev.data;
    var pid = ev.process_id;
    if (d.tarefa) {
      trackState.lastTarefa[pid] = d.tarefa;
    }
    var nomeTarefa =
      d.tarefa ||
      trackState.lastTarefa[pid] ||
      (ev.status === "working" ? ev.title : "") ||
      "—";
    if (elTrackTarefa) {
      elTrackTarefa.textContent = nomeTarefa;
    }
    var rawSub =
      d.subtarefa != null && String(d.subtarefa).trim()
        ? String(d.subtarefa).trim()
        : "";
    if (elTrackSub && elTrackSubWrap) {
      if (rawSub) {
        elTrackSub.textContent = rawSub;
        elTrackSubWrap.classList.remove("is-hidden");
        elTrackSubWrap.setAttribute("aria-hidden", "false");
      } else {
        elTrackSubWrap.classList.add("is-hidden");
        elTrackSubWrap.setAttribute("aria-hidden", "true");
      }
    }
    var linha = (ev.message || "").trim();
    if (!linha && d.mensagem) {
      linha = String(d.mensagem).trim();
    }
    if (elTrackMsg) {
      elTrackMsg.textContent = linha || ev.title || "—";
    }
    if (elTrackHdrSub && d.process_key) {
      elTrackHdrSub.textContent = d.process_key;
      elTrackHdrSub.classList.remove("is-hidden");
      elTrackHdrSub.setAttribute("aria-hidden", "false");
    } else if (elTrackHdrSub && !d.process_key) {
      elTrackHdrSub.classList.add("is-hidden");
      elTrackHdrSub.setAttribute("aria-hidden", "true");
    }
    var gDef = d.progresso_geral !== undefined && d.progresso_geral !== null;
    var tDef = d.progresso_tarefa !== undefined && d.progresso_tarefa !== null;
    if (gDef) {
      trackState.lastGeral[pid] = clampPct100(d.progresso_geral);
    }
    if (tDef) {
      trackState.lastTarefaPct[pid] = clampPct100(d.progresso_tarefa);
    }
    var gV = trackState.lastGeral[pid] != null ? trackState.lastGeral[pid] : 0;
    var tV =
      trackState.lastTarefaPct[pid] != null ? trackState.lastTarefaPct[pid] : 0;
    setOneBar(elBarGeral, elBarGeralFill, elPctGeral, gV);
    setOneBar(elBarTarefa, elBarTarefaFill, elPctTarefa, tV);
  }

  function notificacaoPodeExibirToast(ev) {
    var toasts = el("process-toasts");
    if (!toasts) {
      return false;
    }
    if (ev.kind === "server_log" && ev.level === "info") {
      return false;
    }
    if (ev.data && ev.data.channel === "process") {
      return false;
    }
    return true;
  }

  function toast(ev) {
    if (!notificacaoPodeExibirToast(ev)) {
      return;
    }
    var toasts = el("process-toasts");
    if (!toasts) {
      return;
    }
    var item = document.createElement("div");
    item.className = "process-toast is-" + (ev.status || "info");
    item.innerHTML =
      "<strong>" +
      esc(ev.title || "Aviso") +
      "</strong>" +
      (ev.message ? "<span>" + esc(ev.message) + "</span>" : "");
    toasts.appendChild(item);
    setTimeout(function () {
      item.classList.add("is-out");
    }, 5200);
    setTimeout(function () {
      item.remove();
    }, 5800);
  }

  function receive(ev) {
    if (!ev) {
      return;
    }
    if (
      window.SRALiveLog &&
      typeof window.SRALiveLog.onSse === "function"
    ) {
      window.SRALiveLog.onSse(ev);
    }
    if (ev.kind === "connection") {
      return;
    }
    var d = ev.data || {};
    if (
      d.channel === "process" &&
      ev.kind === "process" &&
      d.outcome &&
      ev.status !== "working"
    ) {
      var fimPid = ev.process_id;
      var sraTrackWrap = el("sra-cpl-track");
      if (fimPid && omitSseFim[fimPid]) {
        delete omitSseFim[fimPid];
        if (sraTrackWrap) {
          sraTrackWrap.classList.add("is-hidden");
        }
        return;
      }
      if (sraTrackWrap) {
        sraTrackWrap.classList.add("is-hidden");
      }
      mostrarModalFimProcesso(d);
      toast(ev);
      return;
    }
    atualizarAcompanhamentoTratado(ev);
    toast(ev);
  }

  function openTrackPendente(opts) {
    opts = opts || {};
    var ch = opts.chave || opts.process_key || "";
    var pendente = window.SRAProcessTrackDefaults || {};
    var gen =
      pendente[ch] ||
      {
        tarefa: "Acompanhamento do processo",
        mensagem: "A iniciar a operação no servidor…",
      };
    var sraTrackWrap = el("sra-cpl-track");
    if (!sraTrackWrap) {
      return;
    }
    var elTrackTarefa = el("sra-cpl-now-tarefa");
    var elTrackMsg = el("sra-cpl-now-msg");
    var elTrackSubWrap = el("sra-cpl-now-sub-wrap");
    var elTrackHdrSub = el("sra-cpl-track-sub");
    var elBarGeral = el("sra-cpl-bar-geral");
    var elBarGeralFill = el("sra-cpl-bar-geral-fill");
    var elBarTarefa = el("sra-cpl-bar-tarefa");
    var elBarTarefaFill = el("sra-cpl-bar-tarefa-fill");
    var elPctGeral = el("sra-cpl-pct-geral");
    var elPctTarefa = el("sra-cpl-pct-tarefa");
    [
      "sra-cpl-confirm",
      "sra-cpl-status-ok",
      "sra-cpl-status-partial",
      "sra-cpl-status-fail",
    ].forEach(function (rid) {
      var w = el(rid);
      if (w) {
        w.classList.add("is-hidden");
      }
    });
    sraTrackWrap.classList.remove("is-hidden");
    if (elTrackTarefa) {
      var t1 = opts.tarefa;
      elTrackTarefa.textContent =
        t1 != null && String(t1).length ? String(t1) : gen.tarefa;
    }
    if (elTrackMsg) {
      var t2 = opts.mensagem;
      elTrackMsg.textContent =
        t2 != null && String(t2).length ? String(t2) : gen.mensagem;
    }
    if (elTrackSubWrap) {
      elTrackSubWrap.classList.add("is-hidden");
      elTrackSubWrap.setAttribute("aria-hidden", "true");
    }
    if (elTrackHdrSub) {
      if (ch) {
        elTrackHdrSub.textContent = ch;
        elTrackHdrSub.classList.remove("is-hidden");
        elTrackHdrSub.setAttribute("aria-hidden", "false");
      } else {
        elTrackHdrSub.classList.add("is-hidden");
        elTrackHdrSub.setAttribute("aria-hidden", "true");
      }
    }
    setOneBar(elBarGeral, elBarGeralFill, elPctGeral, 0);
    setOneBar(elBarTarefa, elBarTarefaFill, elPctTarefa, 0);
  }

  function hideTrack() {
    var w = el("sra-cpl-track");
    if (w) {
      w.classList.add("is-hidden");
    }
  }

  function registerTrackDefaults(extra) {
    if (!extra || typeof extra !== "object") {
      return;
    }
    window.SRAProcessTrackDefaults = window.SRAProcessTrackDefaults || {};
    Object.assign(window.SRAProcessTrackDefaults, extra);
  }

  window.SRAProcess = {
    notify: function (title, message, status) {
      receive({
        kind: "client",
        level: status || "info",
        status: status || "info",
        title: title,
        message: message,
        ts: new Date().toISOString(),
        process_id: "client-" + Date.now(),
        data: { channel: "notify" },
      });
    },
    setStatus: function () {},
    log: function (title, message, status) {
      receive({
        kind: "client",
        level: status || "info",
        status: status || "info",
        title: title,
        message: message,
        ts: new Date().toISOString(),
        process_id: "client-log",
        data: { channel: "notify" },
      });
    },
    open: function () {},
    openTrackPendente: openTrackPendente,
    hideTrack: hideTrack,
    registerTrackDefaults: registerTrackDefaults,
    mostrarFimAposRedirect: function (payload) {
      if (!payload || !payload.data) {
        return;
      }
      if (payload.process_id) {
        omitSseFim[payload.process_id] = true;
      }
      var tw = el("sra-cpl-track");
      if (tw) {
        tw.classList.add("is-hidden");
      }
      mostrarModalFimProcesso(payload.data);
    },
  };

  var nativeFetch = window.fetch;
  window.fetch = async function () {
    var resp = await nativeFetch.apply(this, arguments);
    if (resp.status === 401) {
      window.location.href = "/login";
    }
    return resp;
  };

  var sseErrorToastMostrado = false;
  try {
    var source = new EventSource("/processos/eventos");
    source.onmessage = function (msg) {
      try {
        receive(JSON.parse(msg.data));
      } catch (e) {
        /* evento inválido */
      }
    };
    source.onerror = function () {
      var toasts = el("process-toasts");
      if (!toasts || sseErrorToastMostrado) {
        return;
      }
      sseErrorToastMostrado = true;
      var item = document.createElement("div");
      item.className = "process-toast is-danger";
      item.innerHTML =
        "<strong>Conexão</strong><span>Canal de eventos indisponível. Atualize a página se o problema persistir.</span>";
      toasts.appendChild(item);
      setTimeout(function () {
        item.classList.add("is-out");
      }, 7200);
      setTimeout(function () {
        item.remove();
      }, 7800);
    };
  } catch (err) {
    /* sem EventSource */
  }

  function initDomHooks() {
    var sraTrackWrap = el("sra-cpl-track");
    if (sraTrackWrap) {
      var c = el("sra-cpl-track-close");
      if (c && !c.dataset.sraTrackWired) {
        c.dataset.sraTrackWired = "1";
        c.addEventListener("click", function () {
          sraTrackWrap.classList.add("is-hidden");
        });
      }
      if (!sraTrackWrap.dataset.sraBackdropWired) {
        sraTrackWrap.dataset.sraBackdropWired = "1";
        sraTrackWrap.addEventListener("click", function (e) {
          if (e.target === sraTrackWrap) {
            sraTrackWrap.classList.add("is-hidden");
          }
        });
      }
    }
    function fecharWrap(wrapId) {
      var w = el(wrapId);
      if (w) {
        w.classList.add("is-hidden");
      }
    }
    [
      ["sra-cpl-status-ok", "sra-cpl-status-ok-btn"],
      ["sra-cpl-status-partial", "sra-cpl-status-partial-btn"],
      ["sra-cpl-status-fail", "sra-cpl-status-fail-btn"],
    ].forEach(function (pair) {
      var wid = pair[0];
      var btn = el(pair[1]);
      if (btn && !btn.dataset.sraFimWired) {
        btn.dataset.sraFimWired = "1";
        btn.addEventListener("click", function () {
          fecharWrap(wid);
          window.location.reload();
        });
      }
      var wrap = el(wid);
      if (wrap && !wrap.dataset.sraFimBackdropWired) {
        wrap.dataset.sraFimBackdropWired = "1";
        wrap.addEventListener("click", function (e) {
          if (e.target === wrap) {
            fecharWrap(wid);
          }
        });
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDomHooks);
  } else {
    initDomHooks();
  }
})();
