---
name: melhorar-upload-conteudo
description: >-
  Melhorar extracao e classificacao no upload/importacao de conteudo do SRA (TXT/DOCX, revisao assistida).
  Também use /application-text-intelligence para contexto geral sobre pipelines de texto neste projeto.
disable-model-invocation: true
---

# Melhorar upload de conteúdo (SRA)

Fluxo existente na tela de secao/importacao — nao redesenhar a aplicacao do zero.

## Contexto Do Codigo Atual

- Importador principal: `app/routes/importacao.py`.
- Interface: `app/templates/secao_edit_conteudo_upload.html`.
- Fluxo atual: aceita `.txt` e `.docx`, analisa, retorna blocos para revisao, persiste apos confirmacao; DOCX pode criar `Figura` quando houver imagem embutida.

## Objetivo

Melhorar extracao, reconhecimento de estruturas e alocacao em secoes/blocos/grupos; manter revisao assistida obrigatoria para persistencia.

## Escopo Dinamico

- Sem hardcodar numero/nome especifico de secao na logica de parser — taxonomia vem das secoes reais do relatorio.
- Indicacao de secao pelo usuario ou usuario no documento deve ser parametro/contexto inferido, nao constante fixa no codigo.
- Sem correspondencia confiavel: manter revisao para escolha de secao.

## Prioridade De Arquivos

- `app/routes/importacao.py`
- `app/templates/secao_edit_conteudo_upload.html`
- `app/models.py`, `app/pdf_render.py`, `app/templates/pdf/relatorio.html`, `.cursor/project-instructions.md`

## Diretrizes Tecnicas

- Manter revisao antes de criar blocos definitivos.
- Fluxo frontend HTML/Jinja2 (sem React no projeto padrao).
- Sem mocks substituindo comportamento real.
- Dependências novas so com ganho claro — preferir parsers em funcoes pequenas e testaveis.
- Compatível com TXT e DOCX atual; expansoes novas incrementais.

## Criterios De Qualidade

- Nao repetir titulo da secao em todos os blocos.
- Linhas denotando secao definem destino, nao bloco repetido.
- Preservar ordem e, quando possivel, figura + legenda + fonte no DOCX.

## Validacao Antes De Concluir

- Testes/objetivas com TXT e DOCX; mostrar genericidade (nao apenas uma numeracao fixa).
- `import app.main`; releitura integral dos alterados.
- Zerar ou justificar Notificacoes dos arquivos alterados na aba Problemas.

Consulte **`/application-text-intelligence`** para filosofia de parsers, OCR e ferramentas sugeridas.
