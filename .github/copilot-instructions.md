# Instrucoes Do Projeto Para O Copilot

## O Que E Esta Aplicacao

Este repositorio contem o SRA, Sistema de Relatorios de Atividades para o contrato PLI/SP-2050. A aplicacao e uma plataforma web interna para producao semi-automatica dos Relatorios Mensais D20 do consorcio Concremat-Transplan, usados no contexto SEMIL/DER-SP.

O objetivo principal e permitir que autores preencham suas secoes de responsabilidade com blocos estruturados de conteudo, enquanto coordenadores e administradores controlam relatorios, secoes, responsaveis, revisao e geracao do PDF final no padrao visual do projeto.

O sistema deve funcionar em modo de producao real. Evite mocks, dados ficticios ou atalhos que substituam comportamento real da aplicacao.

## Stack E Arquitetura

- Backend: FastAPI.
- ORM: SQLAlchemy 2.
- Banco: PostgreSQL real, geralmente remoto no Render.
- Templates: Jinja2 com HTML tradicional.
- Frontend: HTML, CSS e JavaScript simples. Nao migrar para React.
- PDF: WeasyPrint renderizando HTML/CSS a partir de `app/templates/pdf/relatorio.html`.
- Autenticacao: sessao assinada via `SessionMiddleware` e senha com `bcrypt`.
- Uploads: figuras ficam armazenadas no banco em `Figura.dados` como binario.
- Deploy: Docker e Render.

Arquivos centrais:

- `app/main.py`: cria a aplicacao FastAPI, registra middleware, arquivos estaticos e routers.
- `app/db.py`: cria engine SQLAlchemy, normaliza `DATABASE_URL` para `postgresql+psycopg2` e configura pool/latencia para Postgres remoto.
- `app/models.py`: define `User`, `Relatorio`, `Secao`, `Bloco`, `Figura` e `SECOES_PADRAO`.
- `app/bootstrap.py`: inicializacao leve do banco, seed do admin e ajustes de esquema simples.
- `app/auth.py`: usuario atual, validacao de roles e regras de nome/senha.
- `app/routes/`: rotas de paginas, relatorios, blocos, figuras, importacao e PDF.
- `app/pdf_render.py`: monta contexto do relatorio e converte blocos para HTML/PDF.
- `app/list_lines.py`: deteccao e renderizacao de listas em texto bruto (paragrafos + listas; HTML para PDF e ramo de bloco `lista`).
- `app/templates/secao_edit.html`: tela principal de edicao de secoes, tabela de blocos, importacao assistida e editor manual.

## Mapa Atual Da Aplicacao

Use este mapa como orientacao inicial antes de procurar pontos de entrada:

- `app/routes/auth.py`: login, logout e gestao de usuarios.
- `app/routes/pages.py`: dashboard, detalhe do relatorio e tela de edicao de secao.
- `app/routes/relatorios.py`: criacao, edicao, status, versao, duplicacao, reversao, exclusao e gestao de secoes.
- `app/routes/blocos.py`: criacao, edicao, confirmacao/bloqueio, exclusao, movimentacao e acoes em lote de blocos.
- `app/routes/figuras.py`: upload de figuras e entrega dos binarios armazenados no banco.
- `app/routes/importacao.py`: analise e confirmacao da importacao assistida de TXT/DOCX.
- `app/routes/pdf.py`: PDF final, preview HTML e exportacao por escopo.
- `app/routes/processos.py`: eventos de progresso para operacoes longas.
- `app/sumario_extractor.py`: extracao de sumario a partir de PDFs entregues/disponiveis.
- `app/process_events.py`: registro e streaming de progresso de processos; `process_start` envia `data` com `tarefa` (nome do fluxo), `subtarefa` inicial, `progresso_geral` e `progresso_tarefa` (1..100, passo de 1 %); `process_log` aceita opcionalmente `tarefa`, `progresso_geral`, `progresso_tarefa` e usa `etapa` como rótulo de subtarefa em `data.subtarefa`; `process_done` acrescenta `progresso_*` em 100 e `tarefa` ao título; aceita `process_key`, `outcome`, `detalhe`, `recomendacao`; eventos trazem `data.channel=process` para o modal de acompanhamento.
- `app/sra_process_modal.py`: contrato de chaves e helpers (`montar_data_modal_fim`, `nivel_e_status_por_outcome`) alinhados aos slots dos parciais em `templates/complementos/`.
- `app/numeracao.py`: renumeracao hierarquica consolidada (`renumerar_relatorio`) e consolidacao de referencias textuais para marcadores estaveis (`consolidar_referencias`).
- `app/templates/`: telas Jinja da aplicacao; `app/templates/pdf/relatorio.html` e o template do PDF final; `app/templates/complementos/`: parciais HTML reutilizaveis (modais de confirmacao, acompanhamento de processo e status: sucesso, ressalvas, falha), incluidos em `base.html` quando o usuario esta autenticado.
- `app/routes/dev_ui.py` (rota `GET /dev/modais`): pré-visualização local dos modais de complemento; requer login; ativo com `APP_ENV=development` ou `SRA_MODAL_PREVIEW=1` no ambiente; use `SRA_MODAL_PREVIEW=0` se precisar desligar.
- `app/static/`: CSS e assets estaticos.

