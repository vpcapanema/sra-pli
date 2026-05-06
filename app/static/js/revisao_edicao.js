/* cSpell:ignore MORFOLOGIK REDUNDAN PROLIX ocorrencias ocorrência ocorrências bloco blocos secao secão seções relatório relatório */
/* Revisão editorial — Ribbon estilo Word com toolbar Quill integrada, auto-save JSON, dock de revisão.
   ============================================================================
   Princípio:
     - O documento renderiza estaticamente (HTML do pdf_render) com capa, ficha, sumário e seções.
     - Ribbon único estilo Word com dropdowns, botões grandes e toolbar Quill integrada.
     - Ao focar um bloco editável, instanciamos Quill *só naquele bloco*; ao
       perder foco com latência, destruímos o editor para evitar acumular
       toolbars/listeners.
     - A toolbar Quill padrão é escondida; usamos a toolbar customizada no ribbon.
     - Auto-save por bloco em JSON, debounced, com indicação visual.
     - Blocos com marcadores estruturais ([[FIGURA/TABELA/REF]]) chegam como
       readonly e nunca recebem Quill.

   Pendências de save são protegidas com `beforeunload` para evitar perda
   acidental ao recarregar a página.
*/
(function () {
  "use strict";

  var root = document.getElementById("rev-edit-root");
  if (!root) return;
  var REL_ID = root.dataset.relId;
  var EDITAVEL = root.dataset.editavel === "1";
  var SRA_RICH_PREFIX = "<!--SRA_RICH-->";
  var QUILL_DESTROY_DELAY_MS = 250;
  var SAVE_DEBOUNCE_MS = 900;

  var quillByBloco = new Map(); // blocoId -> Quill instance
  var quillHostByBloco = new Map(); // blocoId -> host (que substituiu .rev-block__body)
  var quillDestroyTimer = new Map(); // blocoId -> timeoutId p/ destruição
  var saveTimers = new Map(); // blocoId -> timeoutId
  var pendingSaves = new Set(); // blocoIds com save em voo ou pendente
  var ignoredIssues = new Set();
  var dockData = { motor: "", secoes: [], achados_planos: [] };
  var filtroAtual = "todas";
  var activeQuillId = null; // ID do bloco com Quill ativo

  function log() {
    if (window.SRA_LOG && window.SRA_LOG.debug) {
      window.SRA_LOG.debug.apply(window.SRA_LOG, arguments);
    }
  }

  // ---------- Save state UI ----------
  function setSaveState(blockEl, state, msg) {
    var s = blockEl.querySelector("[data-save-state]");
    if (!s) return;
    s.dataset.state = state;
    s.textContent =
      msg ||
      (state === "saving"
        ? "Salvando…"
        : state === "saved"
          ? "Salvo"
          : state === "error"
            ? "Erro"
            : "");
  }
  function setGlobalSave(state, msg) {
    var chip = document.getElementById("rev-chip-save");
    if (!chip) return;
    chip.hidden = false;
    chip.classList.remove("rev-chip--saving", "rev-chip--error");
    if (state === "saving") chip.classList.add("rev-chip--saving");
    if (state === "error") chip.classList.add("rev-chip--error");
    chip.textContent =
      msg ||
      (state === "saving" ? "Salvando…" : state === "saved" ? "Salvo" : "Erro");
    if (state === "saved")
      setTimeout(function () {
        chip.hidden = true;
      }, 1800);
  }

  // ---------- Auto-save (debounced JSON POST) ----------
  function scheduleSave(blockEl, payload, debounceMs) {
    if (!EDITAVEL) return;
    var blocoId = blockEl.dataset.blocoId;
    if (!blocoId) return;
    var prev = saveTimers.get(blocoId);
    if (prev) clearTimeout(prev);
    pendingSaves.add(blocoId);
    setSaveState(blockEl, "saving", "Pendente…");
    var t = setTimeout(
      function () {
        saveTimers.delete(blocoId);
        sendSave(blockEl, blocoId, payload);
      },
      debounceMs == null ? SAVE_DEBOUNCE_MS : debounceMs,
    );
    saveTimers.set(blocoId, t);
  }

  function sendSave(blockEl, blocoId, payload) {
    setSaveState(blockEl, "saving", "Salvando…");
    setGlobalSave("saving");
    pendingSaves.add(blocoId);
    fetch("/relatorios/" + REL_ID + "/blocos/" + blocoId + "/revisao-salvar", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        if (!r.ok) {
          return r.json().then(function (j) {
            throw new Error(j.detail || "HTTP " + r.status);
          });
        }
        return r.json();
      })
      .then(function () {
        pendingSaves.delete(blocoId);
        setSaveState(blockEl, "saved", "Salvo");
        setGlobalSave("saved");
        log("rev:save ok", blocoId);
      })
      .catch(function (err) {
        pendingSaves.delete(blocoId);
        setSaveState(blockEl, "error", "Erro");
        setGlobalSave("error", String(err.message || err));
        log("rev:save erro", blocoId, err);
      });
  }

  // ---------- Quill lazy / destroy ----------
  function quillReady(cb) {
    if (window.Quill) return cb();
    var attempts = 0;
    var iv = setInterval(function () {
      attempts++;
      if (window.Quill) {
        clearInterval(iv);
        cb();
      } else if (attempts > 60) {
        clearInterval(iv);
        console.warn("Quill não carregou em tempo hábil.");
      }
    }, 100);
  }

  function showRibbonToolbar() {
    var toolbar = document.getElementById("rev-quill-toolbar");
    if (toolbar) toolbar.hidden = false;
  }

  function hideRibbonToolbar() {
    var toolbar = document.getElementById("rev-quill-toolbar");
    if (toolbar) toolbar.hidden = true;
  }

  function ensureQuill(blockEl) {
    var blocoId = blockEl.dataset.blocoId;
    if (!blocoId) return;
    var pendingDestroy = quillDestroyTimer.get(blocoId);
    if (pendingDestroy) {
      clearTimeout(pendingDestroy);
      quillDestroyTimer.delete(blocoId);
      return; // Editor já existe e estava prestes a ser destruído.
    }
    if (quillByBloco.has(blocoId)) return;

    var body = blockEl.querySelector(
      '[data-edit-field="conteudo"][data-edit-mode="rich"]:not([data-quill-host])',
    );
    if (!body) return;
    if (body.dataset.readonly) return;

    quillReady(function () {
      // Cria container que substitui temporariamente o body.
      var holder = document.createElement("div");
      holder.className = "rev-block__quill";
      holder.innerHTML = body.innerHTML;
      holder.setAttribute("data-edit-field", "conteudo");
      holder.setAttribute("data-edit-mode", "rich");
      holder.setAttribute("data-quill-host", "1");
      body.replaceWith(holder);
      var q = new window.Quill(holder, {
        theme: "snow",
        modules: {
          toolbar: false, // Toolbar escondida, usa o ribbon
        },
      });
      quillByBloco.set(blocoId, q);
      quillHostByBloco.set(blocoId, holder);
      activeQuillId = blocoId;
      showRibbonToolbar();
      q.on("text-change", function (_d, _o, source) {
        if (source !== "user") return;
        scheduleSave(
          blockEl,
          { conteudo: SRA_RICH_PREFIX + q.root.innerHTML },
          SAVE_DEBOUNCE_MS,
        );
      });
      q.focus();
    });
  }

  function destroyQuill(blockEl) {
    var blocoId = blockEl.dataset.blocoId;
    var q = quillByBloco.get(blocoId);
    var holder = quillHostByBloco.get(blocoId);
    if (!q || !holder) return;
    // Flush save imediato se houver debounce em voo.
    var t = saveTimers.get(blocoId);
    if (t) {
      clearTimeout(t);
      saveTimers.delete(blocoId);
      sendSave(blockEl, blocoId, {
        conteudo: SRA_RICH_PREFIX + q.root.innerHTML,
      });
    }
    var html = q.root.innerHTML;
    // Remove o nó adicionado pelo Quill (que ele insere logo após o host) e
    // restaura o body original com o HTML atual editado.
    var toolbar = holder.previousElementSibling;
    if (
      toolbar &&
      toolbar.classList &&
      toolbar.classList.contains("ql-toolbar")
    ) {
      toolbar.remove();
    }
    var newBody = document.createElement("div");
    newBody.className = "rev-block__body";
    newBody.setAttribute("data-edit-field", "conteudo");
    newBody.setAttribute("data-edit-mode", "rich");
    newBody.innerHTML = html;
    holder.replaceWith(newBody);
    quillByBloco.delete(blocoId);
    quillHostByBloco.delete(blocoId);
    if (activeQuillId === blocoId) {
      activeQuillId = null;
      hideRibbonToolbar();
    }
  }

  function scheduleDestroyQuill(blockEl) {
    var blocoId = blockEl.dataset.blocoId;
    var prev = quillDestroyTimer.get(blocoId);
    if (prev) clearTimeout(prev);
    var t = setTimeout(function () {
      quillDestroyTimer.delete(blocoId);
      // Cancela se o foco voltou para dentro do bloco.
      if (blockEl.contains(document.activeElement)) return;
      destroyQuill(blockEl);
    }, QUILL_DESTROY_DELAY_MS);
    quillDestroyTimer.set(blocoId, t);
  }

  // ---------- Edição plain (legenda/fonte) ----------
  function bindPlainEditors(blockEl) {
    if (!EDITAVEL) return;
    blockEl
      .querySelectorAll('[data-edit-field][data-edit-mode="plain"]')
      .forEach(function (el) {
        var field = el.dataset.editField;
        var span = el.querySelector(
          "[data-" + (field === "legenda" ? "legenda" : "fonte") + "-text]",
        );
        if (!span || span.dataset.bound === "1") return;
        span.dataset.bound = "1";
        span.contentEditable = "true";
        span.spellcheck = true;
        span.addEventListener("blur", function () {
          var raw = (span.innerText || "").replace(/\s+/g, " ").trim();
          if (raw === "(legenda)" || raw === "(fonte)") raw = "";
          var payload = {};
          payload[field] = raw;
          sendSave(blockEl, blockEl.dataset.blocoId, payload);
        });
      });
  }

  // ---------- Foco em bloco ----------
  function onFocusIn(ev) {
    var blockEl = ev.target.closest(".rev-block");
    if (!blockEl || !EDITAVEL) return;
    if (blockEl.dataset.editavelInline !== "1") return;
    if (
      blockEl.dataset.blocoTipo === "texto" ||
      blockEl.dataset.blocoTipo === "lista"
    ) {
      ensureQuill(blockEl);
    }
  }

  function onFocusOut(ev) {
    var blockEl = ev.target.closest(".rev-block");
    if (!blockEl) return;
    // Programar destruição com pequeno atraso para permitir refoco interno
    // (clicar entre toolbar e área de texto, por exemplo).
    setTimeout(function () {
      if (blockEl.contains(document.activeElement)) return;
      scheduleDestroyQuill(blockEl);
    }, 0);
  }

  // ---------- Desconfirmar ----------
  function onBlockClick(ev) {
    var btn = ev.target.closest('[data-action="desconfirmar"]');
    if (!btn) return;
    ev.stopPropagation();
    ev.preventDefault();
    var blockEl = btn.closest(".rev-block");
    if (!blockEl) return;
    if (
      !confirm(
        "Desconfirmar este bloco? Ele voltará a ficar editável livremente e a entrega do autor pode ser reaberta.",
      )
    )
      return;
    var blocoId = blockEl.dataset.blocoId;
    fetch(
      "/relatorios/" + REL_ID + "/blocos/" + blocoId + "/revisao-desconfirmar",
      {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      },
    )
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function () {
        blockEl.classList.remove("rev-block--locked");
        blockEl.dataset.bloqueado = "0";
        var lock = blockEl.querySelector(".rev-block__lock");
        if (lock) lock.remove();
        btn.remove();
        setSaveState(blockEl, "saved", "Reaberto");
      })
      .catch(function (err) {
        alert("Falha ao desconfirmar: " + err.message);
      });
  }

  // ---------- Revisão linguística ----------
  function categoriaDe(achado) {
    var regra = (achado.regra || "").toUpperCase();
    if (
      regra === "ORTOGRAFIA" ||
      regra.indexOf("SPELL") !== -1 ||
      regra.indexOf("MORFOLOGIK") !== -1
    )
      return "ortografia";
    if (
      regra.indexOf("STYLE") !== -1 ||
      regra.indexOf("REDUNDAN") !== -1 ||
      regra.indexOf("PROLIX") !== -1
    )
      return "estilo";
    return "gramatica";
  }

  function rodarRevisao() {
    var btn = document.getElementById("rev-btn-revisar");
    var hint = document.getElementById("rev-dock-hint");
    var list = document.getElementById("rev-dock-list");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Analisando…";
    }
    if (hint)
      hint.textContent =
        "Analisando o texto do relatório (pode levar alguns segundos)…";

    fetch("/relatorios/" + REL_ID + "/revisao-linguistica", {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        atualizarMotor(data.motor, data.motor_rotulo, data.aviso_motor);
        var planos = [];
        (data.secoes || []).forEach(function (s) {
          (s.achados || []).forEach(function (a, idx) {
            planos.push({
              secao_numero: s.secao_numero,
              secao_titulo: s.secao_titulo,
              regra: a.regra,
              mensagem: a.mensagem,
              trecho: a.trecho,
              sugestoes: a.sugestoes || [],
              categoria: categoriaDe(a),
              key: s.secao_numero + "|" + a.regra + "|" + a.trecho + "|" + idx,
            });
          });
        });
        dockData = {
          motor: data.motor,
          secoes: data.secoes || [],
          achados_planos: planos,
        };
        atualizarSublinhados();
        atualizarDock();
        if (planos.length === 0) {
          if (hint) {
            hint.textContent = "Nenhuma ocorrência encontrada.";
            hint.hidden = false;
          }
          if (list) list.hidden = true;
        } else {
          if (hint) hint.hidden = true;
          if (list) list.hidden = false;
        }
      })
      .catch(function (err) {
        if (hint)
          hint.textContent = "Falha ao executar a revisão. Tente novamente.";
        log("rev:revisar erro", err);
      })
      .finally(function () {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span aria-hidden="true">✓</span> Revisar texto';
        }
      });
  }

  function atualizarMotor(motor, rotulo, aviso) {
    var chip = document.getElementById("rev-chip-motor");
    var sub = document.getElementById("rev-dock-motor-sub");
    if (chip) {
      chip.textContent = "Revisor: " + (rotulo || motor || "—");
      chip.title = aviso || rotulo || "";
    }
    if (sub)
      sub.textContent = aviso
        ? "— " +
          (motor === "languagetool"
            ? "gramática + estilo"
            : motor === "pyspellchecker"
              ? "só ortografia"
              : "desligado")
        : "";
  }

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function limparMarks() {
    document.querySelectorAll(".rev-mark").forEach(function (m) {
      var p = m.parentNode;
      if (!p) return;
      while (m.firstChild) p.insertBefore(m.firstChild, m);
      p.removeChild(m);
      p.normalize();
    });
  }

  function atualizarSublinhados() {
    limparMarks();
    dockData.achados_planos.forEach(function (a, idx) {
      if (!a.trecho) return;
      if (ignoredIssues.has(a.key)) return;
      var ancora = "sec-" + (a.secao_numero || "").replace(/\./g, "-");
      var sec = document.getElementById(ancora);
      if (!sec) return;
      var blocos = sec.querySelectorAll(".rev-block");
      var marcado = false;
      for (var i = 0; i < blocos.length && !marcado; i++) {
        // Não sublinhar dentro de host do Quill (DOM volátil).
        if (blocos[i].querySelector("[data-quill-host]")) continue;
        marcado = sublinharNoBloco(blocos[i], a, idx);
      }
    });
  }

  function sublinharNoBloco(blockEl, achado, idx) {
    var alvo =
      blockEl.querySelector(
        '[data-edit-field="conteudo"]:not([data-quill-host])',
      ) ||
      blockEl.querySelector("[data-legenda-text]") ||
      blockEl.querySelector("[data-fonte-text]");
    if (!alvo) return false;
    var walker = document.createTreeWalker(alvo, NodeFilter.SHOW_TEXT, null);
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) nodes.push(n);
    var re = new RegExp(escapeRegExp(achado.trecho));
    for (var i = 0; i < nodes.length; i++) {
      var t = nodes[i];
      if (!t.nodeValue) continue;
      var m = t.nodeValue.match(re);
      if (!m) continue;
      var start = m.index;
      var end = start + achado.trecho.length;
      var rng = document.createRange();
      try {
        rng.setStart(t, start);
        rng.setEnd(t, end);
      } catch (e) {
        continue;
      }
      var span = document.createElement("span");
      span.className = "rev-mark rev-mark--" + achado.categoria;
      span.dataset.issueIdx = String(idx);
      span.dataset.issueKey = achado.key;
      span.title = achado.mensagem || "";
      try {
        rng.surroundContents(span);
        return true;
      } catch (e) {
        /* atravessa nós; pula */
      }
    }
    return false;
  }

  function atualizarDock() {
    var counts = { todas: 0, ortografia: 0, gramatica: 0, estilo: 0 };
    dockData.achados_planos.forEach(function (a) {
      if (ignoredIssues.has(a.key)) return;
      counts.todas += 1;
      counts[a.categoria] += 1;
    });
    Object.keys(counts).forEach(function (k) {
      var el = document.querySelector('[data-count="' + k + '"]');
      if (el) el.textContent = counts[k];
    });
    var chipOcc = document.getElementById("rev-chip-ocorrencias");
    if (chipOcc) {
      chipOcc.hidden = counts.todas === 0;
      chipOcc.textContent =
        counts.todas + " ocorrência" + (counts.todas === 1 ? "" : "s");
    }
    document.querySelectorAll("[data-secao-badge]").forEach(function (el) {
      el.hidden = true;
      el.textContent = "0";
    });
    var bySec = {};
    dockData.achados_planos.forEach(function (a) {
      if (ignoredIssues.has(a.key)) return;
      bySec[a.secao_numero] = (bySec[a.secao_numero] || 0) + 1;
    });
    Object.keys(bySec).forEach(function (k) {
      var el = document.querySelector('[data-secao-badge="' + k + '"]');
      if (el) {
        el.textContent = bySec[k];
        el.hidden = false;
      }
    });

    var list = document.getElementById("rev-dock-list");
    if (!list) return;
    list.innerHTML = "";
    dockData.achados_planos.forEach(function (a, idx) {
      if (ignoredIssues.has(a.key)) return;
      if (filtroAtual !== "todas" && a.categoria !== filtroAtual) return;
      var li = document.createElement("li");
      li.className = "rev-issue rev-issue--" + a.categoria;
      li.dataset.issueIdx = String(idx);
      li.dataset.issueKey = a.key;
      var sug =
        a.sugestoes && a.sugestoes.length
          ? '<div class="rev-issue__sug">Sugestões: ' +
            a.sugestoes
              .map(function (s, i) {
                return i === 0 ? "<b>" + escHtml(s) + "</b>" : escHtml(s);
              })
              .join(" · ") +
            "</div>"
          : "";
      var btnAceitar =
        a.sugestoes && a.sugestoes.length && EDITAVEL
          ? '<button type="button" class="rev-issue__btn rev-issue__btn--primary" data-action="aceitar">Aceitar "' +
            escHtml(a.sugestoes[0]) +
            '"</button>'
          : "";
      var btnDicionario =
        a.categoria === "ortografia" && a.trecho && EDITAVEL
          ? '<button type="button" class="rev-issue__btn" data-action="dicionario" title="Adicionar este termo ao vocabulário do projeto">+ Dicionário</button>'
          : "";
      li.innerHTML =
        '<div class="rev-issue__tag">' +
        a.categoria +
        " · seção " +
        escHtml(a.secao_numero) +
        "</div>" +
        '<p class="rev-issue__q">"…<span class="rev-issue__bad">' +
        escHtml(a.trecho) +
        '</span>…" — <i>' +
        escHtml(a.mensagem) +
        "</i></p>" +
        sug +
        '<div class="rev-issue__actions">' +
        btnAceitar +
        '<button type="button" class="rev-issue__btn" data-action="navegar">Ver no documento</button>' +
        btnDicionario +
        '<button type="button" class="rev-issue__btn" data-action="ignorar">Ignorar</button>' +
        "</div>";
      list.appendChild(li);
    });
  }

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function onDockClick(ev) {
    var li = ev.target.closest(".rev-issue");
    if (!li) return;
    var idx = Number(li.dataset.issueIdx);
    var achado = dockData.achados_planos[idx];
    if (!achado) return;
    var btn = ev.target.closest("[data-action]");
    if (btn) {
      var act = btn.dataset.action;
      if (act === "aceitar") return aceitarSugestao(achado);
      if (act === "ignorar") return ignorarAchado(achado);
      if (act === "navegar") return navegarAteAchado(achado);
      if (act === "dicionario") return adicionarAoDicionario(achado, btn);
    } else {
      navegarAteAchado(achado);
    }
  }

  function adicionarAoDicionario(achado, btnEl) {
    if (!EDITAVEL) return;
    var termo = (achado.trecho || "").trim();
    if (!termo) return;
    var ok = confirm(
      'Adicionar "' +
        termo +
        '" ao vocabulário do projeto? Próximas revisões deixarão de marcar este termo como erro.',
    );
    if (!ok) return;
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.textContent = "Adicionando…";
    }
    fetch("/relatorios/" + REL_ID + "/revisao-linguistica/vocabulario", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ termo: termo }),
    })
      .then(function (r) {
        if (!r.ok)
          return r.json().then(function (j) {
            throw new Error(j.detail || "HTTP " + r.status);
          });
        return r.json();
      })
      .then(function (data) {
        // Ignora todas as ocorrências deste termo na sessão atual e marca o
        // botão como confirmado. A próxima revisão (servidor) já saberá.
        var lower = termo.toLowerCase();
        dockData.achados_planos.forEach(function (a) {
          if ((a.trecho || "").toLowerCase() === lower)
            ignoredIssues.add(a.key);
        });
        atualizarSublinhados();
        atualizarDock();
        setGlobalSave(
          "saved",
          data.criado ? "Termo adicionado" : "Termo já existia",
        );
      })
      .catch(function (err) {
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = "+ Dicionário";
        }
        alert("Falha ao adicionar termo: " + err.message);
      });
  }

  function navegarAteAchado(achado) {
    var sel = '.rev-mark[data-issue-key="' + cssEscape(achado.key) + '"]';
    var span = document.querySelector(sel);
    document.querySelectorAll(".rev-mark--active").forEach(function (m) {
      m.classList.remove("rev-mark--active");
    });
    if (span) {
      span.scrollIntoView({ behavior: "smooth", block: "center" });
      span.classList.add("rev-mark--active");
    } else {
      var sec = document.getElementById(
        "sec-" + (achado.secao_numero || "").replace(/\./g, "-"),
      );
      if (sec) sec.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function cssEscape(s) {
    if (window.CSS && window.CSS.escape) return window.CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) {
      return "\\" + c;
    });
  }

  function ignorarAchado(achado) {
    ignoredIssues.add(achado.key);
    atualizarSublinhados();
    atualizarDock();
  }

  function aceitarSugestao(achado) {
    if (!EDITAVEL) return;
    if (!achado.sugestoes || !achado.sugestoes.length) return;
    var sug = achado.sugestoes[0];
    var span = document.querySelector(
      '.rev-mark[data-issue-key="' + cssEscape(achado.key) + '"]',
    );
    if (!span) {
      alert(
        "Não foi possível localizar visualmente o trecho. Edite manualmente o bloco.",
      );
      return;
    }
    var blockEl = span.closest(".rev-block");
    if (!blockEl) return;
    if (
      blockEl.dataset.editavelInline !== "1" &&
      (blockEl.dataset.blocoTipo === "texto" ||
        blockEl.dataset.blocoTipo === "lista")
    ) {
      alert("Bloco com marcadores estruturais — edite no Editor de Conteúdo.");
      return;
    }
    span.replaceWith(document.createTextNode(sug));
    var body = blockEl.querySelector(
      '[data-edit-field="conteudo"]:not([data-quill-host])',
    );
    if (body) {
      sendSave(blockEl, blockEl.dataset.blocoId, {
        conteudo: SRA_RICH_PREFIX + body.innerHTML,
      });
    } else {
      var leg = blockEl.querySelector("[data-legenda-text]");
      var fon = blockEl.querySelector("[data-fonte-text]");
      if (leg && leg.contains(span)) {
        sendSave(blockEl, blockEl.dataset.blocoId, {
          legenda: (leg.innerText || "").trim(),
        });
      } else if (fon) {
        sendSave(blockEl, blockEl.dataset.blocoId, {
          fonte: (fon.innerText || "").trim(),
        });
      }
    }
    ignoredIssues.add(achado.key);
    atualizarDock();
  }

  function onFiltroClick(ev) {
    var btn = ev.target.closest("[data-filter]");
    if (!btn) return;
    document.querySelectorAll("[data-filter]").forEach(function (b) {
      b.classList.remove("rev-filter--on");
    });
    btn.classList.add("rev-filter--on");
    filtroAtual = btn.dataset.filter;
    atualizarDock();
  }

  function onCollapseClick(ev) {
    var btn = ev.target.closest(".rev-collapse");
    if (!btn) return;
    var ws = document.getElementById("rev-workspace");
    var target = btn.dataset.target;
    if (!ws || !target) return;
    var cls =
      target === "rev-tree"
        ? "rev-workspace--no-tree"
        : "rev-workspace--no-dock";
    ws.classList.toggle(cls);
    btn.textContent = ws.classList.contains(cls)
      ? target === "rev-tree"
        ? "›"
        : "‹"
      : target === "rev-tree"
        ? "‹"
        : "›";
  }

  // ---------- Deep-link ----------
  function aplicarDeepLink() {
    var params = new URLSearchParams(window.location.search);
    var sec = params.get("secao");
    var bloco =
      params.get("bloco") ||
      (window.location.hash.indexOf("#bloco-") === 0
        ? window.location.hash.slice(7)
        : null);
    var alvo = null;
    if (bloco) alvo = document.getElementById("bloco-" + bloco);
    else if (sec)
      alvo = document.getElementById("sec-" + sec.replace(/\./g, "-"));
    else if (window.location.hash)
      alvo = document.querySelector(window.location.hash);
    if (alvo) {
      setTimeout(function () {
        alvo.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 80);
    }
  }

  // ---------- beforeunload ----------
  function onBeforeUnload(ev) {
    // Flush sincronizado (best-effort) com sendBeacon para Quills com texto não salvo.
    quillByBloco.forEach(function (q, blocoId) {
      var blockEl = document.querySelector(
        '.rev-block[data-bloco-id="' + blocoId + '"]',
      );
      if (!blockEl) return;
      var t = saveTimers.get(blocoId);
      if (!t) return;
      clearTimeout(t);
      saveTimers.delete(blocoId);
      try {
        var body = JSON.stringify({
          conteudo: SRA_RICH_PREFIX + q.root.innerHTML,
        });
        if (navigator.sendBeacon) {
          navigator.sendBeacon(
            "/relatorios/" + REL_ID + "/blocos/" + blocoId + "/revisao-salvar",
            new Blob([body], { type: "application/json" }),
          );
          pendingSaves.delete(blocoId);
        }
      } catch (e) {
        /* ignore */
      }
    });
    if (pendingSaves.size > 0) {
      ev.preventDefault();
      ev.returnValue = "Há alterações não salvas. Sair mesmo assim?";
      return ev.returnValue;
    }
    return undefined;
  }

  // ---------- Ribbon dropdowns ----------
  function onRibbonDropdownClick(ev) {
    var btn = ev.target.closest("[data-dropdown]");
    if (!btn) return;
    var dropdownId = btn.dataset.dropdown;
    var menu = document.getElementById("dropdown-" + dropdownId);
    if (!menu || !menu.classList.contains("rev-ribbon-dropdown__menu")) return;

    var isOpen = !menu.hidden;
    // Fecha todos os dropdowns e submenus
    document
      .querySelectorAll(
        ".rev-ribbon-dropdown__menu, .rev-ribbon-dropdown__submenu",
      )
      .forEach(function (m) {
        m.hidden = true;
      });
    document.querySelectorAll("[data-dropdown]").forEach(function (b) {
      b.setAttribute("aria-expanded", "false");
    });

    if (!isOpen) {
      menu.hidden = false;
      btn.setAttribute("aria-expanded", "true");
      // Posiciona o dropdown embaixo do botão
      var btnRect = btn.getBoundingClientRect();
      var menusRect = document
        .querySelector(".rev-ribbon__menus")
        .getBoundingClientRect();
      menu.style.left = btnRect.left - menusRect.left + "px";
    }
    ev.stopPropagation();
  }

  function onRibbonSubmenuClick(ev) {
    var btn = ev.target.closest("[data-submenu]");
    if (!btn) return;
    var submenuId = btn.dataset.submenu;
    var submenu = document.getElementById("submenu-" + submenuId);
    if (!submenu || !submenu.classList.contains("rev-ribbon-dropdown__submenu"))
      return;

    var isOpen = !submenu.hidden;
    // Fecha todos os submenus do mesmo nível
    var parentMenu = btn.closest(
      ".rev-ribbon-dropdown__menu, .rev-ribbon-dropdown__submenu",
    );
    parentMenu
      .querySelectorAll(".rev-ribbon-dropdown__submenu")
      .forEach(function (s) {
        s.hidden = true;
      });

    if (!isOpen) {
      submenu.hidden = false;
    }
    ev.stopPropagation();
  }

  function onRibbonDropdownItemClick(ev) {
    var item = ev.target.closest(".rev-dropdown-item");
    if (!item) return;
    var action = item.dataset.action;
    if (!action) return;

    // Fecha o dropdown
    var menu = item.closest(".rev-ribbon-dropdown__menu");
    if (menu) menu.hidden = true;
    var dropdownId = menu.id.replace("dropdown-", "");
    var btn = document.querySelector('[data-dropdown="' + dropdownId + '"]');
    if (btn) {
      btn.setAttribute("aria-expanded", "false");
    }

    // Executa a ação
    if (action === "salvar-tudo") salvarTudo();
    else if (action === "fechar")
      window.location.href =
        "/relatorios/" + REL_ID;
    else if (action === "recarregar") window.location.reload();
    else if (action === "zoom-in") alert("Zoom não implementado ainda");
    else if (action === "zoom-out") alert("Zoom não implementado ainda");
    else if (action === "zoom-reset") alert("Zoom não implementado ainda");

    ev.stopPropagation();
  }

  // ---------- Ribbon toolbar Quill ----------
  function onRibbonToolClick(ev) {
    var btn = ev.target.closest("[data-quill]");
    if (!btn) return;
    if (!activeQuillId) return;

    var q = quillByBloco.get(activeQuillId);
    if (!q) return;

    var format = btn.dataset.quill;
    var value = btn.dataset.value;

    if (format === "header") {
      q.format("header", parseInt(value, 10));
    } else if (format === "align") {
      q.format("align", value);
    } else if (format === "list") {
      q.format("list", value);
    } else if (format === "script") {
      q.format("script", value);
    } else if (format === "clean") {
      var range = q.getSelection();
      if (range) q.removeFormat(range.index, range.length);
    } else if (format === "link") {
      var range = q.getSelection();
      if (range) {
        var url = prompt("URL do link:");
        if (url) q.format("link", url);
      }
    } else {
      q.format(format, !q.getFormat()[format]);
    }

    q.focus();
    ev.stopPropagation();
  }

  // ---------- Ribbon action buttons ----------
  function onRibbonActionClick(ev) {
    var btn = ev.target.closest("[data-action]");
    if (!btn) return;
    var action = btn.dataset.action;

    if (action === "salvar") salvarTudo();
    else if (action === "revisar") rodarRevisao();
    else if (action === "export-docx-todo")
      window.location.href =
        "/relatorios/" + REL_ID + "/exportar?formato=docx&escopo=inteiro";
    else if (action === "export-docx-secoes")
      openModal("modal-export-docx-secoes");

    ev.stopPropagation();
  }

  function salvarTudo() {
    // Salva todos os Quills ativos
    quillByBloco.forEach(function (q, blocoId) {
      var blockEl = document.querySelector(
        '.rev-block[data-bloco-id="' + blocoId + '"]',
      );
      if (!blockEl) return;
      var t = saveTimers.get(blocoId);
      if (t) {
        clearTimeout(t);
        saveTimers.delete(blocoId);
      }
      sendSave(blockEl, blocoId, {
        conteudo: SRA_RICH_PREFIX + q.root.innerHTML,
      });
    });
  }

  // ---------- Modais ----------
  function openModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) modal.hidden = false;
  }

  function closeModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) modal.hidden = true;
  }

  function onModalClick(ev) {
    var action = ev.target.closest("[data-action]");
    if (!action) return;
    var act = action.dataset.action;
    if (act === "close-modal") {
      var modal = action.closest(".rev-modal");
      if (modal) modal.hidden = true;
    }
  }

  function onRibbonCrudClick(ev) {
    var btn = ev.target.closest(
      '[data-action="add-secao"], [data-action="add-figura"], [data-action="add-tabela"], [data-action="add-bloco"]',
    );
    if (!btn) return;
    var action = btn.dataset.action;
    if (action === "add-secao") openModal("modal-add-secao");
    else if (action === "add-figura") openModal("modal-add-figura");
    else if (action === "add-tabela") openModal("modal-add-tabela");
    else if (action === "add-bloco") openModal("modal-add-bloco");
  }

  function onAddSecaoSubmit(ev) {
    ev.preventDefault();
    var form = ev.target;
    var formData = new FormData(form);
    var titulo = formData.get("titulo");
    var secaoPaiId = formData.get("secao_pai_id");

    if (!titulo || !titulo.trim()) {
      alert("Título da seção é obrigatório");
      return;
    }

    // Se tem seção pai, usa a rota de subseção filha
    if (secaoPaiId && secaoPaiId.trim()) {
      var formDataSubmit = new FormData();
      formDataSubmit.append("titulo", titulo);

      fetch("/relatorios/" + REL_ID + "/secoes/" + secaoPaiId + "/subsecao", {
        method: "POST",
        body: formDataSubmit,
        credentials: "same-origin",
      })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.text();
        })
        .then(function () {
          closeModal("modal-add-secao");
          form.reset();
          window.location.reload();
        })
        .catch(function (err) {
          alert("Falha ao criar subseção: " + err.message);
        });
    } else {
      // Se não tem seção pai, usa a rota de criação de seção com número
      var numero = prompt("Número da seção (ex: 4.4):");
      if (!numero) return;

      var formDataSubmit = new FormData();
      formDataSubmit.append("numero", numero);
      formDataSubmit.append("titulo", titulo);

      fetch("/relatorios/" + REL_ID + "/secoes", {
        method: "POST",
        body: formDataSubmit,
        credentials: "same-origin",
      })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.text();
        })
        .then(function () {
          closeModal("modal-add-secao");
          form.reset();
          window.location.reload();
        })
        .catch(function (err) {
          alert("Falha ao criar seção: " + err.message);
        });
    }
  }

  function onAddBlocoSubmit(ev) {
    ev.preventDefault();
    var form = ev.target;
    var formData = new FormData(form);
    var secaoId = formData.get("secao_id");
    var tipo = formData.get("tipo");
    var titulo = formData.get("titulo") || "";
    var conteudo = formData.get("conteudo");

    if (!secaoId) {
      alert("Selecione uma seção");
      return;
    }
    if (!conteudo || !conteudo.trim()) {
      alert("Conteúdo do bloco é obrigatório");
      return;
    }

    var formDataSubmit = new FormData();
    formDataSubmit.append("tipo", tipo);
    formDataSubmit.append("titulo", titulo);
    formDataSubmit.append("conteudo", SRA_RICH_PREFIX + conteudo);
    formDataSubmit.append("legenda", "");
    formDataSubmit.append("fonte", "");
    formDataSubmit.append("figura_id", "");

    fetch("/relatorios/" + REL_ID + "/secoes/" + secaoId + "/blocos", {
      method: "POST",
      body: formDataSubmit,
      credentials: "same-origin",
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then(function () {
        closeModal("modal-add-bloco");
        form.reset();
        window.location.reload();
      })
      .catch(function (err) {
        alert("Falha ao criar bloco: " + err.message);
      });
  }

  function onAddFiguraSubmit(ev) {
    ev.preventDefault();
    alert(
      "Upload de figura ainda não implementado. Use o Editor de Conteúdo para adicionar figuras.",
    );
  }

  function onAddTabelaSubmit(ev) {
    ev.preventDefault();
    alert(
      "Upload de tabela ainda não implementado. Use o Editor de Conteúdo para adicionar tabelas.",
    );
  }

  function onExportDocxSecoesSubmit(ev) {
    ev.preventDefault();
    var form = ev.target;
    var formData = new FormData(form);
    var secoes = formData.getAll("secoes");

    if (secoes.length === 0) {
      alert("Selecione pelo menos uma seção para exportar.");
      return;
    }

    var url =
      "/relatorios/" +
      REL_ID +
      "/exportar?formato=docx&escopo=selecionadas&secao_ids=" +
      secoes.join(",");
    window.open(url, "_blank");
    closeModal("modal-export-docx-secoes");
  }

  function onDeleteBlocoClick(ev) {
    var btn = ev.target.closest('[data-action="delete-bloco"]');
    if (!btn) return;
    var blocoId = btn.dataset.blocoId;
    var secaoId = btn.dataset.secaoId;

    if (!confirm("Tem certeza que deseja excluir este bloco?")) return;

    var formData = new FormData();
    formData.append("bloco_ids[]", blocoId);

    fetch(
      "/relatorios/" + REL_ID + "/secoes/" + secaoId + "/blocos/excluir-lote",
      {
        method: "POST",
        body: formData,
        credentials: "same-origin",
      },
    )
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then(function () {
        window.location.reload();
      })
      .catch(function (err) {
        alert("Falha ao excluir bloco: " + err.message);
      });
  }

  // ---------- Bind ----------
  document.addEventListener("focusin", onFocusIn);
  document.addEventListener("focusout", onFocusOut);
  document.querySelectorAll(".rev-block").forEach(function (b) {
    bindPlainEditors(b);
    b.addEventListener("click", onBlockClick);
    b.addEventListener("click", onDeleteBlocoClick);
    b.addEventListener("click", function (ev) {
      // Foco automático ao clicar em qualquer parte do bloco (exceto botões).
      if (ev.target.closest("button, a, .ql-toolbar")) return;
      b.focus();
    });
  });

  // Ribbon dropdowns
  var ribbon = document.querySelector(".rev-ribbon");
  if (ribbon) {
    ribbon.addEventListener("click", onRibbonDropdownClick);
    ribbon.addEventListener("click", onRibbonSubmenuClick);
    ribbon.addEventListener("click", onRibbonDropdownItemClick);
    ribbon.addEventListener("click", onRibbonToolClick);
    ribbon.addEventListener("click", onRibbonActionClick);
    ribbon.addEventListener("click", onRibbonCrudClick);
  }

  // Ribbon action buttons
  document
    .getElementById("rev-btn-salvar")
    ?.addEventListener("click", function () {
      salvarTudo();
    });
  document
    .getElementById("rev-btn-revisar")
    ?.addEventListener("click", rodarRevisao);
  document
    .getElementById("rev-btn-exportar-docx")
    ?.addEventListener("click", function () {
      window.location.href =
        "/relatorios/" + REL_ID + "/exportar?formato=docx&escopo=inteiro";
    });

  // Modais
  document.querySelectorAll(".rev-modal").forEach(function (m) {
    m.addEventListener("click", onModalClick);
  });

  // Formulários
  var formAddSecao = document.getElementById("form-add-secao");
  if (formAddSecao) formAddSecao.addEventListener("submit", onAddSecaoSubmit);

  var formAddBloco = document.getElementById("form-add-bloco");
  if (formAddBloco) formAddBloco.addEventListener("submit", onAddBlocoSubmit);

  var formAddFigura = document.getElementById("form-add-figura");
  if (formAddFigura)
    formAddFigura.addEventListener("submit", onAddFiguraSubmit);

  var formAddTabela = document.getElementById("form-add-tabela");
  if (formAddTabela)
    formAddTabela.addEventListener("submit", onAddTabelaSubmit);

  var formExportDocxSecoes = document.getElementById("form-export-docx-secoes");
  if (formExportDocxSecoes)
    formExportDocxSecoes.addEventListener("submit", onExportDocxSecoesSubmit);

  var btnRevisar = document.getElementById("rev-btn-revisar");
  if (btnRevisar) btnRevisar.addEventListener("click", rodarRevisao);
  var dockList = document.getElementById("rev-dock-list");
  if (dockList) dockList.addEventListener("click", onDockClick);
  var filtros = document.querySelector(".rev-dock__filters");
  if (filtros) filtros.addEventListener("click", onFiltroClick);
  document.querySelectorAll(".rev-collapse").forEach(function (b) {
    b.addEventListener("click", onCollapseClick);
  });

  // Fecha dropdowns e submenus ao clicar fora
  document.addEventListener("click", function () {
    document
      .querySelectorAll(
        ".rev-ribbon-dropdown__menu, .rev-ribbon-dropdown__submenu",
      )
      .forEach(function (m) {
        m.hidden = true;
      });
    document.querySelectorAll("[data-dropdown]").forEach(function (b) {
      b.setAttribute("aria-expanded", "false");
    });
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.ctrlKey && ev.shiftKey && (ev.key === "R" || ev.key === "r")) {
      ev.preventDefault();
      rodarRevisao();
    }
  });

  window.addEventListener("beforeunload", onBeforeUnload);
  aplicarDeepLink();
  log("rev-edit: pronto", { rel: REL_ID, editavel: EDITAVEL });
})();
