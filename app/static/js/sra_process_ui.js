/**
 * Confirmações destrutivas ou longas via window.confirm (sem modal HTML nem API).
 * Textos equivalentes ao antigo fluxo por chave.
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

  function initDataConfirmForms() {
    document.querySelectorAll("form[data-sra-confirm]").forEach(function (form) {
      if (form.dataset.sraWired) {
        return;
      }
      form.dataset.sraWired = "1";
      form.addEventListener("submit", function (e) {
        if (form.getAttribute(SKIP) === "1" || form.dataset.sraConfirmSkip === "1") {
          form.removeAttribute(SKIP);
          return;
        }
        var ch = form.getAttribute("data-sra-confirm");
        if (!ch) {
          return;
        }
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
            return;
          }
          form.setAttribute(SKIP, "1");
          if (form.requestSubmit) {
            form.requestSubmit();
          } else {
            form.submit();
          }
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
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