### Modais de feedback de processo (complementos)

- Parciais em `app/templates/complementos/`: **confirmar** (cabeçalho, lead, detalhe opcional, pergunta; botões Cancelar e Continuar); **acompanhamento** (cabeçalho, sublinha opcional `process_key`, caixa única de estado com tarefa/etapa/mensagem, duas barras horizontais: progresso da tarefa atual e progresso geral do fluxo, em %); **sucesso** (cabeçalho, mensagem, detalhe opcional, botão Entendi); **ressalvas** (cabeçalho, mensagem, bloco ressalvas, Entendi); **falha** (cabeçalho, erro, detalhe opcional, O que fazer, Entendi).
- Evento SSE: `title` e `message` no topo; `data` com `channel=process`, `process_key`, `titulo`/`mensagem` (espelho semântico), `outcome`, `detalhe`, `recomendacao` quando houver. Processos de uma tarefa única devem manter o canal de notificação, não duplicar estes modais.
- Os botões **Entendi** e o clique no fundo dos modais de fim de processo (sucesso, ressalvas, falha) fecham o respetivo wrap em `base.html` (`wireFimStatusModais`). Após `POST /relatorios` (criação), a resposta é **200** com o HTML do detalhe do relatório (sem HTTP redirect); antes disso grava-se `sra_fim_pendente` na sessão com `process_id` e o mesmo `data` do `process_done`. A renderização de `relatorio_detail` remove a chave e passa `sra_fim_pendente` ao template — `base.html` chama `SRAProcess.mostrarFimAposRedirect` para abrir o modal sem depender do replay SSE (necessário se o evento foi publicado noutro worker). O cliente regista `omitSseFim[process_id]` para ignorar o mesmo fim quando o EventSource repetir o evento.
- A barra de cabeçalho não exibe controle de processo: só os toasts (avisos) e os modais de complemento (confirmar, acompanhamento, status) recebem o feedback; o cliente ignora toasts para eventos `data.channel=process` (ficam no modal de acompanhamento).
- Preencher `process_key` com identificador estável por fluxo; textos de domínio por rota, não frases genéricas no backend.
- Confirmação reutilizável: rota `GET /processos/fluxo-confirmacao/{chave}` (sessão obrigatória) devolve JSON de textos (`title`, `lead`, `detail`, `ask`, `show_detail`) em `app/sra_fluxo_confirmacao.py`.
- Chaves de fluxo a documentar: `importacao_assistida_analise`, `importacao_assistida_confirmar`, `relatorio_criar`, `relatorio_excluir`, `exportar_relatorio`, `secao_excluir`, `bloco_confirmar`, `bloco_excluir`, `blocos_lote_excluir`, `blocos_lote_aprovar`.
- Cliente `sra_process_ui.js` (com `base.html` e sessão) expõe `window.SRAComplementos`. Formulários com atributo `data-sra-confirm` (chave) podem ainda levar título, lead, detalhe e ask com os `data-sra` correspondentes (nomes alinhados ao script).
- Importação assistida e ações em lote: modal com `confirmarComChave` em scripts sem submit clássico. Em `relatorio_criar` (`dashboard.html`), a segunda linha de mensagem no cliente lembra a fonte do sumário («Relatório entregue» / «Upload de PDF»); o trecho fica no bloco com id `#sra-cpl-confirm-lead-source`.
- No formulário, atributo `data-sra-iniciar-acompanhamento` (valor 1) seguido de clique em «Continuar» chama `window.SRAProcess.openTrackPendente` em `base.html`, abrindo o acompanhamento antes do SSE e cobrindo o vazio no fluxo (ex. `relatorio_criar`).

