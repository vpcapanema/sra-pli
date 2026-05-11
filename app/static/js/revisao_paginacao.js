/* Paginação A4 do visualizador de revisão editorial.
   =====================================================
   Estratégia:
     - Cada `<div class="rev-sheet" data-orientacao="..." data-rev-secoes-pagina="N">`
       começa com `<div.rev-sheet__body data-rev-paginate-source>` contendo
       uma ou mais `<section.secao>` com seus blocos.
     - Esta rotina coleta todos os "flow items" (header da seção + cada bloco)
       e distribui em folhas A4 fixas (height 297mm portrait / 210mm
       landscape). Quando o body de uma folha overflowa, criamos uma nova
       folha de mesma orientação e continuamos. O h1 da seção é replicado
       no topo da nova folha para preservar a referência hierárquica.
     - Rodada UMA VEZ no DOMContentLoaded, ANTES de qualquer Quill anexar
       (Quill é lazy/foco, então é seguro).
     - Idempotente: marca `data-rev-paginated="1"` nas folhas processadas.
*/
(function () {
  "use strict";

  function paginateSheet(originalSheet) {
    if (originalSheet.dataset.revPaginated === "1") return;
    var body = originalSheet.querySelector("[data-rev-paginate-source]");
    if (!body) return;
    var orient = originalSheet.dataset.orientacao || "portrait";
    var paginaInicial = parseInt(
      originalSheet.dataset.revSecoesPagina || "4",
      10,
    );

    // 1) Coleta flow items
    var sectionEls = Array.from(body.children).filter(function (n) {
      return n.nodeType === 1 && n.matches("section.secao");
    });
    var flow = []; // {type:'section', el} | {type:'bloco', el, sectionRef}
    sectionEls.forEach(function (sec) {
      var children = Array.from(sec.children);
      // Primeiro flow item: a própria seção (vai conter h1 + blocos até overflow)
      flow.push({ type: "section", el: sec, original: sec, children: children });
    });

    // 2) Limpa o body original; vamos reconstruir
    body.innerHTML = "";

    // 3) Helpers
    function makeSheet(landscape, pageNumber) {
      var sheet = originalSheet.cloneNode(false);
      // Remove conteúdo herdado e classes específicas
      sheet.classList.remove("rev-sheet--landscape");
      if (landscape) sheet.classList.add("rev-sheet--landscape");
      sheet.setAttribute("data-orientacao", landscape ? "landscape" : "portrait");
      sheet.dataset.revPaginated = "1";

      // Header (clone do logo)
      var origHdr = originalSheet.querySelector(".rev-sheet__hdr");
      if (origHdr) sheet.appendChild(origHdr.cloneNode(true));

      // Body vazio
      var newBody = document.createElement("div");
      newBody.className = "rev-sheet__body";
      sheet.appendChild(newBody);

      // Footer
      var newFtr = document.createElement("div");
      newFtr.className = "rev-sheet__ftr";
      newFtr.innerHTML =
        '<span>Plano de Logística e Investimentos do Estado de SP | PLI 2050</span>' +
        '<span class="rev-sheet__pg">' +
        pageNumber +
        "</span>";
      sheet.appendChild(newFtr);

      return { sheet: sheet, body: newBody };
    }

    function makeContinuationSection(originalSecEl) {
      // Cria um wrapper <section> com o mesmo h1 e classes, sem blocos.
      // Não duplica o id (apenas a primeira ocorrência fica com id real
      // para garantir uma única âncora). Mantém data-rev-secao-numero
      // para sinalizar continuação ao usuário.
      var wrapper = document.createElement("section");
      wrapper.className = originalSecEl.className;
      wrapper.setAttribute(
        "data-rev-secao-numero",
        originalSecEl.getAttribute("data-rev-secao-numero") || "",
      );
      wrapper.setAttribute("data-rev-continuacao", "1");
      var h1Orig = originalSecEl.querySelector(":scope > h1");
      if (h1Orig) wrapper.appendChild(h1Orig.cloneNode(true));
      return wrapper;
    }

    var paginaAtual = paginaInicial;
    var landscape = orient === "landscape";
    var first = makeSheet(landscape, paginaAtual);
    var currentSheet = first.sheet;
    var currentBody = first.body;
    var currentSection = null; // <section> dentro do currentBody

    // Substitui o originalSheet pela primeira folha
    originalSheet.replaceWith(currentSheet);
    var insertionAnchor = currentSheet;

    function newPage() {
      paginaAtual += 1;
      var built = makeSheet(landscape, paginaAtual);
      insertionAnchor.parentNode.insertBefore(
        built.sheet,
        insertionAnchor.nextSibling,
      );
      insertionAnchor = built.sheet;
      currentSheet = built.sheet;
      currentBody = built.body;
      currentSection = null;
    }

    function overflowsBody() {
      // Considera overflow quando scrollHeight ultrapassa clientHeight do
      // body. Margem de 1px para evitar falso-positivo por arredondamento.
      return currentBody.scrollHeight > currentBody.clientHeight + 1;
    }

    function appendBloco(blocoEl, ownerSectionOriginal) {
      if (!currentSection) {
        // Cria seção destino (cópia do h1 da seção original)
        var continuation = makeContinuationSection(ownerSectionOriginal);
        currentBody.appendChild(continuation);
        currentSection = continuation;
      }
      currentSection.appendChild(blocoEl);
      if (overflowsBody() && currentSection.children.length > 1) {
        // bloco causou overflow — tira, vai para nova folha
        currentSection.removeChild(blocoEl);
        newPage();
        var continuation2 = makeContinuationSection(ownerSectionOriginal);
        currentBody.appendChild(continuation2);
        currentSection = continuation2;
        currentSection.appendChild(blocoEl);
        // Se ainda assim overflowa (bloco muito grande), aceita e segue.
      }
    }

    function startSection(secOriginal, children) {
      // Cria a <section> "primária" — leva o id real
      var sec = document.createElement("section");
      sec.id = secOriginal.id;
      sec.className = secOriginal.className;
      Array.from(secOriginal.attributes).forEach(function (a) {
        if (a.name === "id" || a.name === "class") return;
        sec.setAttribute(a.name, a.value);
      });
      // Adiciona h1
      var h1 = children.find(function (c) { return c.tagName === "H1"; });
      if (h1) sec.appendChild(h1.cloneNode(true));

      currentBody.appendChild(sec);
      if (overflowsBody() && currentBody.children.length > 1) {
        // header da seção sozinho não cabe (caso raro) — quebra para nova folha
        currentBody.removeChild(sec);
        newPage();
        currentBody.appendChild(sec);
      }
      currentSection = sec;

      // Distribui blocos
      var blocos = children.filter(function (c) { return c.tagName !== "H1"; });
      blocos.forEach(function (blocoEl) {
        appendBloco(blocoEl, secOriginal);
      });
    }

    // 4) Itera flow processando cada seção
    flow.forEach(function (item) {
      if (item.type === "section") {
        startSection(item.original, item.children);
      }
    });
  }

  function paginateAll() {
    var sheets = Array.from(
      document.querySelectorAll(
        ".rev-sheet[data-rev-secoes-pagina][data-orientacao]",
      ),
    );
    sheets.forEach(paginateSheet);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", paginateAll, { once: true });
  } else {
    paginateAll();
  }
})();
