(function () {
  const modal = document.getElementById("modal-editar-lote-sumario");
  const btnAbrir = document.getElementById("btn-editar-lote-sumario");
  const btnFechar = document.getElementById("fechar-modal-editar-lote");
  const campoEditar = document.getElementById("campo-editar");
  const valorEditar = document.getElementById("valor-editar");
  const btnAplicar = document.getElementById("btn-aplicar-lote");
  const secoesList = document.getElementById("secoes-list");
  const selectAllSecoes = document.getElementById("select-all-secoes");
  const selecionadosCount = document.getElementById("selecionados-count");

  let editLoteData = {};

  try {
    const dataEl = document.getElementById("edit-lote-data");
    if (dataEl) {
      editLoteData = JSON.parse(dataEl.textContent);
    }
  } catch (e) {
    console.error("Erro ao ler dados de edição em lote:", e);
  }

  // Abrir modal
  if (btnAbrir && modal) {
    btnAbrir.addEventListener("click", () => {
      modal.showModal();
    });
  }

  // Fechar modal
  if (btnFechar && modal) {
    btnFechar.addEventListener("click", () => {
      modal.close();
    });
  }

  // Fechar ao clicar fora
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        modal.close();
      }
    });
  }

  // Selecionar todas as seções
  if (selectAllSecoes && secoesList) {
    selectAllSecoes.addEventListener("change", () => {
      const checkboxes = secoesList.querySelectorAll('input[name="secao_ids"]');
      checkboxes.forEach((cb) => {
        cb.checked = selectAllSecoes.checked;
      });
      atualizarEstadoBotao();
      atualizarContador();
    });
  }

  // Atualizar contador de seções selecionadas
  function atualizarContador() {
    const count =
      secoesList?.querySelectorAll('input[name="secao_ids"]:checked').length ||
      0;
    if (selecionadosCount) {
      selecionadosCount.textContent = `${count} seção(ões) selecionada(s)`;
    }
  }

  // Atualizar opções de valor baseado no campo selecionado
  if (campoEditar) {
    campoEditar.addEventListener("change", () => {
      const campo = campoEditar.value;
      valorEditar.innerHTML = '<option value="">Selecione um valor</option>';

      if (campo === "responsavel_id") {
        editLoteData.autores?.forEach((autor) => {
          const option = document.createElement("option");
          option.value = autor.id;
          option.textContent = autor.nome;
          valorEditar.appendChild(option);
        });
      } else if (campo === "status") {
        editLoteData.statusOptions?.forEach((opt) => {
          const option = document.createElement("option");
          option.value = opt.value;
          option.textContent = opt.label;
          valorEditar.appendChild(option);
        });
      }

      valorEditar.disabled = false;
      atualizarEstadoBotao();
    });
  }

  // Atualizar estado do botão de aplicar
  function atualizarEstadoBotao() {
    const secoesSelecionadas = secoesList?.querySelectorAll(
      'input[name="secao_ids"]:checked',
    );
    const campoSelecionado = campoEditar?.value;
    const valorSelecionado = valorEditar?.value;

    if (btnAplicar) {
      btnAplicar.disabled = !(
        secoesSelecionadas?.length > 0 &&
        campoSelecionado &&
        valorSelecionado
      );
    }
  }

  // Atualizar estado ao selecionar seções
  if (secoesList) {
    secoesList.addEventListener("change", (e) => {
      if (e.target.name === "secao_ids") {
        // Atualizar checkbox "selecionar todas"
        const checkboxes = secoesList.querySelectorAll(
          'input[name="secao_ids"]',
        );
        const allChecked = Array.from(checkboxes).every((cb) => cb.checked);
        if (selectAllSecoes) {
          selectAllSecoes.checked = allChecked;
        }
        atualizarEstadoBotao();
        atualizarContador();
      }
    });
  }

  // Atualizar estado ao selecionar valor
  if (valorEditar) {
    valorEditar.addEventListener("change", atualizarEstadoBotao);
  }

  // Aplicar mudanças em lote
  if (btnAplicar) {
    btnAplicar.addEventListener("click", async () => {
      const secoesSelecionadas = Array.from(
        secoesList?.querySelectorAll('input[name="secao_ids"]:checked') || [],
      ).map((cb) => cb.value);

      const campo = campoEditar?.value;
      const valor = valorEditar?.value;

      if (!secoesSelecionadas.length || !campo || !valor) {
        alert("Selecione seções, campo e valor");
        return;
      }

      if (
        !confirm(
          `Aplicar ${campo} = ${valor} para ${secoesSelecionadas.length} seção(ões)?`,
        )
      ) {
        return;
      }

      try {
        const resp = await fetch(
          `/relatorios/${editLoteData.relId}/secoes/editar-lote`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              campo,
              valor,
              secao_ids: secoesSelecionadas,
            }),
          },
        );

        if (!resp.ok) {
          const data = await resp.json();
          throw new Error(data.detail || "Erro ao aplicar mudanças");
        }

        alert("Mudanças aplicadas com sucesso!");
        modal.close();
        location.reload();
      } catch (error) {
        alert("Erro ao aplicar mudanças: " + error.message);
      }
    });
  }
})();