## Funcionalidades Atuais

- Autenticacao por sessao e roles `admin`, `coordenador` e `autor`.
- Cadastro e edicao de relatorios D20 com periodo, mes de referencia, numero de medicao, versao e status.
- Criacao de relatorios a partir de sumario extraido de PDF entregue/disponivel ou upload de PDF.
- Criacao automatica e gestao de secoes padrao, incluindo subsecoes, responsaveis e status por secao.
- Edicao de secoes por blocos estruturados (`texto`, `lista`, `figura`, `tabela`) com ordem, autor, bloqueio e acoes em lote.
- Insercao manual de figuras e tabelas por marcadores no conteudo, com contagem coerente por secao e global.
- Numeracao hierarquica consolidada: ao criar/excluir/mover subsecao ou bloco que afete numeracao, o sistema reescreve `Secao.numero`/`Secao.ordem` em DFS e troca referencias textuais "Figura X.Y" / "Tabela X.Y" / "Secao X.Y" por marcadores estaveis `[[REF:tipo|id]]`, resolvidos no render para o numero atual.
- Subsecoes podem ser movidas para cima/baixo na tela de detalhe do relatorio; relatorios `finalizado` bloqueiam mutacoes estruturais (criar/excluir/mover secao ou bloco).
- Upload e reutilizacao de figuras armazenadas no banco.
- Importacao assistida de TXT/DOCX com revisao humana antes da persistencia.
- Geracao, preview e exportacao de PDF no padrao visual do contrato.
- Eventos de progresso para processos longos, como criacao/importacao.
- Tasks de desenvolvimento no Cursor agrupadas por TaskBari em `.vscode/tasks.json`.
- **Database Client** (`cweijan.vscode-database-client2`): vista "Database" no painel do **Explorador** (manifesto local `contributes.views.explorer`; se a extensao atualizar, pode ser preciso repetir o patch). **SQLTools** + Driver PG na mesma lista; ligacoes SQLTools via `tools/sync_sqltools_connections.py` para `%APPDATA%\\Cursor\\User\\settings.json` (SQLTools fica com icone proprio na barra, nao duplicado no Explorador).

## Modelo De Dominio

Um `Relatorio` representa um D20 mensal, com codigo como `D20-15`, periodo, mes de referencia, numero de medicao, versao `R00/R01/...` e status.

Cada relatorio possui varias `Secao`, criadas a partir de `SECOES_PADRAO`. `Secao.numero` (string `String(16)`, com `UniqueConstraint(relatorio_id, numero)`) e `Secao.ordem` (inteiro DFS) definem a hierarquia. A numeracao e parte essencial do documento final, por exemplo `4`, `4.4`, `4.4.7`, `10.1`. Nao trate numero de secao como texto decorativo: ele direciona ordenacao, importacao, sumario, contadores de figura/tabela e referencias textuais.

Numeracao automatica: qualquer mutacao estrutural (criar/excluir/mover subsecao, criar/excluir/mover bloco que afete numeracao) deve passar por `consolidar_referencias` ANTES da mutacao e `renumerar_relatorio` DEPOIS, ambos em transacao explicita (`tx_session`). O top-level (`4`, `5`, ...) e preservado por contrato D20; apenas subniveis sao reescritos em sequencia 1..N por DFS.

Cada secao possui `Bloco` em ordem. Um bloco pode ser:

