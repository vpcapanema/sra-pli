/**
 * Confirmações destrutivas ou longas via window.confirm (sem modal HTML nem API).
 * Textos equivalentes ao antigo fluxo por chave.
 *
 * Chrome [Violation] "handler submit levou Xms": inclui o tempo em que o utilizador
 * deixa o diálogo nativo `confirm()` aberto; não é latência do servidor nem do POST.
 *
 * Logs `[fluxo confirm]`: metadados em JSON numa linha (evita expansão do Object na consola).
 * Fluxos com validação HTML5 (criar relatório, importação) usam segunda fase SKIP+requestSubmit;
 * os restantes usam form.submit() direto após o confirm.
 */
(function () {
  "use strict";

  var SKIP = "data-sra-confirm-skip";

  var FLUXO = {
    importacao_assistida_analise: {
      title: "Confirmar análise assistida",
      lead:
        "O ficheiro TXT ou DOCX é analisado; os blocos propostos serão exibidos para revisão. " +
        "Nada é gravado no relatório neste passo.",
      detail:
        "A duração depende do tamanho do documento (típico: segundos a cerca de um minuto). " +
        "Mantém-se a sessão; pode sair de Importar conteúdo sem perder a revisão, desde que não confirme a gravação.",
      ask: "Iniciar a análise do ficheiro selecionado?",
      show_detail: true,
    },
    importacao_assistida_confirmar: {
      title: "Confirmar gravação da importação",
      lead:
        "Os blocos selecionados serão inseridos no relatório em transação única, com eventuais ajustes de secções, " +
        "quando a estrutura o exigir.",
      detail: "Operação de escrita: verifique a lista de revisão antes de continuar.",
      ask: "Gravar no relatório os blocos selecionados?",
      show_detail: true,
    },
    relatorio_criar: {
      title: "Confirmar criação do relatório",
      lead:
        "Será criado um novo D20 com as secções de acordo com a fonte de sumário indicada:",
      detail: "Após a criação, o código não poderá ser alterado; a versão inicia em R00.",
      ask: "Criar o relatório com estes parâmetros?",
      show_detail: true,
    },
    exportar_relatorio: {
      title: "Confirmar exportação",
      lead:
        "Gera-se o ficheiro (PDF ou DOCX) a partir do conteúdo atual do relatório, segundo o âmbito escolhido.",
      detail:
        "O processo pode levar de alguns segundos a minutos, conforme o volume. O download abre noutro separador.",
      ask: "Iniciar a exportação?",
      show_detail: true,
    },
    relatorio_excluir: {
      title: "Confirmar exclusão do relatório",
      lead:
        "O relatório e os dados associados serão removidos de forma definitiva. Esta ação não pode ser desfeita.",
      detail: "",
      ask: "Excluir definitivamente este relatório?",
      show_detail: false,
    },
    notificar_autores_abertura: {
      title: "Confirmar envio de abertura aos autores",
      lead:
        "Será enviado o e-mail de abertura do período (Mensagem 1) a todos os autores com notificações ativas, " +
        "incluindo o endereço principal e o secundário.",
      detail:
        "Quem já tiver recebido receberá novamente — útil para reforçar, mas evite duplicar por engano.",
      ask: "Enviar o e-mail de abertura a todos os autores agora?",
      show_detail: true,
    },
    notificar_ciclo_lembrete: {
      title: "Confirmar lembretes (Mensagem 2)",
      lead:
        "Será disparado o lembrete do ciclo para entregas ainda pendentes neste relatório, " +
        "fora do calendário automático de dias.",
      detail:
        "Quem já tiver entrega em «enviado» ou «validado» não entra no lote. " +
        "O serviço pode abrandar reenvios muito próximos (janela mínima entre envios).",
      ask: "Enviar lembretes para este relatório agora?",
      show_detail: true,
    },
    notificar_ciclo_ultima_chamada: {
      title: "Confirmar última chamada (Mensagem 2)",
      lead:
        "Será disparada a variante «última chamada» do ciclo para entregas pendentes neste relatório, " +
        "fora do dia fixo configurado no calendário.",
      detail:
        "Quem já tiver entrega em «enviado» ou «validado» não entra no lote. " +
        "O serviço pode abrandar reenvios muito próximos (janela mínima entre envios).",
      ask: "Enviar última chamada para este relatório agora?",
      show_detail: true,
    },
    secao_excluir: {
      title: "Confirmar exclusão da secção",
      lead:
        "A subsecção e todos os respetivos blocos serão removidos. Esta ação não se pode anular de forma simples no sistema.",
      detail: "",
      ask: "Excluir definitivamente esta secção e o seu conteúdo?",
      show_detail: false,
    },
    bloco_confirmar: {
      title: "Confirmar e bloquear bloco",
      lead:
        "O bloco deixa de ser editável, passando a estado bloqueado para revisão, conforme o fluxo de coordenação.",
      detail: "",
      ask: "Bloquear este bloco para revisão?",
      show_detail: false,
    },
    bloco_excluir: {
      title: "Confirmar exclusão do bloco",
      lead:
        "O bloco será removido de forma definitiva. Contagens e numeração podem ser ajustadas automaticamente após a exclusão.",
      detail: "",
      ask: "Excluir permanentemente este bloco?",
      show_detail: false,
    },
    blocos_lote_excluir: {
      title: "Confirmar exclusão em lote",
      lead: "Os blocos selecionados serão excluídos. Verifique a seleção no quadro de blocos.",
      detail: "",
      ask: "Excluir definitivamente os blocos selecionados?",
      show_detail: false,
    },
    blocos_lote_aprovar: {
      title: "Confirmar aprovação em lote",
      lead:
        "Os blocos selecionados serão bloqueados para revisão, em sequência, uma única operação de escrita na base.",
      detail: "",
      ask: "Bloquear os blocos selecionados para revisão?",
      show_detail: false,
    },
  };

  function basePayload(chave) {
    var row = FLUXO[chave];
    if (!row) {
      return {
        title: "Confirmar",
        lead: "Deseja continuar?",
        detail: "",
        ask: "Continuar?",
        show_detail: false,
      };
    }
    return {
      title: row.title || "Confirmar",
      lead: row.lead || "",
      detail: row.detail || "",
      ask: row.ask || "Deseja continuar?",
      show_detail: Boolean(row.show_detail && String(row.detail || "").trim()),
    };
  }

  function mergePayload(base, ov) {
    if (!ov) {
      return base;
    }
    var out = {
      title: ov.title || base.title,
      lead: ov.lead || base.lead,
      detail:
        ov.detail != null && String(ov.detail).length ? ov.detail : base.detail,
      ask: ov.ask || base.ask,
      show_detail:
        ov.show_detail === true || ov.show_detail === false
          ? ov.show_detail
          : base.show_detail,
    };
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

  function buildConfirmText(p) {
    var parts = [];
    if (p.title) {
      parts.push(p.title);
    }
    var lead = p.lead || "";
    if (Object.prototype.hasOwnProperty.call(p, "source_line") && p.source_line) {
      lead = lead + "\n\n" + p.source_line;
    }
    if (lead.trim()) {
      parts.push(lead.trim());
    }
    if (p.show_detail && (p.detail || "").trim()) {
      parts.push("Detalhe: " + String(p.detail).trim());
    }
    parts.push(p.ask || "Deseja continuar?");
    return parts.join("\n\n");
  }

  function carregarChave(chave) {
    return Promise.resolve(mergePayload(basePayload(chave), null));
  }

  function confirmarComChave(chave, override) {
    var p = mergePayload(basePayload(chave), override || null);
    return Promise.resolve(window.confirm(buildConfirmText(p)));
  }

  function abrirDireto(p) {
    return Promise.resolve(window.confirm(buildConfirmText(p || {})));
  }

  function fecharConfirm() {}

  /** Logs de etapa para a consola (acompanhar confirm → POST). */
  function stringifyFluxoExtra(obj) {
    try {
      return JSON.stringify(obj);
    } catch (err) {
      return String(obj);
    }
  }

  /** Só estes fluxos precisam de ``requestSubmit`` + SKIP (validação HTML5 antes do POST). */
  function precisaSegundaFaseValidacao(chave) {
    return (
      chave === "relatorio_criar" ||
      chave === "importacao_assistida_analise" ||
      chave === "importacao_assistida_confirmar"
    );
  }

  function logFluxoConfirmar(etapa, mensagem, extra) {
    var texto = "[fluxo confirm] " + etapa + ": " + mensagem;
    if (extra !== undefined && extra !== null) {
      texto += " | " + stringifyFluxoExtra(extra);
    }
    if (typeof window.SRA_LOG !== "undefined") {
      window.SRA_LOG.info(texto);
      return;
    }
    console.info("[SRA]", texto);
  }

  /** Mensagem por chave de confirm quando não há data-sra-busy-msg. */
  var BUSY_DEFAULT_BY_CONFIRM = {
    relatorio_excluir: "A excluir o relatório no servidor…",
    relatorio_criar: "A criar o relatório…",
    secao_excluir: "A excluir a secção…",
    notificar_autores_abertura: "A enviar e-mails de abertura…",
    notificar_ciclo_lembrete: "A enviar lembretes…",
    notificar_ciclo_ultima_chamada: "A enviar última chamada…",
  };

  function obterMensagemBusy(form, chaveConfirm) {
    var attr = form.getAttribute("data-sra-busy-msg");
    if (attr && String(attr).trim()) {
      return String(attr).trim();
    }
    if (chaveConfirm && BUSY_DEFAULT_BY_CONFIRM[chaveConfirm]) {
      return BUSY_DEFAULT_BY_CONFIRM[chaveConfirm];
    }
    return "A processar o pedido no servidor…";
  }

  /**
   * Feedback durante POST após confirmação: log na consola e faixa fixa.
   * Ativado por data-sra-iniciar-acompanhamento="1" no formulário.
   * Não desativa botões submit antes de requestSubmit(): botão desativado impede o envio.
   */
  function iniciarAcompanhamentoSubmit(form, chaveConfirm) {
    if (form.getAttribute("data-sra-iniciar-acompanhamento") !== "1") {
      return;
    }
    var msg = obterMensagemBusy(form, chaveConfirm);
    var url = form.action || "";
    if (typeof window.SRA_LOG !== "undefined") {
      window.SRA_LOG.info(
        "Submissão POST (aguardar servidor) | url=" + url + " | faixa=" + msg
      );
      window.SRA_LOG.debug("[acompanhamento] " + msg);
    }
    form.classList.add("sra-form-busy");
    var bar = document.getElementById("sra-submit-busy");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "sra-submit-busy";
      bar.setAttribute("role", "status");
      bar.setAttribute("aria-live", "polite");
      bar.className = "sra-submit-busy";
      document.body.appendChild(bar);
    }
    bar.textContent = msg;
    bar.classList.add("is-visible");
  }

  function initDataConfirmForms() {
    document.querySelectorAll("form[data-sra-confirm]").forEach(function (form) {
      if (form.dataset.sraWired) {
        return;
      }
      form.dataset.sraWired = "1";
      form.addEventListener("submit", function (e) {
        if (form.getAttribute(SKIP) === "1" || form.dataset.sraConfirmSkip === "1") {
          form.removeAttribute(SKIP);
          logFluxoConfirmar("5-post-nativo", "envio HTML normal (sem segundo confirm)", {
            action: form.action || "",
            chave: form.getAttribute("data-sra-confirm"),
          });
          return;
        }
        var ch = form.getAttribute("data-sra-confirm");
        if (!ch) {
          return;
        }
        var actionUrl = form.action || "";
        var t0 =
          typeof performance !== "undefined" && performance.now ? performance.now() : null;
        logFluxoConfirmar("1-interceptado", "confirmação pendente", {
          chave: ch,
          action: actionUrl,
          method: (form.method || "get").toLowerCase(),
        });
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
          if (!sim) {
            var cancelTxt =
              "[fluxo confirm] cancelado — POST não enviado | " +
              stringifyFluxoExtra({ chave: ch, action: actionUrl });
            if (typeof window.SRA_LOG !== "undefined") {
              window.SRA_LOG.warn(cancelTxt);
            } else {
              console.warn("[SRA]", cancelTxt);
            }
            return;
          }
          var dt =
            t0 !== null && typeof performance !== "undefined" && performance.now
              ? Math.round(performance.now() - t0)
              : null;
          logFluxoConfirmar("2-confirmado", "utilizador aceitou — a preparar envio", {
            chave: ch,
            action: actionUrl,
            msAposInterceptar: dt,
          });
          // Liberta o ciclo atual antes da segunda submissão (SKIP): ajuda o browser a pintar a faixa «busy».
          queueMicrotask(function () {
            logFluxoConfirmar("3-microtask", "antes do envio após confirm", {
              chave: ch,
              segundaFaseValidacao: precisaSegundaFaseValidacao(ch),
              temAcompanhamento: form.getAttribute("data-sra-iniciar-acompanhamento") === "1",
            });
            iniciarAcompanhamentoSubmit(form, ch);
            if (precisaSegundaFaseValidacao(ch)) {
              form.setAttribute(SKIP, "1");
              if (form.requestSubmit) {
                logFluxoConfirmar("4-requestSubmit", "segunda fase (SKIP+validação HTML5)");
                form.requestSubmit();
              } else {
                logFluxoConfirmar("4-submit", "fallback form.submit()");
                form.submit();
              }
            } else {
              logFluxoConfirmar(
                "4-submit-direto",
                "form.submit() — sem SKIP (evita requestSubmit bloqueado por CSS ou segunda fase)"
              );
              form.submit();
            }
          });
        });
      });
    });
  }

  function init() {
    initDataConfirmForms();
  }

  window.SRAComplementos = {
    init: init,
    carregarChave: carregarChave,
    confirmarComChave: confirmarComChave,
    abrirDireto: abrirDireto,
    fecharConfirm: fecharConfirm,
    logFluxoConfirmar: logFluxoConfirmar,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
