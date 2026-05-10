(function () {
  const cod = document.getElementById("rel-novo-codigo");
  const tit = document.getElementById("rel-novo-titulo");
  const med = document.getElementById("rel-novo-medicao");
  if (!cod || !tit || !med) return;

  function derivarDeCodigo(raw) {
    const s = (raw || "").trim();
    if (!s) return { medicao: null, titulo: null };
    if (/^\d+$/.test(s)) {
      const n = parseInt(s, 10);
      if (Number.isNaN(n) || n < 1) return { medicao: null, titulo: null };
      return { medicao: n, titulo: "Relatório Mensal D20-" + n };
    }
    const idx = s.lastIndexOf("-");
    if (idx < 0) {
      return { medicao: null, titulo: "Relatório Mensal " + s };
    }
    const pref = s.slice(0, idx).trim().replace(/\s+/g, "");
    const suf = s.slice(idx + 1).replace(/\s+/g, "");
    if (!/^\d+$/.test(suf)) {
      return { medicao: null, titulo: "Relatório Mensal " + s };
    }
    const n = parseInt(suf, 10);
    if (Number.isNaN(n) || n < 1) {
      return { medicao: null, titulo: "Relatório Mensal " + s };
    }
    let codigoTitulo = s;
    if (/^d20$/i.test(pref)) {
      codigoTitulo = "D20-" + n;
    }
    return { medicao: n, titulo: "Relatório Mensal " + codigoTitulo };
  }

  function syncTituloMedicao() {
    const d = derivarDeCodigo(cod.value);
    if (d.medicao != null) {
      med.value = String(d.medicao);
    }
    if (d.titulo != null) {
      tit.value = d.titulo;
    }
  }

  cod.addEventListener("input", syncTituloMedicao);
  cod.addEventListener("blur", syncTituloMedicao);
})();

(function () {
  document.querySelectorAll("[data-open-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = document.getElementById(btn.dataset.openModal);
      if (modal) modal.classList.remove("is-hidden");
    });
  });
  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = document.getElementById(btn.dataset.closeModal);
      if (modal) modal.classList.add("is-hidden");
    });
  });
  document.querySelectorAll(".rel-modal").forEach((modal) => {
    modal.addEventListener("click", (ev) => {
      if (ev.target === modal) modal.classList.add("is-hidden");
    });
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      document
        .querySelectorAll(".rel-modal:not(.is-hidden)")
        .forEach((modal) => modal.classList.add("is-hidden"));
    }
  });
})();

// Toggle de seções do dashboard
(function () {
  document.querySelectorAll("[data-toggle-target]").forEach((el) => {
    el.addEventListener("click", () => {
      const targetId = el.dataset.toggleTarget;
      const target = document.getElementById(targetId);
      if (!target) return;

      const isHidden = target.classList.contains("ss-content-collapsed");
      if (isHidden) {
        target.classList.remove("ss-content-collapsed");
        el.querySelector(".ss-toggle-icon").style.transform = "rotate(180deg)";
      } else {
        target.classList.add("ss-content-collapsed");
        el.querySelector(".ss-toggle-icon").style.transform = "rotate(0deg)";
      }
    });
  });
})();

/**
 * Progresso real de criação de relatório no dashboard (3 opções).
 *
 * - Opções 1 e 2 (clone / docx_disponivel): submit tradicional intercepta,
 *   envia via fetch(FormData) com header Accept: application/json; recebe
 *   {token} e inicia polling em /relatorios/novo/progresso/{token}.
 * - Opção 3 (docx_upload): change no <input type=file> dispara upload via
 *   XMLHttpRequest; upload.onprogress alimenta 0..50% (upload real);
 *   depois do load recebe {token} e passa 50..100% via polling.
 * - Overlay único com <progress> + % numérica + texto de etapa.
 *
 * Convive com sra_process_ui.js: remove data-sra-confirm/data-sra-iniciar-
 * acompanhamento do form de novo relatório antes de sua inicialização, para
 * evitar conflito com o fluxo nativo de SweetAlert2.
 */