- `texto`: conteudo textual com suporte leve a `#`, `##`, listas e marcadores de figura/tabela.
- `lista`: linhas iniciadas por `-`.
- `figura`: referencia opcional a `Figura`, com legenda e fonte.
- `tabela`: conteudo tabular em texto, normalmente separado por `|`, com legenda e fonte.

`Figura` armazena nome, MIME, binario, legenda e fonte. Imagens podem ser enviadas manualmente ou extraidas de DOCX pela importacao assistida.

`Bloco.bloqueado` indica bloco confirmado. Blocos bloqueados nao devem ser editados, excluidos nem movidos.

## Regras De Permissao

Roles existentes:

- `admin`: acesso amplo.
- `coordenador`: acesso de gestao/revisao.
- `autor`: deve editar apenas secoes sem responsavel ou secoes em que seja o responsavel.

Sempre reutilize `current_user`, `require_user`, `require_admin` e os checks locais das rotas. Ao criar endpoint novo para secao/bloco, replique a regra de autor responsavel.

Mutacoes estruturais (criar/excluir/mover subsecao em `app/routes/relatorios.py`; criar/excluir/mover bloco em `app/routes/blocos.py`) tambem precisam passar pelo guard de status: relatorio com `status == 'finalizado'` rejeita a operacao. Em `relatorios.py` use o helper `_exigir_relatorio_editavel(rel)`; em `blocos.py` chame `_check(..., exigir_editavel=True)`.

## Fluxos Principais

### Dashboard E Relatorios

O dashboard lista relatorios e sugere proximo D20 com base na ultima medicao. A tela de detalhe do relatorio mostra secoes, responsaveis, status e acesso para edicao.

### Edicao De Secao

A tela de secao permite:

- visualizar blocos em tabela;
- criar bloco manual;
- editar bloco pelo container inferior;
- confirmar/bloquear bloco;
- excluir bloco;
- importar conteudo de TXT/DOCX;
- anexar ou usar figuras existentes;
- manter contagem de figuras/tabelas coerente com a secao e o PDF.

Nao quebre o fluxo de revisao: importacao deve sempre permitir revisao assistida antes de criar blocos definitivos.

### Importacao Assistida

`app/routes/importacao.py` analisa arquivos `.txt` e `.docx` e retorna blocos em JSON para revisao na tela antes da confirmacao.

Cuidados importantes:

- Linhas como `4.4.7Atividades...` ou `4.4.7 - Atividades...` representam destino de secao e nao devem virar bloco repetido.
- Titulos numerados como `4.4.7.1 Os tratamentos...` podem virar subtitulos dentro do conteudo.
- Legendas `Figura 4-1: ... Fonte: ...` devem separar legenda e fonte.
- DOCX pode conter imagem em um paragrafo e legenda no paragrafo seguinte; mantenha associacao entre imagem extraida e legenda/fonte.
- Imagem embutida de DOCX deve virar `Figura` real ao confirmar importacao.
- Nao repita o titulo da secao como `Bloco.titulo` em todos os blocos importados.
- Listas no conteudo sao formatacao **local** (independente da numeracao de secoes): `app/list_lines.py` define o texto bruto com recuo em multiplos de 2 espacos e marcadores (`-`, `1.`, `a)`, romano, etc.). A revisao de importacao em `secao_edit.html` inclui barra de ferramentas que so atua no textarea (com `import_texto_tools.js`). DOCX com `w:numPr` e mapeamento em `word/numbering.xml` e normalizado para esse texto bruto na analise.

### Modelo de documento canonico (Word/TXT) para preenchimento

Objetivo: **não** restringir o importador, mas oferecer ao usuario um ficheiro **alinhado** ao que a analise ja reconhece, para menos ajuste manual. As regras abaixo seguem o codigo em `importacao.py` e `list_lines.py` (nomes tecnicos para quem mexe em templates).

**Ficheiro `.txt` (opcional para o template)**

