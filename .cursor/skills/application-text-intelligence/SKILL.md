---
name: application-text-intelligence
description: >-
  Extracao/classificacao de texto, interpretacao de documentos, pipelines de importacao assistida,
  alocacao em secoes ou grupos, PDF, DOCX, HTML, TXT, OCR, NLP, parsers e revisao humana antes de
  persistir. Use quando o pedido envolver texto, documentos ou fluxo semelhante ao importador do SRA.
---

# Application Text Intelligence (SRA)

Especialista em aplicacoes orientadas a documentos e texto no repositorio SRA.

## Especialidade

- Criacao de fluxos robustos para extrair, interpretar, estruturar, classificar e alocar conteudos em secoes, grupos ou blocos.
- Extracao de texto de DOCX, PDF, TXT, HTML, Markdown, CSV, XLSX e imagens com OCR quando necessario.
- Interpretacao semantica: cabecalhos, listas, tabelas, figuras, legendas e metadados.
- Classificacao por regras, regex, similaridade, estrutura, palavras-chave ou modelos conforme risco e necessidade.
- Pipelines com revisao assistida antes de gravar dados definitivos.

## Bibliotecas E Ferramentas Que Deve Considerar

Escolha conforme formato e qualidade do documento. Nao adicione dependencia sem justificar ganho real.

- DOCX: `python-docx`; `mammoth` para HTML limpo a partir de DOCX.
- PDF texto: `pypdf`; `pdfplumber` para layout/tabelas; `PyMuPDF`/`fitz` para paginas complexas ou performance.
- PDF escaneado: OCR (`pytesseract` ou servico); marcar confianca e exigir revisao humana.
- HTML/XML: `BeautifulSoup`, `lxml` ou parser nativo.
- Tabelas: `pandas`, `openpyxl`, `csv`.
- NLP: regex, `rapidfuzz`, classificadores leves, embeddings quando houver ambiguidade clara.
- Validacao com `pydantic` ou estruturas equivalentes antes de persistir.

## Alocacao De Textos Em Secoes Ou Grupos

1. Entenda a taxonomia de destino: secoes, numeros, titulos, aliases, ordem e permissoes.
2. Preserve estrutura original: ordem, hierarquia, titulos, tabelas, imagens e fontes.
3. Separe extracao de interpretacao: primeiro elementos brutos, depois classificacao por elemento.
4. Sinais fortes antes de IA: numero de secao, heading, marcadores, tabela nativa, nome de arquivo e proximidade.
5. Similaridade textual com limiar de confianca e justificativa para titulos aproximados.
6. Baixa confianca: revisao humana, nao persistencia automatica.
7. Pre-visualizacao editavel com secao sugerida, tipo, titulo, conteudo, legenda, fonte, confianca e motivo.
8. Persistir somente confirmado, com auditoria minima da importacao.

## Padrao De Implementacao

- Pipeline em etapas pequenas: carregar, extrair, normalizar, classificar, revisar, confirmar e persistir.
- Contratos de dados claros entre etapas, preferindo estruturas tipadas.
- Parsers principais testaveis e separados da UI onde fizer sentido.
- Idempotencia quando possivel ao reprocessar o mesmo documento.
- Erros por item quando recuperavel.

## Regras Para Este Repositorio

- Frontend permanece HTML/Jinja2/CSS/JS simples — nao use React neste projeto.
- Sistema real de producao — nao substitua fluxo real por mock.
- Respeitar `Relatorio`, `Secao`, `Bloco` e `Figura` como conceitos centrais.
- Na importacao SRA: nao repetir o titulo da secao como titulo de todos os blocos.
- Linhas que representam secao existente sao destino de conteudo, nao texto repetido.
- DOCX: preservar imagem, legenda e fonte juntas quando possivel.

## Checklist Antes De Concluir

- Releia integralmente os arquivos alterados; corrija inconsistencias relevantes no escopo dos arquivos tocados.
- Zere ou justifique Itens na aba Problemas nos arquivos alterados.
- Valide objetivamente: parser/amostras, import do app, endpoint, render, persistencia ou teste.

## Formato Da Resposta Final

Objetivamente, em pt-BR: fluxo ou aplicacao projetada; bibliotecas e estrategia de extracao/classificacao; como textos foram alocados; arquivos alterados; validacoes e estado dos Problemas; riscos residuais.

## Fonte Canonica Do Dominio

Leia sempre `.cursor/project-instructions.md` antes de mudar comportamento persistente ou modelos.
