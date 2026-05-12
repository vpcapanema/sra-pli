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
  }

  function toggleEventoForm() {
    const freq = document.getElementById("alerta-frequencia").value;
    const subtipo = document.getElementById("alerta-subtipo").value;
    const unicoForm = document.getElementById("evento-unico-form");
    const recForm = document.getElementById("evento-recorrente-form");
    const hint = document.getElementById("evento-rec-hint");
    if (!unicoForm || !recForm) return;
    if (freq === "recorrente") {
      unicoForm.style.display = "none";
      recForm.style.display = "block";
      const labelMap = {
        horaria: "Minuto do ciclo",
        diaria: "Dia do ciclo",
        semanal: "Dia da semana (1=Seg … 7=Dom)",
        quinzenal: "Dia da semana (1=Seg … 7=Dom)",
        mensal: "Dia do mês",
        anual: "Dia e mês (DD/MM)",
        customizada: "Dia do ciclo",
      };
      const label = labelMap[subtipo] || "Dia do ciclo";
      document.getElementById("evento-rec-dia-ini").placeholder = label;
      document.getElementById("evento-rec-dia-fim").placeholder = label;
      if (hint) {
        hint.textContent =
          "Informe o dia relativo ao ciclo de recorrência e o horário.";
      }
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
    const colunaDireita = document.getElementById("coluna-direita-frequencia");
    campoSubtipo.style.display = freq === "recorrente" ? "block" : "none";
    if (freq !== "recorrente") {
      colunaDireita.style.display = "none";
      document.getElementById("alerta-subtipo").value = "";
      document.querySelectorAll('[id^="rec-"]').forEach(function (el) {
        el.style.display = "none";
      });
    }
    toggleEventoForm();
  };

  window.toggleSubtipoRecorrencia = function () {
    const subtipo = document.getElementById("alerta-subtipo").value;
    const colunaDireita = document.getElementById("coluna-direita-frequencia");
    document.querySelectorAll('[id^="rec-"]').forEach(function (el) {
      el.style.display = "none";
    });
    if (!subtipo) {
      colunaDireita.style.display = "none";
      return;
    }
    colunaDireita.style.display = "block";
    switch (subtipo) {
      case "horaria":
        document.getElementById("rec-horaria").style.display = "block";
        document.getElementById("rec-horario").style.display = "block";
        break;
      case "diaria":
      case "semanal":
      case "quinzenal":
        document.getElementById("rec-dias-semana").style.display = "block";
        document.getElementById("rec-horario").style.display = "block";
        break;
      case "mensal":
        document.getElementById("rec-mensal").style.display = "block";
        document.getElementById("rec-horario").style.display = "block";
        break;
      case "anual":
        document.getElementById("rec-anual").style.display = "block";
        document.getElementById("rec-horario").style.display = "block";
        break;
      case "customizada":
        document.getElementById("rec-customizada").style.display = "block";
        break;
    }
    toggleEventoForm();
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
    let inicioEvento, fimEvento;
    if (freq === "recorrente") {
      const dIni = document.getElementById("evento-rec-dia-ini").value;
      const hIni = document.getElementById("evento-rec-hora-ini").value;
      const dFim = document.getElementById("evento-rec-dia-fim").value;
      const hFim = document.getElementById("evento-rec-hora-fim").value;
      if (dIni && hIni) {
        inicioEvento = "2000-01-" + String(dIni).padStart(2, "0") + "T" + hIni;
      }
      if (dFim && hFim) {
        fimEvento = "2000-01-" + String(dFim).padStart(2, "0") + "T" + hFim;
      }
    } else {
      inicioEvento = document.getElementById("evento-inicio").value || null;
      fimEvento = document.getElementById("evento-fim").value || null;
    }
    return {
      nome: document.getElementById("alerta-nome").value,
      descricao: document.getElementById("alerta-descricao").value,
      status: document.getElementById("alerta-status").value,
      frequencia: freq,
      subtipo_recorrencia:
        document.getElementById("alerta-subtipo").value || null,
      timezone: document.getElementById("alerta-timezone").value,
      inicio_evento: inicioEvento || null,
      fim_evento: fimEvento || null,
      inicio_alerta: document.getElementById("alerta-inicio").value || null,
      fim_alerta: document.getElementById("alerta-fim").value || null,
      condicao_encerramento: document.getElementById("alerta-condicao").value,
      data_inicio_disparos:
        document.getElementById("alerta-inicio-disparos").value || null,
      dias_semana: diasSemana.length ? diasSemana : null,
      intervalo_horario_inicio:
        document.getElementById("alerta-hora-ini").value || null,
      intervalo_horario_fim:
        document.getElementById("alerta-hora-fim").value || null,
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
        if (data.frequencia === "recorrente" && data.inicio_evento) {
          const dtIni = new Date(data.inicio_evento);
          document.getElementById("evento-rec-dia-ini").value = dtIni.getDate();
          document.getElementById("evento-rec-hora-ini").value =
            String(dtIni.getHours()).padStart(2, "0") +
            ":" +
            String(dtIni.getMinutes()).padStart(2, "0");
        } else {
          document.getElementById("evento-rec-dia-ini").value = "";
          document.getElementById("evento-rec-hora-ini").value = "08:00";
        }
        if (data.frequencia === "recorrente" && data.fim_evento) {
          const dtFim = new Date(data.fim_evento);
          document.getElementById("evento-rec-dia-fim").value = dtFim.getDate();
          document.getElementById("evento-rec-hora-fim").value =
            String(dtFim.getHours()).padStart(2, "0") +
            ":" +
            String(dtFim.getMinutes()).padStart(2, "0");
        } else {
          document.getElementById("evento-rec-dia-fim").value = "";
          document.getElementById("evento-rec-hora-fim").value = "18:00";
        }
        document.getElementById("evento-inicio").value = data.inicio_evento
          ? data.inicio_evento.slice(0, 16)
          : "";
        document.getElementById("evento-fim").value = data.fim_evento
          ? data.fim_evento.slice(0, 16)
          : "";
        document.getElementById("alerta-inicio").value = data.inicio_alerta
          ? data.inicio_alerta.slice(0, 16)
          : "";
        document.getElementById("alerta-fim").value = data.fim_alerta
          ? data.fim_alerta.slice(0, 16)
          : "";
        document.getElementById("alerta-condicao").value =
          data.condicao_encerramento || "manual";
        document.getElementById("alerta-inicio-disparos").value =
          data.data_inicio_disparos
            ? data.data_inicio_disparos.slice(0, 16)
            : "";
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