- Marcador de destino: linha exata do tipo ``[SECAO:4.4.1]`` (e variante de maiusculas, sem letras a mais) — ver `_parse_import_text`.
- Tabelas explicitas: ``[TABELA]`` / ``[TABELA:legenda]`` ... linhas ``| célula | célula |`` ... ``[/TABELA]``, ``Fonte:`` dentro do bloco.
- Linha vazia: faz *flush* de paragrafo; serve para nao juntar blocos de texto.
- Linhas a começar por ``#`` / ``##`` (e subtitulo numerado via `_normalize_heading_line`) sao trata como no agregado de blocos; subtitulo numerado no ficheiro requer o padrao de `_HEADING_RE` (numero com **dois (ou mais) segmentos** separados por ponto, ex.: `4.4.7.1`).

**Ficheiro `.docx` (foco do modelo Word recomendado)**

- **Ordem do corpo de Word**: a analise percorre paragrafos e tabelas na ordem; evitar caixas de texto/fluxo alternativo se quiser ordem 1:1.
- **Secao / titulos**: use estilos de titulo reais (``Heading 1..N`` / ``Título 1..N``). Paragrafos nesses estilos passam por `_section_from_heading` (numero+ titulo) ou viram blocos de texto com ``#``/``##``; linhas "normais" ainda podem bater com `_match_secao_linha` se forem, por ex., ``4.4.7  Titulo alinhado`` ao sumario.
- **Listas (formatacao local)**: o melhor alinhamento com o que o sistema gera a seguir e usar **listas reais** do Word (itens com numeracao/realce). Isso cria `w:numPr` e entra em `word/numbering.xml` — a analise mapeia ``bullet``/``decimal``/``lowerLetter``/``roman`` etc. para o texto de revisao. Estilos so de paragrafo com "Lista" (sem `numPr`) ainda sao aproximados com o padrao hífen + espaço a cabeça (``-`` e texto a seguir).
- **Tabelas**: tabelas nativas do Word viram grelha ``| a | b |``; linha *antes* no mesmo padrao `Tabela X.Y: ...` (ver `_TABELA_RE`) associa legenda; ``Fonte:`` a seguir ou na legenda, como ja documentado.
- **Figuras**: imagem **no proprio paragrafo** (incorporar imagem) — leitura em `_paragraph_images`. Legenda na linha de texto que bate com ``Figura``/``Fig.`` e numero + um de ``:``/``-``/``.``/``…``; ``Fonte:`` nessa linha ou no paragrafo seguinte. O prefixo "Figura 4.1" na legenda e depois alinhado na persistencia, mas o texto deve acompanhar a regex para ser detectado.
- **O que o modelo nao exige (mas pode incluir)**: tudo o que a analise nao mapeia continua a ir para texto; o modelo e uma **carta de bons costumes**, nao um validador de upload.

#### Checklist resumida para o autor do template

- Titulos: estilos de titulo Word; numeros de secao com pelo menos `N.M` quando se quer subtitulo numerado *dentro* do conteudo (ver `_HEADING_RE`).
- Listas: listas reais; recuo = nivel; tipos (bullet, numerico, romano) alinhados ao `word/numbering.xml` do proprio ficheiro.
- Figura: paragrafo com imagem + paragrafo de legenda com padrao `Fig(ura)...`.
- Tabela: objecto tabela; opcional legenda com `Tabela ...` na imediações (fluxo de `_parse_docx`).
- Evitar: numeracao manual so com espacos a fingir listas (quebra o `w:numPr`); legendas de figura/tabela sem a forma minima que as regex exigem.

**Ficheiros no repositorio**: a pasta `modelos_upload_doc_canonicos/` inclui `SRA_todas_secoes.dotx` (sumario com todas as secoes padrao) e um ficheiro `.dotx` por secao em `SECOES_PADRAO` (`app/models.py`), para o autor descarregar so o da sua responsabilidade. Regenerar com `scripts/build_canonical_upload_dotx.py` quando a lista de secoes padrao mudar.

### PDF Final

`app/pdf_render.py` transforma blocos em estrutura para `app/templates/pdf/relatorio.html`.

Cuidados importantes:

