---
name: "Melhorar Upload De Conteudo"
description: "Use para acionar o agente de inteligencia textual e melhorar a extracao, interpretacao, classificacao e alocacao de textos no upload/importacao de conteudo do SRA."
agent: "Application Text Intelligence Architect"
argument-hint: "Descreva os formatos/problematicas do upload, quais secoes/grupos devem ser usados e o resultado esperado por secao/bloco."
tools: [read, search, edit, execute, todo]
---

Melhore o fluxo existente de upload/importacao de conteudo do SRA, sem reescrever a aplicacao do zero.

## Contexto

A aplicacao ja possui um importador assistido em `app/routes/importacao.py`, integrado na tela `app/templates/secao_edit.html`.

O fluxo atual aceita `.txt` e `.docx`, analisa o arquivo, retorna blocos em JSON para revisao humana e so persiste depois da confirmacao. Ao confirmar, cria `Bloco` e, quando houver imagem embutida no DOCX, cria `Figura` vinculada.

O objetivo e melhorar o que ja existe nesse fluxo: extracao, reconhecimento, interpretacao, classificacao e alocacao dos textos importados em secoes/blocos corretos.

O prompt nao deve induzir solucao presa a uma secao especifica. O agente deve funcionar para qualquer secao ou grupo indicado pelo usuario, ou para qualquer secao existente no relatorio quando o destino puder ser inferido pelo numero, titulo, alias, contexto ou similaridade textual.

## Tarefa

Analise o upload/importador atual e implemente melhorias cirurgicas para que ele reconheca melhor:

- linhas que representam secoes reais do relatorio;
- titulos e subtitulos numerados;
- paragrafos comuns;
- listas;
- tabelas nativas de DOCX ou tabelas textuais;
- figuras, imagens embutidas, legendas e fontes;
- trechos que devem ir para outra secao/grupo;
- casos ambiguos que devem ir para revisao assistida em vez de persistencia automatica.

## Escopo Dinamico De Secoes/Grupos

- Nao hardcode numeros, nomes ou titulos de secoes especificas na logica do parser.
- Use as secoes reais do relatorio como taxonomia dinamica de destino.
- Quando o usuario indicar uma secao/grupo alvo, trate essa indicacao como parametro de contexto, nao como regra fixa no codigo.
- Quando o documento trouxer numero ou titulo de secao, tente mapear para a secao correspondente do relatorio atual.
- Quando nao houver correspondencia confiavel, mantenha o item na revisao assistida para o usuario escolher a secao/grupo.
- Qualquer exemplo usado em teste deve demonstrar genericidade, nao dependencia de um unico numero de secao.

## Arquivos Prioritarios

Comece por estes arquivos:

- `app/routes/importacao.py`
- `app/templates/secao_edit.html`
- `app/models.py`
- `app/pdf_render.py`
- `app/templates/pdf/relatorio.html`
- `.github/copilot-instructions.md`

Leia outros arquivos se forem necessarios para entender permissoes, banco, modelos, rotas ou renderizacao.

## Diretrizes Tecnicas

- Preserve o fluxo atual de revisao assistida antes de criar blocos definitivos.
- Nao troque HTML/Jinja2 por React.
- Nao use mocks para substituir comportamento real.
- Nao adicione dependencia nova sem justificar claramente o ganho.
- Prefira melhorar funcoes pequenas e testaveis do parser em vez de criar um parser monolitico.
- Separe extracao bruta de interpretacao/classificacao quando isso reduzir complexidade.
- Mantenha compatibilidade com TXT e DOCX existentes.
- Se implementar suporte novo a PDF/OCR/planilha, faca isso incrementalmente e com validacao objetiva.
- Para baixa confianca, exponha o item para revisao humana com motivo/confianca, em vez de gravar automaticamente.

## Criterios De Qualidade

O importador melhorado deve:

- nao repetir titulo da secao como titulo de todos os blocos;
- usar linhas de secao como destino, nao como bloco repetido;
- preservar ordem original do documento;
- preservar imagem, legenda e fonte de figuras quando possivel;
- mapear conteudo para a secao correta quando houver numero/titulo reconhecivel;
- funcionar para qualquer secao/grupo indicado pelo usuario, sem regras fixas para uma unica secao;
- produzir blocos editaveis na revisao antes da confirmacao;
- evitar consultas desnecessarias ao banco durante confirmacao/importacao;
- nao quebrar a geracao de PDF.

## Validacao Obrigatoria

Antes de concluir:

1. Crie ou execute validacoes focadas do parser com amostras representativas de TXT e DOCX.
2. Inclua pelo menos uma amostra com secao numerada, subtitulo, paragrafo, figura com fonte e tabela quando possivel.
3. Inclua validacao que prove que o parser nao depende de uma secao fixa: use secoes/grupos diferentes ou uma secao alvo informada pelo contexto do teste.
4. Valide `import app.main`.
5. Releia integralmente todos os arquivos alterados apos a ultima edicao.
6. Procure inconsistencias em todo arquivo alterado, mesmo que nao tenham sido causadas diretamente pela mudanca.
7. Corrija inconsistencias relevantes nos arquivos alterados.
8. Zere a aba Problemas do workspace.
9. Informe na resposta final os arquivos alterados, as melhorias feitas, as validacoes executadas e qualquer risco residual.

## Resultado Esperado

Ao final, entregue uma melhoria real e testada no upload/importacao de conteudo existente, com comportamento mais robusto para extrair e reconhecer textos e aloca-los corretamente em secoes/grupos/blocos do SRA.

Use o pedido especifico do usuario como prioridade adicional quando ele fornecer exemplos de documentos, trechos problematicos ou resultado esperado.
