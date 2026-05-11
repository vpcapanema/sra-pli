/* Paginação A4 do visualizador de revisão editorial.
   ============================================================
   Algoritmo:
     - Para cada `<div class="rev-sheet" data-rev-paginate-source-root>`,
       extrai todos os blocos do body, depois reanexa um a um.
     - Quando o body overflowa, primeiro tenta DIVIDIR o bloco que causou
       o overflow (split por <li>, <tr> ou parágrafo). Se não couber
       nenhuma parte na folha atual, cria nova folha A4 com continuação.
     - Se o bloco é indivisível (figura única) e SOZINHO já excede A4,
       aceita overflow nessa folha (caso isolado, sem como dividir).
     - Remove folhas residuais com apenas o h1 da seção (sem blocos).
*/
(function () {
  "use strict";

  function log() {
    if (window.SRA_LOG && window.SRA_LOG.debug) {
      window.SRA_LOG.debug.apply(window.SRA_LOG, arguments);
    }
  }

  // ---------- Detecção de containers divisíveis dentro de um .bloco ----------
  function findSplittableContainer(bloco) {
    // Caso 1: o próprio nó é uma lista/tabela divisível (ex.: <ol> do sumário)
    if (
      (bloco.tagName === "UL" || bloco.tagName === "OL") &&
      bloco.children.length > 1
    ) {
      return { kind: "list", node: bloco, self: true };
    }
    if (bloco.tagName === "TABLE") {
      var tb0 = bloco.querySelector(":scope > tbody");
      if (tb0 && tb0.children.length > 1) {
        return { kind: "tbody", node: tb0, table: bloco, self: true };
      }
    }
    // Caso 2: container "natural" interno ao bloco editorial.
    // Preferência: <ul>/<ol>, <table tbody>, depois o body do bloco.
    var ul = bloco.querySelector(
      ":scope > .rev-block__body > ul, :scope > .rev-block__body > ol, :scope > ul, :scope > ol",
    );
    if (ul && ul.children.length > 1) return { kind: "list", node: ul };
    var tbody = bloco.querySelector(
      ":scope > .tabela > table > tbody, :scope > .rev-block__body > table > tbody",
    );
    if (tbody && tbody.children.length > 1) {
      return { kind: "tbody", node: tbody, table: tbody.parentNode };
    }
    var body = bloco.querySelector(":scope > .rev-block__body");
    if (body && body.children.length > 1) return { kind: "body", node: body };
    return null;
  }

  // Cria um clone "vazio" do bloco para ser preenchido com o overflow.
  // Mantém atributos (classes, data-bloco-id é REMOVIDO para não duplicar
  // âncora do DOM; usamos data-rev-bloco-continuacao para marcar).
  function cloneBlocoShell(orig) {
    var shell = orig.cloneNode(false);
    shell.removeAttribute("id");
    shell.removeAttribute("data-bloco-id");
    shell.setAttribute("data-rev-bloco-continuacao", "1");
    // Não-editável na continuação (a edição real fica no bloco original).
    shell.setAttribute("data-readonly", "1");
    return shell;
  }

  // Para split de listas: cria um wrapper bloco com <ul>/<ol> contendo só
  // os <li> de overflow.
  function buildListContinuation(orig, listNode, tailLis) {
    var shell = cloneBlocoShell(orig);
    var bodyOrig = orig.querySelector(":scope > .rev-block__body");
    var newBody = document.createElement("div");
    newBody.className = "rev-block__body";
    if (bodyOrig) {
      var attrs = bodyOrig.attributes;
      for (var i = 0; i < attrs.length; i++) {
        if (attrs[i].name !== "id") {
          newBody.setAttribute(attrs[i].name, attrs[i].value);
        }
      }
      newBody.removeAttribute("data-edit-field");
      newBody.removeAttribute("data-edit-mode");
    }
    var newList = document.createElement(listNode.tagName);
    for (var j = 0; j < listNode.attributes.length; j++) {
      newList.setAttribute(
        listNode.attributes[j].name,
        listNode.attributes[j].value,
      );
    }
    tailLis.forEach(function (li) {
      newList.appendChild(li);
    });
    newBody.appendChild(newList);
    shell.appendChild(newBody);
    return shell;
  }

  // Para split de tabelas: cria um wrapper bloco com a mesma <table>
  // (incluindo <thead> clonado se houver) contendo só os <tr> de overflow.
  function buildTableContinuation(orig, tbodyNode, table, tailRows) {
    var shell = cloneBlocoShell(orig);
    var tabelaOrig = orig.querySelector(":scope > .tabela");
    var newTabela = document.createElement("div");
    newTabela.className = (tabelaOrig && tabelaOrig.className) || "tabela";
    var newTable = document.createElement("table");
    for (var i = 0; i < table.attributes.length; i++) {
      newTable.setAttribute(
        table.attributes[i].name,
        table.attributes[i].value,
      );
    }
    var thead = table.querySelector(":scope > thead");
    if (thead) newTable.appendChild(thead.cloneNode(true));
    var newTbody = document.createElement("tbody");
    for (var k = 0; k < tbodyNode.attributes.length; k++) {
      newTbody.setAttribute(
        tbodyNode.attributes[k].name,
        tbodyNode.attributes[k].value,
      );
    }
    tailRows.forEach(function (tr) {
      newTbody.appendChild(tr);
    });
    newTable.appendChild(newTbody);
    newTabela.appendChild(newTable);
    shell.appendChild(newTabela);
    return shell;
  }

  // Para split de body genérico (texto): cria wrapper bloco com os
  // children que sobraram.
  function buildBodyContinuation(orig, bodyNode, tailKids) {
    var shell = cloneBlocoShell(orig);
    var newBody = document.createElement("div");
    for (var i = 0; i < bodyNode.attributes.length; i++) {
      newBody.setAttribute(
        bodyNode.attributes[i].name,
        bodyNode.attributes[i].value,
      );
    }
    newBody.removeAttribute("data-edit-field");
    newBody.removeAttribute("data-edit-mode");
    tailKids.forEach(function (k) {
      newBody.appendChild(k);
    });
    shell.appendChild(newBody);
    return shell;
  }

  // ---------- Flatten de uma rev-sheet em items ordenados ----------
  // Aceita seções editoriais (section.secao com h1) e seções "estruturais"
  // como o sumário (section.sumario com h2). Para a sumário, o "h1" lógico
  // do shell é o próprio h2 ("Sumário"), e os filhos (ol/ul) entram como
  // blocos divisíveis.
  function flattenSheet(sourceBody) {
    var items = [];
    var sections = Array.from(sourceBody.children).filter(function (n) {
      return (
        n.nodeType === 1 &&
        (n.matches("section.secao") || n.matches("section.sumario"))
      );
    });
    sections.forEach(function (sec) {
      var children = Array.from(sec.children);
      var shell = sec.cloneNode(false);
      var heading = children.find(function (c) {
        return c.tagName === "H1" || c.tagName === "H2";
      });
      if (heading) shell.appendChild(heading.cloneNode(true));
      items.push({ kind: "section", node: shell, orig: sec });
      children.forEach(function (c) {
        if (c.tagName === "H1" || c.tagName === "H2") return;
        items.push({ kind: "bloco", node: c, orig: sec });
      });
    });
    return items;
  }

  function makeSheetClone(origSheet, pageNo) {
    var sheet = origSheet.cloneNode(false);
    sheet.dataset.revPaginated = "1";
    sheet.removeAttribute("data-rev-paginate-source-root");

    var origHdr = origSheet.querySelector(":scope > .rev-sheet__hdr");
    if (origHdr) sheet.appendChild(origHdr.cloneNode(true));

    var newBody = document.createElement("div");
    newBody.className = "rev-sheet__body";
    sheet.appendChild(newBody);

    var newFtr = document.createElement("div");
    newFtr.className = "rev-sheet__ftr";
    newFtr.innerHTML =
      "<span>Plano de Logística e Investimentos do Estado de SP | PLI 2050</span>" +
      '<span class="rev-sheet__pg">' +
      pageNo +
      "</span>";
    sheet.appendChild(newFtr);
    return { sheet: sheet, body: newBody };
  }

  function paginateOne(origSheet) {
    if (origSheet.dataset.revPaginated === "1") return;
    var sourceBody = origSheet.querySelector(
      ":scope > [data-rev-paginate-source]",
    );
    if (!sourceBody) return;

    var paginaInicial = parseInt(origSheet.dataset.revSecoesPagina || "4", 10);
    var isLandscape = origSheet.dataset.orientacao === "landscape";
    var MM_TO_PX = 96 / 25.4;
    var sheetLimitPx = (isLandscape ? 210 : 297) * MM_TO_PX;

    var items = flattenSheet(sourceBody);
    log("[rev-paginate] sheet", origSheet, "items:", items.length);

    var paginaAtual = paginaInicial;
    var first = makeSheetClone(origSheet, paginaAtual);
    var currentSection = null;
    origSheet.replaceWith(first.sheet);

    var currentSheet = first.sheet;
    var currentBody = first.body;
    var allSheets = [currentSheet];

    function overflow() {
      return currentSheet.offsetHeight > sheetLimitPx + 0.5;
    }

    function newSheet() {
      paginaAtual += 1;
      var built = makeSheetClone(origSheet, paginaAtual);
      currentSheet.parentNode.insertBefore(
        built.sheet,
        currentSheet.nextSibling,
      );
      currentSheet = built.sheet;
      currentBody = built.body;
      currentSection = null;
      allSheets.push(currentSheet);
    }

    function ensureSection(orig) {
      if (currentSection && currentBody.contains(currentSection)) return;
      var continuation = orig.cloneNode(false);
      // Em seções de continuação NÃO repetimos o h1/h2 — o título aparece
      // apenas onde a seção começa (mesmo padrão do Word/PDF tradicional).
      continuation.setAttribute("data-rev-continuacao", "1");
      continuation.removeAttribute("id");
      currentBody.appendChild(continuation);
      currentSection = continuation;
    }

    // Tenta dividir o bloco (que já está em currentSection e overflowa).
    // Retorna o bloco-continuação a ser processado a seguir, ou null se
    // não foi possível dividir (bloco indivisível).
    function trySplitOverflowingBloco(bloco) {
      var split = findSplittableContainer(bloco);
      if (!split) return null;

      var container = split.node;
      var tail = [];
      // Vai removendo do final até caber, ou até sobrar 1 elemento.
      while (overflow() && container.children.length > 1) {
        var last = container.lastElementChild;
        container.removeChild(last);
        tail.unshift(last);
      }
      if (tail.length === 0) return null;
      // Se ainda overflowa com 1 só item, não há como dividir mais.
      if (overflow() && container.children.length <= 1) {
        // Restaura o tail ao container (não conseguiu dividir útil)
        // e retorna null para sinalizar split inviável.
        tail.forEach(function (t) {
          container.appendChild(t);
        });
        return null;
      }

      // Quando o próprio bloco é a lista/tabela (sumário, p.ex.), a
      // continuação é apenas um clone vazio do container com o tail.
      if (split.self && split.kind === "list") {
        var newList = container.cloneNode(false);
        newList.setAttribute("data-rev-bloco-continuacao", "1");
        tail.forEach(function (li) {
          newList.appendChild(li);
        });
        return newList;
      }
      if (split.self && split.kind === "tbody") {
        var newTable = container.parentNode.cloneNode(false);
        newTable.setAttribute("data-rev-bloco-continuacao", "1");
        var thead0 = container.parentNode.querySelector(":scope > thead");
        if (thead0) newTable.appendChild(thead0.cloneNode(true));
        var newTbody0 = container.cloneNode(false);
        tail.forEach(function (tr) {
          newTbody0.appendChild(tr);
        });
        newTable.appendChild(newTbody0);
        return newTable;
      }

      if (split.kind === "list") {
        return buildListContinuation(bloco, container, tail);
      }
      if (split.kind === "tbody") {
        return buildTableContinuation(bloco, container, split.table, tail);
      }
      // body
      return buildBodyContinuation(bloco, container, tail);
    }

    // Distribui itens
    var queue = items.slice();
    var safety = items.length * 50; // proteção anti-loop
    while (queue.length > 0 && safety-- > 0) {
      var item = queue.shift();

      if (item.kind === "section") {
        currentBody.appendChild(item.node);
        if (overflow() && currentBody.children.length > 1) {
          currentBody.removeChild(item.node);
          newSheet();
          currentBody.appendChild(item.node);
        }
        currentSection = item.node;
        continue;
      }

      // bloco
      ensureSection(item.orig);
      currentSection.appendChild(item.node);

      if (!overflow()) continue;

      // Overflow — tenta dividir
      var firstBlocoOnSection =
        Array.from(currentSection.children).filter(function (c) {
          return c.tagName !== "H1";
        }).length === 1;

      var continuation = trySplitOverflowingBloco(item.node);

      if (continuation) {
        // Conseguiu dividir: a parte que ficou cabe (ou está perto).
        // A continuação vai pra próxima folha (re-enfileira).
        queue.unshift({
          kind: "bloco",
          node: continuation,
          orig: item.orig,
        });
        // Se mesmo após split ainda overflowa (caso raro), força nova folha
        if (overflow() && currentSection.children.length > 1) {
          currentSection.removeChild(item.node);
          // re-enfileira o bloco original (com seu conteúdo restante) também
          queue.unshift({ kind: "bloco", node: item.node, orig: item.orig });
          newSheet();
        }
        continue;
      }

      // Não pôde dividir
      if (firstBlocoOnSection) {
        // Bloco é o único da seção e é indivisível. Aceita overflow nesta
        // folha (caso de figura/tabela enorme isolada).
        continue;
      }

      // Há outros blocos antes: retira esse bloco e leva pra próxima folha.
      currentSection.removeChild(item.node);
      newSheet();
      ensureSection(item.orig);
      currentSection.appendChild(item.node);
      // Se ainda overflowa, tenta dividir nessa nova folha
      if (overflow()) {
        var cont2 = trySplitOverflowingBloco(item.node);
        if (cont2) {
          queue.unshift({
            kind: "bloco",
            node: cont2,
            orig: item.orig,
          });
        }
      }
    }

    // Limpa folhas residuais: seções com apenas <h1> e folhas vazias.
    allSheets.forEach(function (sh) {
      var body = sh.querySelector(":scope > .rev-sheet__body");
      if (!body) return;
      Array.from(body.children).forEach(function (sec) {
        if (!sec.matches) return;
        if (!sec.matches("section.secao") && !sec.matches("section.sumario"))
          return;
        var hasContent = Array.from(sec.children).some(function (c) {
          return c.tagName !== "H1" && c.tagName !== "H2";
        });
        if (!hasContent) sec.remove();
      });
      if (body.children.length === 0) {
        sh.remove();
      }
    });
  }

  function paginateAll() {
    var sheets = Array.from(
      document.querySelectorAll(".rev-sheet[data-rev-paginate-source-root]"),
    );
    log("[rev-paginate] start; sheets:", sheets.length);
    sheets.forEach(function (s) {
      try {
        paginateOne(s);
      } catch (err) {
        if (window.console && window.console.error) {
          window.console.error("[rev-paginate] erro:", err);
        }
      }
    });
    log("[rev-paginate] done");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", paginateAll, { once: true });
  } else {
    paginateAll();
  }
})();