- O PDF deve preservar sumario, numeracao de secoes, legendas, fontes, figuras, tabelas, cabecalho/rodape e pagina de assinaturas.
- Marcadores em texto como `[[FIGURA:...]]` e `[[TABELA...]]` ainda precisam ser suportados por compatibilidade.
- Blocos `figura` sem imagem associada podem renderizar placeholder, mas o fluxo ideal de DOCX deve importar a imagem real.
- Contadores de figuras e tabelas seguem o primeiro nivel da secao, como `4.1`, `4.2`, etc.
- O campo `idx` em `[[FIGURA:idx|...]]` / `[[TABELA:idx|...]]` segue convencao bimodal: se contem ponto (ex.: `4.1`) e tratado como "por secao" e o numero exibido e derivado do contador atual; se e puramente numerico (ex.: `5`) e tratado como sequencial global e o valor armazenado e respeitado. `idx` vazio cai no contador local.
- Os tres marcadores REF comuns (exemplos no bloco abaixo) sao resolvidos em `_resolver_referencias` usando `_MapasRef` calculado por `_calcular_mapas_referencia`, sempre exibindo o numero atual. Se o alvo foi excluido, o marcador permanece intocado para sinalizar inconsistencia ao revisor (em vez de gerar "Figura None").

  ```text
  [[REF:figura|ID_BLOCO]]
  [[REF:tabela|ID_BLOCO]]
  [[REF:secao|ID_SECAO]]
  ```

### Numeracao Hierarquica E Referencias Estaveis

`app/numeracao.py` concentra a logica:

- `renumerar_relatorio(db, rel_id)`: recalcula `Secao.numero`/`Secao.ordem` por DFS sobre a arvore inferida pelo prefixo do numero e pela ordem dos irmaos. Aplica em duas fases (prefixo temporario `__t` e UPDATE com `CASE`) para nao colidir com `UniqueConstraint(relatorio_id, numero)`. Top-level e preservado.
- `consolidar_referencias(db, rel_id)`: varre `Bloco.conteudo` e `Bloco.legenda`, troca "Figura X.Y" / "Tabela X.Y" / "Secao X.Y" (e variantes com `-` e acentuacao) por `[[REF:tipo|id]]`. Idempotente: marcadores ja existentes nao sao reprocessados.
- `consolidar_e_renumerar(db, rel_id)`: atalho que faz consolidar + renumerar na ordem correta.

Ordem obrigatoria nas rotas que mutam estrutura: (1) `consolidar_referencias` ANTES da mutacao para fixar o alvo atual em ID estavel; (2) executar a mutacao (insert/delete/swap-ordem); (3) `renumerar_relatorio` DEPOIS para reescrever os numeros. Tudo dentro de `tx_session`.

Ja integrado em: `app/routes/relatorios.py` (criar/excluir/mover subsecao), `app/routes/blocos.py` (criar/excluir/mover bloco quando o bloco impacta numeracao via `_impacta_numeracao`) e `app/routes/importacao.py` (apos finalizar importacao, para converter referencias textuais herdadas em marcadores).

## Banco E Performance

O banco pode estar remoto no Render, com latencia alta. `app/db.py` usa pool de conexoes, keepalives e `isolation_level="AUTOCOMMIT"` para reduzir round-trips.

Ao mexer em banco:

- Evite consultas N+1; use `selectinload`, `load_only`, agregacoes ou consultas em lote quando fizer sentido.
- Para operacoes multi-statement que exigem atomicidade real, use transacao explicita (`tx_session` ou `with db.begin()` conforme o contexto).
- Nao reative `pool_pre_ping` nem remova ajustes de pool sem medir impacto.
- Evite contar/inserir item a item quando uma consulta em lote resolve.

Para tarefas de performance, use o agente `.github/agents/performance-agility.agent.md` como referencia de postura: mudancas cirurgicas, ganho verificavel, releitura completa dos arquivos alterados e testes antes de concluir.

## Convencoes De Frontend

- Preferir HTML/Jinja2/CSS/JavaScript simples.
- Nao introduzir React ou build frontend pesado.
- Manter a interface densa, utilitaria e focada em producao/revisao de relatorios, nao em landing page.
- Evitar mudancas visuais amplas sem pedido direto.
- Em tabelas e controles da area de secao, preservar legibilidade, alinhamento, bordas e acoes por icones quando esse padrao ja existir.
- Nao inserir texto explicativo excessivo dentro da interface; deixe fluxos claros pelo proprio controle.

