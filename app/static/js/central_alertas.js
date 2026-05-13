/**
 * SRA Sender — Central de Alertas Configuráveis
 * Interatividade: modal, formulário por etapas, CRUD via API REST
 */

(function () {
  "use strict";

  const API = "/api";
  let etapaAtual = 1;
  const totalEtapas = 6;
  let fluxosTemp = [];
  let alertaEditandoId = null;

  // ---------- Modal ----------

  window.abrirModalAlerta = function () {
    alertaEditandoId = null;
    etapaAtual = 1;
    fluxosTemp = [];
    document.getElementById("form-alerta").reset();
    document.getElementById("alerta-id").value = "";
    document.getElementById("modal-titulo").textContent = "Criar Alerta";
    atualizarSteps();
    atualizarBotoesModal();
    renderTabelaFluxo();
    document.getElementById("modal-alerta").style.display = "flex";
  };

  window.fecharModalAlerta = function () {
    document.getElementById("modal-alerta").style.display = "none";
  };

  window.abrirModalLogs = function (alertaId) {
    carregarLogs(alertaId);
    document.getElementById("modal-logs").style.display = "flex";
  };

  window.fecharModalLogs = function () {
    document.getElementById("modal-logs").style.display = "none";
  };

  // ---------- Steps ----------

  window.mudarEtapa = function (direcao) {
    const nova = etapaAtual + direcao;
    if (nova < 1 || nova > totalEtapas) return;
    etapaAtual = nova;
    atualizarSteps();
    atualizarBotoesModal();
    if (etapaAtual === 6) {
      preencherRevisao();
    }
  };

  function atualizarSteps() {
    document.querySelectorAll(".cn-step").forEach((el) => {
      const step = parseInt(el.dataset.step, 10);
      el.classList.toggle("cn-step--ativo", step === etapaAtual);
    });
    document.querySelectorAll(".cn-step-panel").forEach((el) => {
      const step = parseInt(el.dataset.step, 10);
      el.style.display = step === etapaAtual ? "block" : "none";
    });
    if (etapaAtual === 3) {
      toggleEventoForm();
    }
    if (etapaAtual === 4) {
      toggleAlertaForm();
    }
  }

  function toggleEventoForm() {
    const freq = document.getElementById("alerta-frequencia").value;
    const unicoForm = document.getElementById("evento-unico-form");
    const recForm = document.getElementById("evento-recorrente-form");
    const hint = document.getElementById("evento-rec-hint");
    if (!unicoForm || !recForm) return;
    if (freq === "recorrente") {
      unicoForm.style.display = "none";
      recForm.style.display = "block";
      if (hint) {
        hint.textContent = "Defina a posição dentro do ciclo de recorrência (ex: dia 1 ao dia 10 do mês para recorrência mensal).";
      }
    } else {
      unicoForm.style.display = "block";
      recForm.style.display = "none";
    }
  }

  function toggleAlertaForm() {
    const freq = document.getElementById("alerta-frequencia").value;
    const unicoForm = document.getElementById("alerta-unico-form");
    const recForm = document.getElementById("alerta-recorrente-form");
    if (!unicoForm || !recForm) return;
    if (freq === "recorrente") {
      unicoForm.style.display = "none";
      recForm.style.display = "block";
    } else {
      unicoForm.style.display = "block";
      recForm.style.display = "none";
    }
  }

  function atualizarBotoesModal() {
    document.getElementById("btn-voltar").style.display =
      etapaAtual > 1 ? "inline-flex" : "none";
    document.getElementById("btn-proximo").style.display =
      etapaAtual < totalEtapas ? "inline-flex" : "none";
    document.getElementById("btn-salvar").style.display =
      etapaAtual === totalEtapas ? "inline-flex" : "none";
    document.getElementById("btn-finalizar").style.display =
      etapaAtual === totalEtapas ? "inline-flex" : "none";
  }

  // ---------- Frequência ----------

  window.toggleFrequencia = function () {
    const freq = document.getElementById("alerta-frequencia").value;
    const campoSubtipo = document.getElementById("campo-subtipo");
    campoSubtipo.style.display = freq === "recorrente" ? "block" : "none";
    if (freq !== "recorrente") {
      document.getElementById("alerta-subtipo").value = "";
    }
    toggleEventoForm();
  };

  window.toggleSubtipoRecorrencia = function () {
    // Não é mais necessário, pois não há campos específicos por subtipo
  };

  // ---------- Fluxo ----------

  window.adicionarFluxo = function () {
    const tipo = document.getElementById("fluxo-tipo").value;
    const perfisSel = Array.from(
      document.getElementById("fluxo-perfis").selectedOptions,
    ).map((o) => o.value);
    const dia = parseInt(document.getElementById("fluxo-dia").value, 10) || 1;
    const hora = document.getElementById("fluxo-hora").value;

    fluxosTemp.push({
      tipo_mensagem: tipo,
      perfis_destinatarios: perfisSel,
      usuarios_destinatarios: [],
      dia_no_ciclo: dia,
      hora_disparo: hora,
      ativo: true,
    });
    renderTabelaFluxo();
  };

  function renderTabelaFluxo() {
    const tbody = document.querySelector("#tabela-fluxo tbody");
    if (!tbody) return;
    tbody.innerHTML = fluxosTemp
      .map(
        (f, i) => `
      <tr>
        <td>${i + 1}</td>
        <td>${f.tipo_mensagem}</td>
        <td>${(f.perfis_destinatarios || []).join(", ")}</td>
        <td>${f.dia_no_ciclo}</td>
        <td>${f.hora_disparo}</td>
        <td>
          <button class="cn-btn cn-btn--sm cn-btn--ghost" onclick="removerFluxo(${i})"><i class="fas fa-trash"></i></button>
        </td>
      </tr>
    `,
      )
      .join("");
  }

  window.removerFluxo = function (idx) {
    fluxosTemp.splice(idx, 1);
    renderTabelaFluxo();
  };

  // ---------- Revisão ----------

  function preencherRevisao() {
    document.getElementById("rev-nome").textContent =
      document.getElementById("alerta-nome").value || "—";
    const freq = document.getElementById("alerta-frequencia").value;
    const sub = document.getElementById("alerta-subtipo").value;
    document.getElementById("rev-frequencia").textContent =
      freq + (sub ? " / " + sub : "");
    let ei, ef;
    if (freq === "recorrente") {
      const dIni = document.getElementById("evento-rec-dia-ini").value;
      const hIni = document.getElementById("evento-rec-hora-ini").value;
      const dFim = document.getElementById("evento-rec-dia-fim").value;
      const hFim = document.getElementById("evento-rec-hora-fim").value;
      ei = dIni && hIni ? dIni + " " + hIni : "";
      ef = dFim && hFim ? dFim + " " + hFim : "";
    } else {
      ei = document.getElementById("evento-inicio").value;
      ef = document.getElementById("evento-fim").value;
    }
    document.getElementById("rev-evento").textContent =
      (ei ? ei : "—") + (ef ? " → " + ef : "");
    const ai = document.getElementById("alerta-inicio").value;
    const af = document.getElementById("alerta-fim").value;
    document.getElementById("rev-alerta").textContent =
      (ai ? ai : "—") + (af ? " → " + af : "");
    document.getElementById("rev-condicao").textContent =
      document.getElementById("alerta-condicao").value;
    document.getElementById("rev-fluxo").textContent = fluxosTemp.length;
  }

  // ---------- Salvar / Finalizar ----------

  function coletarPayload() {
    const diasSemana = Array.from(
      document.querySelectorAll(".cn-dias-semana input:checked"),
    ).map((c) => parseInt(c.value, 10));
    const freq = document.getElementById("alerta-frequencia").value;
    let inicioEventoPosicao = null;
    let fimEventoPosicao = null;
    let inicioAlertaPosicao = null;
    let fimAlertaPosicao = null;
    if (freq === "recorrente") {
      const dIni = document.getElementById("evento-rec-dia-ini").value;
      const dFim = document.getElementById("evento-rec-dia-fim").value;
      if (dIni) {
        inicioEventoPosicao = parseInt(dIni, 10);
      }
      if (dFim) {
        fimEventoPosicao = parseInt(dFim, 10);
      }
    }
    if (freq === "recorrente") {
      const alertaPosIni = document.getElementById("alerta-rec-pos-ini").value;
      const alertaPosFim = document.getElementById("alerta-rec-pos-fim").value;
      if (alertaPosIni) {
        inicioAlertaPosicao = parseInt(alertaPosIni, 10);
      }
      if (alertaPosFim) {
        fimAlertaPosicao = parseInt(alertaPosFim, 10);
      }
    }
    return {
      nome: document.getElementById("alerta-nome").value,
      descricao: document.getElementById("alerta-descricao").value,
      status: document.getElementById("alerta-status").value,
      frequencia: freq,
      subtipo_recorrencia:
        document.getElementById("alerta-subtipo").value || null,
      timezone: document.getElementById("alerta-timezone").value,
      inicio_ciclo_evento_posicao: inicioEventoPosicao || null,
      fim_ciclo_evento_posicao: fimEventoPosicao || null,
      inicio_ciclo_alerta_posicao: inicioAlertaPosicao || null,
      fim_ciclo_alerta_posicao: fimAlertaPosicao || null,
      condicao_encerramento: document.getElementById("alerta-condicao").value,
      fluxos: fluxosTemp.length ? fluxosTemp : undefined,
    };
  }

  window.salvarAlerta = function () {
    const payload = coletarPayload();
    const url = alertaEditandoId
      ? `${API}/alertas/${alertaEditandoId}`
      : `${API}/alertas`;
    const method = alertaEditandoId ? "PUT" : "POST";
    fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => Promise.reject(d));
        return r.json();
      })
      .then(() => {
        fecharModalAlerta();
        window.location.reload();
      })
      .catch((e) => alert(e.detail || "Erro ao salvar alerta."));
  };

  window.finalizarAlerta = function () {
    const payload = coletarPayload();
    payload.status = "agendado";
    const url = alertaEditandoId
      ? `${API}/alertas/${alertaEditandoId}`
      : `${API}/alertas`;
    const method = alertaEditandoId ? "PUT" : "POST";
    fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => Promise.reject(d));
        return r.json();
      })
      .then((data) => {
        const id = data.id;
        return fetch(`${API}/alertas/${id}/agendar`, { method: "POST" }).then(
          () => {
            fecharModalAlerta();
            window.location.reload();
          },
        );
      })
      .catch((e) => alert(e.detail || "Erro ao finalizar alerta."));
  };

  // ---------- Editar ----------

  window.editarAlerta = function (id) {
    fetch(`${API}/alertas/${id}`)
      .then((r) => r.json())
      .then((data) => {
        alertaEditandoId = id;
        etapaAtual = 1;
        document.getElementById("alerta-id").value = id;
        document.getElementById("modal-titulo").textContent = "Editar Alerta";
        document.getElementById("alerta-nome").value = data.nome || "";
        document.getElementById("alerta-descricao").value =
          data.descricao || "";
        document.getElementById("alerta-status").value =
          data.status || "rascunho";
        document.getElementById("alerta-frequencia").value =
          data.frequencia || "unico";
        document.getElementById("alerta-subtipo").value =
          data.subtipo_recorrencia || "";
        document.getElementById("alerta-timezone").value =
          data.timezone || "America/Sao_Paulo";
        if (data.frequencia === "recorrente" && data.inicio_ciclo_evento_posicao) {
          document.getElementById("evento-rec-dia-ini").value = data.inicio_ciclo_evento_posicao;
        } else {
          document.getElementById("evento-rec-dia-ini").value = "";
        }
        if (data.frequencia === "recorrente" && data.fim_ciclo_evento_posicao) {
          document.getElementById("evento-rec-dia-fim").value = data.fim_ciclo_evento_posicao;
        } else {
          document.getElementById("evento-rec-dia-fim").value = "";
        }
        document.getElementById("alerta-rec-pos-ini").value = data.inicio_ciclo_alerta_posicao || "";
        document.getElementById("alerta-rec-pos-fim").value = data.fim_ciclo_alerta_posicao || "";
        document.getElementById("alerta-condicao").value =
          data.condicao_encerramento || "manual";
        toggleFrequencia();
        fluxosTemp = (data.fluxos || []).map((f) => ({
          tipo_mensagem: f.tipo_mensagem,
          perfis_destinatarios: f.perfis_destinatarios || [],
          usuarios_destinatarios: f.usuarios_destinatarios || [],
          dia_no_ciclo: f.dia_no_ciclo,
          hora_disparo: f.hora_disparo,
          ativo: f.ativo,
        }));
        renderTabelaFluxo();
        atualizarSteps();
        atualizarBotoesModal();
        document.getElementById("modal-alerta").style.display = "flex";
      })
      .catch(() => alert("Erro ao carregar alerta."));
  };

  // ---------- Estado ----------

  function acaoEstado(id, acao, confirmar) {
    if (confirmar && !window.confirm("Confirmar ação?")) return;
    fetch(`${API}/alertas/${id}/${acao}`, { method: "POST" })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => Promise.reject(d));
        return r.json();
      })
      .then(() => window.location.reload())
      .catch((e) => alert(e.detail || "Erro ao executar ação."));
  }

  window.ativarAlerta = function (id) {
    acaoEstado(id, "ativar", false);
  };
  window.pausarAlerta = function (id) {
    acaoEstado(id, "pausar", true);
  };
  window.reativarAlerta = function (id) {
    acaoEstado(id, "reativar", false);
  };
  window.encerrarAlerta = function (id) {
    acaoEstado(id, "encerrar", true);
  };

  window.duplicarAlerta = function (id) {
    if (!window.confirm("Duplicar este alerta?")) return;
    fetch(`${API}/alertas/${id}/duplicar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then((r) => r.json())
      .then(() => window.location.reload())
      .catch(() => alert("Erro ao duplicar."));
  };

  window.excluirAlerta = function (id) {
    if (!window.confirm("Excluir permanentemente este alerta?")) return;
    fetch(`${API}/alertas/${id}`, { method: "DELETE" })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => Promise.reject(d));
        return r.json();
      })
      .then(() => window.location.reload())
      .catch((e) => alert(e.detail || "Erro ao excluir."));
  };

  // ---------- Filtros ----------

  window.filtrarAlertas = function () {
    const busca = document
      .getElementById("busca-alertas")
      .value.toLowerCase()
      .trim();
    const status = document.getElementById("filtro-status").value;
    const frequencia = document.getElementById("filtro-frequencia").value;
    document.querySelectorAll("#cards-grid > .cn-card").forEach((card) => {
      const nome = card.dataset.nome || "";
      const st = card.dataset.status || "";
      const fr = card.dataset.frequencia || "";
      const okNome = !busca || nome.includes(busca);
      const okStatus = !status || st === status;
      const okFreq = !frequencia || fr === frequencia;
      card.style.display = okNome && okStatus && okFreq ? "" : "none";
    });
  };

  // ---------- Logs ----------

  function carregarLogs(alertaId) {
    fetch(`${API}/alertas/${alertaId}/logs?limit=50`)
      .then((r) => r.json())
      .then((data) => {
        const tbody = document.querySelector("#tabela-logs tbody");
        if (!tbody) return;
        tbody.innerHTML = data
          .map(
            (l) => `
          <tr>
            <td>${new Date(l.criado_em).toLocaleString("pt-BR")}</td>
            <td>${l.tipo_evento}</td>
            <td>${l.descricao || "—"}</td>
            <td>${l.usuario_acao_id || "—"}</td>
          </tr>
        `,
          )
          .join("");
      })
      .catch(() => {
        const tbody = document.querySelector("#tabela-logs tbody");
        if (tbody)
          tbody.innerHTML =
            '<tr><td colspan="4">Erro ao carregar logs.</td></tr>';
      });
  }

  // ---------- Init ----------

  document.addEventListener("DOMContentLoaded", function () {
    console.log("[SRA Sender] Central de Alertas carregada.");

    document.addEventListener("click", function (e) {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;
      const id = btn.dataset.id;
      const action = btn.dataset.action;
      if (!id || !action) return;
      switch (action) {
        case "editar":
          editarAlerta(id);
          break;
        case "ativar":
          ativarAlerta(id);
          break;
        case "pausar":
          pausarAlerta(id);
          break;
        case "encerrar":
          encerrarAlerta(id);
          break;
        case "reativar":
          reativarAlerta(id);
          break;
        case "duplicar":
          duplicarAlerta(id);
          break;
        case "excluir":
          excluirAlerta(id);
          break;
      }
    });
  });
})();