(function () {
  "use strict";

  function mount() {
    var form = document.getElementById("form-novo-relatorio");
    if (!form) {
      return;
    }

    var inpDocxUpload = form.querySelector('input[name="docx_upload"]');
    var selSRA = form.querySelector('select[name="base_relatorio_id"]');
    var selDocx = form.querySelector('select[name="docx_disponivel"]');
    var hiddenFonte = form.querySelector('input[name="fonte_secoes"]');
    var btnSubmit = form.querySelector('button[type="submit"]');
    var btnUploadDocx = form.querySelector("#btn-upload-docx");

    var overlay = criarOverlay();

    function fonteAtual() {
      if (selDocx && selDocx.value) {
        return "docx_disponivel";
      }
      if (inpDocxUpload && inpDocxUpload.files && inpDocxUpload.files[0]) {
        return "docx_upload";
      }
      if (selSRA && selSRA.value) {
        return "clone_relatorio";
      }
      return "";
    }

    function atualizarFonteHidden() {
      if (!hiddenFonte) return;
      var f = fonteAtual();
      if (f) {
        hiddenFonte.value = f;
      }
    }

    selSRA.addEventListener("change", function () {
      if (this.value) {
        selDocx.value = "";
        if (inpDocxUpload) inpDocxUpload.value = "";
      }
      atualizarFonteHidden();
    });

    selDocx.addEventListener("change", function () {
      if (this.value) {
        selSRA.value = "";
        if (inpDocxUpload) inpDocxUpload.value = "";
      }
      atualizarFonteHidden();
    });

    if (btnUploadDocx && inpDocxUpload) {
      btnUploadDocx.addEventListener("click", function () {
        inpDocxUpload.click();
      });
    }

    form.addEventListener("submit", function (ev) {
      var fonte = fonteAtual();
      if (!fonte) {
        ev.preventDefault();
        return;
      }
      ev.preventDefault();
      if (!form.reportValidity()) {
        return;
      }
      iniciarCriacao(form, overlay, null);
    });

    if (inpDocxUpload) {
      inpDocxUpload.addEventListener("change", function () {
        if (!inpDocxUpload.files || !inpDocxUpload.files[0]) {
          return;
        }
        // Upload apenas, sem clonagem automática
        uploadDocxOnly(form, overlay, inpDocxUpload.files[0]);
      });
    }
  }

  function uploadDocxOnly(form, overlay, arquivo) {
    overlay.open();
    overlay.set(0, "Enviando arquivo...");

    var fd = new FormData();
    fd.append("docx_upload", arquivo);

    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/relatorios/upload-docx", true);

    xhr.upload.onprogress = function (e) {
      if (!e.lengthComputable) return;
      var pct = (e.loaded / e.total) * 100;
      overlay.set(
        pct,
        "Enviando arquivo (" +
          formatSize(e.loaded) +
          " / " +
          formatSize(e.total) +
          ")",
      );
    };

    xhr.onload = function () {
      if (xhr.status === 200) {
        overlay.set(100, "Upload concluído");
        overlay.concluido();
        // Recarregar página para atualizar lista de DOCX
        setTimeout(function () {
          window.location.reload();
        }, 1000);
      } else {
        overlay.falhou("Falha ao fazer upload (HTTP " + xhr.status + ")");
      }
    };

    xhr.onerror = function () {
      overlay.falhou("Erro de rede.");
    };

    xhr.send(fd);
  }

  function criarOverlay() {
    var ov = document.createElement("div");
    ov.id = "sra-progress-overlay";
    ov.setAttribute("role", "dialog");
    ov.setAttribute("aria-modal", "true");
    ov.setAttribute("aria-labelledby", "sra-progress-title");
    ov.innerHTML =
      '<div class="sra-progress-box">' +
      '  <div class="sra-progress-hdr" id="sra-progress-title">Criando relatório</div>' +
      '  <div class="sra-progress-etapa" id="sra-progress-etapa">Preparando…</div>' +
      '  <div class="sra-progress-bar-wrap">' +
      '    <progress id="sra-progress-bar" max="100" value="0"></progress>' +
      '    <span class="sra-progress-pct" id="sra-progress-pct">0%</span>' +
      "  </div>" +
      '  <div class="sra-progress-erro" id="sra-progress-erro" hidden></div>' +
      '  <div class="sra-progress-actions">' +
      '    <button type="button" class="sra-progress-close" id="sra-progress-close" disabled>Fechar</button>' +
      "  </div>" +
      "</div>";
    document.body.appendChild(ov);

    var btnClose = ov.querySelector("#sra-progress-close");
    btnClose.addEventListener("click", function () {
      ov.classList.remove("is-open");
    });

    return {
      el: ov,
      etapa: ov.querySelector("#sra-progress-etapa"),
      bar: ov.querySelector("#sra-progress-bar"),
      pct: ov.querySelector("#sra-progress-pct"),
      erro: ov.querySelector("#sra-progress-erro"),
      close: btnClose,
      open: function () {
        this.erro.hidden = true;
        this.erro.textContent = "";
        this.close.disabled = true;
        this.close.textContent = "Fechar";
        this.set(0, "Preparando…");
        ov.classList.add("is-open");
      },
      set: function (pct, etapa) {
        var p = Math.max(0, Math.min(100, Math.round(pct)));
        this.bar.value = p;
        this.pct.textContent = p + "%";
        if (etapa) {
          this.etapa.textContent = etapa;
        }
      },
      falhou: function (msg) {
        this.erro.hidden = false;
        this.erro.textContent = msg || "Falha ao criar relatório.";
        this.close.disabled = false;
      },
      concluido: function () {
        this.close.disabled = false;
        this.close.textContent = "Fechar";
      },
    };
  }

  function iniciarCriacao(form, overlay, arquivoOpcaoTres) {
    overlay.open();
    var fd = new FormData(form);
    var xhr = new XMLHttpRequest();
    xhr.open("POST", form.action || "/relatorios", true);
    xhr.setRequestHeader("Accept", "application/json");

    var temUploadPesado = Boolean(arquivoOpcaoTres);
    if (temUploadPesado) {
      xhr.upload.onprogress = function (e) {
        if (!e.lengthComputable) return;
        var pctUpload = (e.loaded / e.total) * 50;
        overlay.set(
          pctUpload,
          "Enviando arquivo (" +
            formatSize(e.loaded) +
            " / " +
            formatSize(e.total) +
            ")",
        );
      };
      xhr.upload.onload = function () {
        overlay.set(50, "Arquivo enviado; processando no servidor…");
      };
    }

    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      if (xhr.status === 202) {
        try {
          var data = JSON.parse(xhr.responseText);
          if (data && data.token) {
            iniciarPolling(data.token, overlay, temUploadPesado ? 50 : 0);
            return;
          }
        } catch (err) {
          overlay.falhou("Resposta inválida do servidor.");
          return;
        }
        overlay.falhou("Sem token de progresso.");
        return;
      }
      var msg = "Falha (HTTP " + xhr.status + ").";
      try {
        var j = JSON.parse(xhr.responseText);
        if (j && j.detail) {
          msg =
            typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        }
      } catch (_) {
        if (xhr.responseText) {
          var t = xhr.responseText.trim();
          if (t.length < 500) msg = t;
        }
      }
      overlay.falhou(msg);
    };

    xhr.onerror = function () {
      overlay.falhou("Erro de rede.");
    };

    xhr.send(fd);
  }

  function iniciarPolling(token, overlay, pctFloor) {
    var url = "/relatorios/novo/progresso/" + encodeURIComponent(token);
    var terminado = false;
    function tick() {
      if (terminado) return;
      fetch(url, { headers: { Accept: "application/json" } })
        .then(function (r) {
          if (r.status === 404) {
            throw new Error("Token expirado ou desconhecido.");
          }
          return r.json();
        })
        .then(function (j) {
          if (terminado) return;
          var pct = Math.max(pctFloor, j.pct || 0);
          overlay.set(pct, j.etapa || "Processando…");
          if (j.erro) {
            terminado = true;
            overlay.falhou(j.erro);
            return;
          }
          if (j.pronto) {
            terminado = true;
            overlay.set(100, "Concluído");
            overlay.concluido();
            if (j.redirect_url) {
              window.location.href = j.redirect_url;
            }
            return;
          }
          setTimeout(tick, 400);
        })
        .catch(function (err) {
          if (terminado) return;
          terminado = true;
          overlay.falhou(String(err && err.message ? err.message : err));
        });
    }
    tick();
  }

  function formatSize(n) {
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(2) + " MB";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