## Ferramentas De Navegador Para Agentes

Use ferramentas de navegador quando a tarefa envolver interface, fluxo web, regressao visual, interacao com formularios, importacao pela UI, preview/exportacao de PDF ou validacao ponta a ponta.

Padrao preferencial:

1. MCP de navegador, quando estiver configurado no ambiente do agente.
2. Playwright, quando houver necessidade de teste reproduzivel, fluxo multi-etapa, screenshots ou automacao e2e.
3. Puppeteer, quando ja existir no projeto ou for a alternativa mais simples disponivel para automacao/screenshot.

Antes de usar, confirme que a ferramenta existe no ambiente. Nao adicione Playwright/Puppeteer como dependencia nova sem necessidade clara e sem justificar o ganho. Se nenhuma ferramenta de navegador estiver disponivel, diga isso explicitamente e valide por outro meio proporcional ao risco.

## Convencoes De Codigo

- Mudancas devem ser minimas, focadas e compativeis com o estilo existente.
- Nao reverta alteracoes do usuario.
- Nao adicione dependencia nova sem necessidade clara.
- Nao crie abstracoes grandes para resolver ajuste pequeno.
- Preserve nomes e conceitos do dominio em portugues: relatorio, secao, bloco, figura, legenda, fonte, medicao.
- Para novas rotas, siga o padrao de `APIRouter`, `Depends(get_db)`, `current_user` e respostas HTML com `TemplateResponse` (200; funções reutilizáveis em `app/routes/pages.py` como `response_dashboard`, `response_relatorio_detail`, `user_or_login_page`, `response_client_goto` para trocar a URL no cliente sem 3xx) ou `JSONResponse` para API. **Não** use `RedirectResponse` (3xx) para fluxos de formulário: após `POST` devolva a página de destino em 200. **Exceção de UX:** após `POST /login` e `GET /logout` usa-se `response_client_goto` (JS `location.replace`) para o browser mostrar `/dashboard` ou `/login` na barra; caso contrário o endereço ficaria desalinhado com o conteúdo. Recarregar a página (F5) após outro `POST` pode fazer o browser pedir reenvio do formulário.
- Para templates, mantenha Jinja2 simples e evite logica complexa demais quando puder preparar dados na rota.

## Documentacao Viva Para Agentes

Este arquivo e a fonte canonica de contexto para novos agentes de IA. Atualize-o na mesma mudanca sempre que uma alteracao significativa:

- criar, remover ou mudar fluxo funcional relevante;
- alterar modelo de dominio, permissao, status, persistencia ou contrato de dados;
- mudar arquitetura, rotas, templates principais, importacao, PDF, tarefas de desenvolvimento ou deploy;
- introduzir convencao nova que agentes futuros precisam conhecer.

Nao atualize este documento para ajustes puramente internos, correcoes pequenas de lint, textos triviais ou refatoracoes sem mudanca de comportamento. Quando atualizar, prefira editar secoes existentes em vez de duplicar informacao.

## Linting E Formatacao

O projeto tem linters integrados ao Cursor/VSCode via extensoes oficiais. Toda mudanca em codigo deve respeitar essas regras antes de concluir a tarefa. A configuracao canonica esta em `pyproject.toml` e `.vscode/settings.json`. NAO altere essas configs sem motivo claro.

### Ferramentas Ativas

- `flake8` + `Flake8-pyproject`: erros de sintaxe e estilo Python. Config em `[tool.flake8]`.
- `pylint`: analise estatica. Config em `[tool.pylint.*]`. Le `pyproject.toml` direto.
- `djlint`: linter de templates Jinja2/HTML, perfil `jinja`. Config em `[tool.djlint]`. Roda em `app/templates/**/*.html`.
- `Pylance`: `typeCheckingMode = "off"` (so erros de import/undefined). Diagnostic mode `openFilesOnly` (menos carga que análise do workspace inteiro).
- `cSpell` (Code Spell Checker): verificacao ortografica em pt-BR + ingles. Config em `cspell.json` raiz, dicionario customizado em `.cspell/projeto.txt`. Extensoes `streetsidesoftware.code-spell-checker` e `code-spell-checker-portuguese-brazilian` no Cursor; pacote `@cspell/dict-pt-br` em `node_modules/` para validacao via CLI.
- Interpretador: SEMPRE o do `.venv` do projeto (`./.venv/Scripts/python.exe` no Windows). Extensoes ja apontam para ele.

### Codigo Python — O Que Evitar Em Codigo Novo

- Multiplos statements na mesma linha com `;` (E702). Quebre em duas linhas.
- Funcoes novas com mais de 5 argumentos posicionais (R0917) sem justificativa real.
- Imports nao utilizados, variaveis nao utilizadas em codigo novo.
- Linhas extremamente longas (E501 e ignorado globalmente, mas use bom senso).
- Reativar `pool_pre_ping` em `app/db.py` ou remover ajustes de pool sem medir impacto.

### Templates Jinja — O Que Garantir

- Todo `{% block %}`, `{% if %}`, `{% for %}`, `{% with %}`, `{% macro %}` tem `{% end* %}` correspondente.
- Use `{{ var }}` com espaco interno entre as chaves e o nome (regra T001 do djlint). Sem espaco gera aviso.
- Tags com aspas duplas em strings (T002).
- Esta e aplicacao FastAPI: nao use convencoes Flask como `{{ url_for('static', ...) }}` ou `{{ url_for('view') }}`. As regras `J004` e `J018` do djlint estao desligadas justamente por isso, mas nao introduza esses padroes.
- Templates em `app/templates/**/*.html` sao registrados como `jinja-html` em `.vscode/settings.json`. Mantenha essa associacao.

### Codigo Legado E Warnings De Complexidade

Warnings pre-existentes de `pylint` como `too-many-locals`, `too-many-branches`, `too-many-arguments`, `too-many-positional-arguments`, `too-many-return-statements`, `too-many-statements` NAO devem ser desligados globalmente. A politica e refatorar gradualmente ao topar com a funcao. Nao adicione novas violacoes desse tipo em codigo seu.

### Ortografia (cSpell)

- Palavras NOVAS de dominio ou termos tecnicos que o pt-BR oficial nao cobre devem ser adicionadas em `.cspell/projeto.txt` (uma por linha, sem aspas, case-insensitive).
- NAO desabilite cSpell em arquivos inteiros. Se uma palavra aparece varias vezes, e termo de dominio: coloque no dicionario do projeto.
- Para um falso positivo isolado (sigla, hash, exemplo), use `// cspell:disable-line` ou `// cspell:disable-next-line`. Em HTML/Jinja, `{# cspell:disable-next-line #}`.

### Comandos De Validacao

```powershell
.\.venv\Scripts\python.exe -m flake8 app
.\.venv\Scripts\python.exe -m pylint --rcfile=pyproject.toml app
.\.venv\Scripts\python.exe -m djlint app/templates
npm run spell
```

A aba Problemas do Cursor reflete tudo isso automaticamente apos `Developer: Reload Window`.

## Validacao Obrigatoria

Antes de concluir qualquer tarefa de implementacao neste repositorio:

- Releia integralmente todos os arquivos alterados apos a ultima edicao.
- Procure inconsistencias em todo o arquivo relido, estejam elas diretamente ligadas ou nao a alteracao feita.
- Corrija inconsistencias encontradas na releitura sempre que estiverem no arquivo alterado e puderem afetar eficiencia, estabilidade, legibilidade ou comportamento.
- Rode os linters da secao "Linting E Formatacao" para os arquivos alterados e deixe a aba Problemas zerada para eles.
- Execute uma validacao objetiva do que foi afetado: import do app, snippet focado, teste de parser, chamada de endpoint, render de template/PDF ou comando equivalente.
- Informe na resposta final o que foi alterado e como foi validado.

Comandos uteis:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Validacao rapida de importacao da aplicacao:

```powershell
.\.venv\Scripts\python.exe -c "import app.main; print('ok')"
```
