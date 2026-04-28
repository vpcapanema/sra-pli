# Instrucoes Do Projeto (SRA)

## Como Usar Este Documento E A Pasta `.cursor`

### Documento canonico

Este arquivo (`project-instructions.md`) e a **unica referencia completa** de dominio, stack, permissoes, fluxos, PDF, ciclo de notificacoes, linting e validacao obrigatoria. Atualize-o quando alguma mudanca alterar comportamento persistente ou contratos de dados.

### Estrutura de `.cursor/`

| Item                  | Funcao                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `rules/*.mdc`         | Regras sempre aplicadas ou condicionadas (linting, sanitizacao, browser, documentacao ao mudar comportamento).      |
| `skills/*/SKILL.md`   | Workflows especializados; comando `/nome-do-skill` no modo Agent.                                                   |
| `agents/*.md`         | Subagentes; `/nome` no Agent; doc em cursor.com/docs/subagents.md.                                                  |

Checklist obrigatorio ao encerrar qualquer tarefa: **`.cursor/rules/task-completion.mdc`** — alinhar **terminal** (`flake8`/`pylint`/`djlint` nos arquivos tocados), **diagnosticos expostos ao agente** e a **aba Problemas** do humano; releitura integral dos arquivos alterados. O agente nao ve a aba Problemas diretamente; sem essa paridade, humano e agente nao compartilham a mesma definicao de “zerado”. Para o mesmo habito em outros workspaces, replique o texto nas regras de usuario do Cursor.

Lista resumida de skills e convencoes para agentes: **`AGENTS.md`** na raiz do repositorio.

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

- `app/main.py`: cria a aplicacao FastAPI, registra middleware, arquivos estaticos e routers; `SraAutorRouteGuardMiddleware` + `SraEnsureProcessSessionMiddleware` + `SessionMiddleware` (ordem em `add_middleware`). O segundo chama `process_session_id` em pedidos HTTP autenticados exceto `/static/`; middleware `@app.middleware("http")` fica por fora da sessao.
- `app/access_control.py`: URLs permitidas a `autor` e `SraAutorRouteGuardMiddleware`.
- `app/db.py`: cria engine SQLAlchemy, normaliza `DATABASE_URL` para `postgresql+psycopg2` e configura pool/latencia para Postgres remoto.
- `app/models.py`: define `User`, `Relatorio`, `Secao`, `Bloco`, `Figura`, `EntregaRelatorio`, `NotificacaoEnvio` e `SECOES_PADRAO`.
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
- `app/routes/relatorios.py`: criacao, edicao, status, versao, duplicacao, reversao, exclusao e gestao de secoes; `GET /relatorios/{id}/blocos-confirmados.json` (blocos `bloqueados` em todo o relatorio, so admin/coord) e `POST /relatorios/{id}/blocos/excluir-todos-confirmados` (exclui todos esses blocos; `_exigir_relatorio_editavel` + `_pode_editar_status` importados de `blocos.py`).
- `app/routes/blocos.py`: criacao, edicao, confirmacao/bloqueio, exclusao, movimentacao e acoes em lote de blocos.
- `app/routes/figuras.py`: upload de figuras e entrega dos binarios armazenados no banco.
- `app/routes/importacao.py`: analise e confirmacao da importacao assistida de TXT/DOCX.
- `app/routes/pdf.py`: PDF final, preview HTML e exportacao por escopo.
- `app/routes/processos.py`: eventos de progresso para operacoes longas.
- `app/routes/notificacoes.py`: toggle do opt-out (`notificacoes_ativas`), painel de entregas por relatorio (`/relatorios/{id}/entregas`), acoes do coord (status / reenvio manual) e download autenticado dos modelos `.dotx`.
- `app/routes/cron_admin.py`: endpoints `POST /admin/cron/...` token-protegidos (`X-Cron-Token`); equivalentes HTTP dos jobs CLI.
- `app/notificacoes/`: orquestracao do ciclo mensal — `service.py` (`abrir_periodo` clona seções + blocos + figuras do relatório-base, ajusta texto do período/código no conteúdo, remapeia `[[REF:]]`; `notificar_autores_abertura` dispara Mensagem 1 após responsáveis atribuídos; `enviar_lembretes`, `retry_falhas`, `recompute_status_enviado`, `alterar_status_entrega`, `reenviar_manual`), `email_sender.py`, `modelos.py`, `templates/email_notificacao.{html,txt}`.
- `app/cron/`: pontos de entrada CLI dos jobs (`abrir_periodo`, `enviar_lembretes`, `retry_falhas`) — invocaveis via `python -m app.cron.NOME_DO_JOB` no Render Cron ou cron externo (`NOME_DO_JOB` = modulo em `app/cron/`).
- `app/sumario_extractor.py`: extracao de sumario a partir de PDFs entregues/disponiveis.
- `app/process_events.py`: registro e streaming de progresso de processos; `process_start` envia `data` com `tarefa` (nome do fluxo), `subtarefa` inicial, `progresso_geral` e `progresso_tarefa` (1..100, passo de 1 %); `process_log` aceita opcionalmente `tarefa`, `progresso_geral`, `progresso_tarefa` e usa `etapa` como rótulo de subtarefa em `data.subtarefa`; `process_done` acrescenta `progresso_*` em 100 e `tarefa` ao título; aceita `process_key`, `outcome`, `detalhe`, `recomendacao`; eventos trazem `data.channel=process` para o modal de acompanhamento.
- `app/sra_process_modal.py`: contrato de chaves e helpers (`montar_data_modal_fim`, `nivel_e_status_por_outcome`) alinhados aos slots dos parciais em `templates/complementos/`.
- `app/numeracao.py`: renumeracao hierarquica consolidada (`renumerar_relatorio`) e consolidacao de referencias textuais para marcadores estaveis (`consolidar_referencias`).
- `app/templates/`: telas Jinja da aplicacao; `app/templates/pdf/relatorio.html` e o template do PDF final; `app/templates/complementos/`: parciais HTML reutilizaveis (modais de confirmacao, acompanhamento de processo e status: sucesso, ressalvas, falha), incluidos em `base.html` quando o usuario esta autenticado.
- Layout autenticado: `base.html` define `<body class="sra-app …">` quando ha sessao (`padding-left: var(--sw)` em `app/static/css/app.css` reserva a largura da sidebar fixa). Classes por pagina usam o bloco Jinja `{% block body_class %}` (substitui o antigo `body_attrs`). O `#main` fica com `width:100%` dentro da area de conteudo do flex, sem `margin-left` sobreposto ao padding.
- `app/routes/dev_ui.py`: `GET /dev/modais` — pré-visualização local dos modais de complemento; `GET /dev/preview-emails-notificacao` — **uma página com as três mensagens** (abertura, lembrete, última chamada), cada qual renderizada com `preview_corpo_notificacao` / `email_notificacao.html` como no envio; `GET /dev/preview-email-notificacao` — uma mensagem só, barra com assunto + iframe `data:text/html;base64,...` (evita segundo GET sem cookie com `SameSite=lax`); `?raw=1` devolve só o HTML do e-mail; query opcional `tipo=...`, `relatorio_id=N` (dados reais). Requer login; ativo com `APP_ENV=development` ou `SRA_MODAL_PREVIEW=1`; se desligado, devolve página HTML com instruções; use `SRA_MODAL_PREVIEW=0` para forçar desligado. Com preview ativo, o menu lateral (`base.html`) ganha o grupo **Pré-visualização** com link direto para as três mensagens (`modais_preview_allowed()` + middleware em `app/main.py`).
- `app/static/`: CSS e assets estaticos.

### Modais de feedback de processo (complementos)

- Parciais em `app/templates/complementos/`: **confirmar** (cabeçalho, lead, detalhe opcional, pergunta; botões Cancelar e Continuar); **acompanhamento** (cabeçalho, sublinha opcional `process_key`, caixa única de estado com tarefa/etapa/mensagem, duas barras horizontais: progresso da tarefa atual e progresso geral do fluxo, em %); **sucesso** (cabeçalho, mensagem, detalhe opcional, botão Entendi); **ressalvas** (cabeçalho, mensagem, bloco ressalvas, Entendi); **falha** (cabeçalho, erro, detalhe opcional, O que fazer, Entendi).
- Evento SSE: `title` e `message` no topo; `data` com `channel=process`, `process_key`, `titulo`/`mensagem` (espelho semântico), `outcome`, `detalhe`, `recomendacao` quando houver. Processos de uma tarefa única devem manter o canal de notificação, não duplicar estes modais.
- Nos modais de fim de processo (sucesso, ressalvas, falha), o botão **Entendi** em `base.html` (`wireFimStatusModais`) fecha o wrap e em seguida recarrega a página atual (`location.reload()`). O clique no fundo apenas fecha o wrap, sem recarregar. Após `POST /relatorios` (criação), a resposta é **200** com o HTML do detalhe do relatório (sem HTTP redirect); antes disso grava-se `sra_fim_pendente` na sessão com `process_id` e o mesmo `data` do `process_done`. A renderização de `relatorio_detail` remove a chave e passa `sra_fim_pendente` ao template — `base.html` chama `SRAProcess.mostrarFimAposRedirect` para abrir o modal sem depender do replay SSE (necessário se o evento foi publicado noutro worker). O cliente regista `omitSseFim[process_id]` para ignorar o mesmo fim quando o EventSource repetir o evento.
- A barra de cabeçalho não exibe controle de processo: só os toasts (avisos) e os modais de complemento (confirmar, acompanhamento, status) recebem o feedback; o cliente ignora toasts para eventos `data.channel=process` (ficam no modal de acompanhamento).
- Preencher `process_key` com identificador estável por fluxo; textos de domínio por rota, não frases genéricas no backend.
- Confirmação reutilizável: rota `GET /processos/fluxo-confirmacao/{chave}` (sessão obrigatória) devolve JSON de textos (`title`, `lead`, `detail`, `ask`, `show_detail`) em `app/sra_fluxo_confirmacao.py`.
- Chaves de fluxo a documentar: `importacao_assistida_analise`, `importacao_assistida_confirmar`, `relatorio_criar`, `relatorio_excluir`, `exportar_relatorio`, `secao_excluir`, `bloco_confirmar`, `bloco_excluir`, `blocos_lote_excluir`, `blocos_lote_aprovar`.
- Cliente `sra_process_ui.js` (com `base.html` e sessão) expõe `window.SRAComplementos`. Formulários com atributo `data-sra-confirm` (chave) podem ainda levar título, lead, detalhe e ask com os `data-sra` correspondentes (nomes alinhados ao script).
- Importação assistida e ações em lote: modal com `confirmarComChave` em scripts sem submit clássico. Em `relatorio_criar` (`dashboard.html`), a segunda linha de mensagem no cliente lembra a fonte do sumário («Relatório entregue» / «Upload de PDF»); o trecho fica no bloco com id `#sra-cpl-confirm-lead-source`.
- No formulário, atributo `data-sra-iniciar-acompanhamento` (valor 1) seguido de clique em «Continuar» chama `window.SRAProcess.openTrackPendente` em `base.html`, abrindo o acompanhamento antes do SSE e cobrindo o vazio no fluxo (ex. `relatorio_criar`).

## Funcionalidades Atuais

- Autenticacao por sessao e roles `admin`, `coordenador` e `autor`. No `User`, o mesmo e-mail pode existir mais de uma vez desde que o **perfil** seja diferente: unicidade do par `(email, role)`; no login (`POST /login`) o formulário exige e-mail, senha e **perfil** para identificar a conta. Recuperação de senha: `GET/POST /recuperar-senha` (e-mail + perfil) e `GET/POST /recuperar-senha/definir` (nova senha); o passo válido fica na sessão (`sra_pwd_reset_*`) por até 1 h; rotas públicas no guard de autor.
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
- Ciclo mensal de notificacoes: dia 1 03:00 BRT abre o relatorio do mes (clona estrutura e conteudo do ultimo `finalizado`; responsaveis iniciam em `NULL` — coord/autor atribuem). Mensagem 1 (abertura) apos «Notificar autores» ou `notificar_autores_abertura`. Importacao assistida na secao **substitui** blocos existentes (inclui clone do mes anterior). Lembretes 5/8, ultima chamada 10. Status: `notificado` -> `aguardando_envio` -> `enviado` (blocos confirmados) -> `validado`. Painel `/relatorios/{id}/entregas`.
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

`Bloco.bloqueado` indica bloco confirmado. Blocos bloqueados nao devem ser editados, excluidos nem movidos (exceto `POST /relatorios/{id}/blocos/excluir-todos-confirmados` para admin/coord, que remove em lote todos os confirmados do relatorio). Um bloco passar para `bloqueado=true` dispara `recompute_status_enviado` no servico de notificacoes (via hook em `app/routes/blocos.py::_hook_recompute_entrega`): se todas as seções do responsavel naquele relatorio tem todos os blocos bloqueados, a `EntregaRelatorio` correspondente avanca para `enviado` com `data_envio` carimbada.

Notificacoes mensais (modelos novos):

- `User.notificacoes_ativas` (bool, default true): coluna **Relatorio** na UI; so utilizadores `role=autor` com valor true entram na lista de destinatarios do ciclo (abertura, lembrete, ultima chamada). Opt-out em `/usuarios`. Secoes atribuídas ao autor no relatorio alimentam o corpo do e-mail (lista de secoes sob responsabilidade) e podem estar vazias.
- `EntregaRelatorio` (1 por par `relatorio` × `user`): registro de entrega com `status` (`notificado`/`aguardando_envio`/`enviado`/`validado`), `data_envio`, `data_validacao`, `validado_por_id` e auditoria (`atualizado_por_id`/`atualizado_em`). Estado "finalizado" continua sendo do `Relatorio` inteiro, derivado pelo template — nao e estado por usuario.
- `NotificacaoEnvio` (1:N por `EntregaRelatorio`): histórico de envios com `tipo` (`abertura`/`lembrete`/`ultima_chamada`/`manual`), `enviada_em`, `sucesso`, `erro`, `destinatario_email` (snapshot, preserva auditoria mesmo se usuario trocar de email) e `sendgrid_message_id`.

## Regras De Permissao

Roles existentes:

- `admin`: acesso amplo.
- `coordenador`: acesso de gestao/revisao.
- `autor`: deve editar apenas secoes sem responsavel ou secoes em que seja o responsavel (regra por rota em blocos/relatorios); **ao nivel de URL**, autores ficam restritos ao fluxo de **upload de conteudo** — ver `app/access_control.py` (`SraAutorRouteGuardMiddleware`, lista `_AUTOR_PATH_RES`): `GET /painel-upload`, `GET /modelos-word-importacao` (+ `baixar`), `GET /relatorios/{id}/secoes/{sid}/upload-conteudo`, `POST` na mesma secao para `responsavel` (so pode atribuir a si) e `status`, APIs usadas por essa pagina (blocos.json, importar analisar/confirmar, figuras, PDF/exportar/preview, SSE `/processos/eventos`, fluxo-confirmacao), `GET /` e login/logout. **Admin e coordenador** nao passam por essa lista. A sessao guarda `user_role` no login (`app/routes/auth.py`) para o guard nao consultar o banco em todo pedido; ao editar o proprio perfil, `user_role` na sessao e atualizado se o papel mudar. No painel de upload (`conteudo_upload.html`), o autor ve listas de responsavel e status com confirmacao; responsaveis que nao sejam ele aparecem desabilitados; com secao `pendente`, o formulario sugere `em_andamento` ate confirmar. `POST` com `retorno=upload` volta para a pagina de upload (nao para o editor clássico). Em «Editar bloco existente», o seletor «Seção atual» do autor limita-se às secções em que pode atuar; a opção «Todas (blocos confirmados)» e o botão «Excluir todos os blocos» existem só para admin/coord (`blocos-confirmados.json` / `excluir-todos-confirmados`).

Sempre reutilize `current_user`, `require_user`, `require_admin` e os checks locais das rotas. Ao criar endpoint novo para secao/bloco, replique a regra de autor responsavel. **Novas rotas necessarias ao painel `upload-conteudo`** devem ser acrescentadas em `path_allowed_for_autor` (ou o middleware bloqueara autores).

Mutacoes estruturais (criar/excluir/mover subsecao em `app/routes/relatorios.py`; criar/excluir/mover bloco em `app/routes/blocos.py`) tambem precisam passar pelo guard de status: relatorio com `status == 'finalizado'` rejeita a operacao. Em `relatorios.py` use o helper `_exigir_relatorio_editavel(rel)`; em `blocos.py` chame `_check(..., exigir_editavel=True)`.

## Fluxos Principais

### Dashboard E Relatorios

O dashboard lista relatorios e sugere proximo D20 com base na ultima medicao. A tela de detalhe do relatorio mostra secoes, responsaveis, status e acesso para edicao.

### Edicao De Secao

Endpoints de UI: `/relatorios/{id}` (`relatorio_detail.html`, ``page-rel-com-preview``): mesmo layout em duas colunas que ``upload-conteudo`` — sumário/ações à esquerda (botão `+` por linha do sumário cria subseção inline como última filha direta via `POST /relatorios/{rel_id}/secoes/{sec_id}/subsecao`; o servidor decide o número (`_proximo_numero_filho`) e roda `consolidar_referencias`+`renumerar_relatorio`), pré-visualização PDF à direita (css em ``app/static/css/app.css`` junto com ``upload-conteudo``, classe combinada ``page-conteudo-upload page-rel-com-preview``); `GET /painel-upload` redireciona (`303`) para `/relatorios/{id}/secoes/{sec_id}/upload-conteudo` do relatório mais recente e primeira secao por ``ordem`` (sem página intermédia); `/relatorios/{id}/secoes/{sec_id}` (template `secao_edit.html` — editor principal da secao); `/relatorios/{id}/secoes/{sec_id}/upload-conteudo` (`conteudo_upload.html`) — painel combinado para envio e importacao com import revisado, blocos, editor na coluna esquerda e pre-visualizacao PDF a direita. Usa os mesmos POST que o editor principal (`_response_secao_page`).

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

**Ficheiros no repositorio**: a pasta `modelos_upload_doc_canonicos/` inclui `SRA_todas_secoes.dotx` (sumario com todas as secoes padrao) e um ficheiro `.dotx` por secao em `SECOES_PADRAO` (`app/models.py`), para o autor descarregar so o da sua responsabilidade. Cada `secao_*.dotx` inclui titulos Word (Heading 1 a 3 conforme numero) desde a ascendencia ate a peca atual: niveis superiores so como contexto; os exemplos texto/lista/figura/tabela ficam apenas na subsecao alvo deste `.dotx`. Regenerar com `scripts/build_canonical_upload_dotx.py` quando a lista de secoes padrao mudar.

**Catalogo na aplicacao (login)**: `GET /modelos-word-importacao` (`app/routes/modelos_word.py`, template `app/templates/modelos_word_importacao.html`) explica o uso dos modelos e lista links de download para `SRA_todas_secoes.dotx` e cada `secao_*.dotx` permitido (mesma convencao de nome que `app/notificacoes/modelos.py`). `GET /modelos-word-importacao/baixar/{arquivo}` serve o ficheiro apenas se o nome estiver na lista branca e existir em disco; caso contrario 404. Link na barra lateral em Upload conteudo > Modelos Word (.dotx); na pagina de upload de conteudo ha atalho no cabecalho.

### Ciclo De Notificacoes Mensais

Orquestrado por `app/notificacoes/service.py`. Quatro pontos de entrada ja idempotentes:

- `abrir_periodo(db, *, force=False, data_referencia=None)`: cria o relatorio do mes corrente clonando seções, blocos e figuras do ultimo `finalizado` (fallback: mais recente). Substitui no texto strings de periodo/codigo/titulo/medicao para o novo relatorio e remapeia `[[REF:]]`. Responsaveis **nao** sao copiados (`NULL`). Em seguida envia Mensagem 1 a **todos** os `User` com `role=autor` e coluna Relatorio (`notificacoes_ativas`) ativa; nao exige secção atribuída. `data_referencia` simula data (e2e).
- `notificar_autores_abertura(db, rel_id)`: Mensagem 1 para autores com Relatorio ativo que ainda nao receberam `abertura` com sucesso; idempotente.
- `enviar_lembretes(db, *, tipo, relatorio_id=None)`: envia Mensagem 2. `tipo` em `{lembrete, ultima_chamada}`. Filtro: status `notificado`/`aguardando_envio`, ultimo envio bem-sucedido > 22h. Apos 2 envios bem-sucedidos status vai para `aguardando_envio`. `relatorio_id` restringe a um relatorio (manutencao manual / e2e).
- `retry_falhas(db)`: reenvia falhas dos ultimos 7 dias, ate 3 tentativas por par `(entrega, tipo)`. Cria nova linha em `notificacao_envio` por tentativa para preservar audit trail.
- `recompute_status_enviado(db, user_id, rel_id)`: avalia se a entrega pode ser promovida a `enviado` (todas as secoes do user com pelo menos 1 bloco e todos `bloqueado=true`). Nao regride a partir de `enviado`/`validado`. Hook chamado por `app/routes/blocos.py` em `confirmar_bloco` e `aprovar_blocos_lote` via `_hook_recompute_entrega`.

Acoes manuais do coord (em `app/routes/notificacoes.py`):

- `POST /usuarios/{id}/notificacoes-toggle`: liga/desliga `notificacoes_ativas`.
- `POST /relatorios/{id}/entregas/{eid}/status` (form `novo_status`): altera status manualmente; `validado` carimba `validado_por_id`/`data_validacao`.
- `POST /relatorios/{id}/entregas/{eid}/reenviar`: dispara nova mensagem `manual`, ignora janela de 22h.

Email (`app/notificacoes/email_sender.py`):

- Modos: `real` (com `SENDGRID_API_KEY` + `NOTIFICAR_HABILITADO=true` + `NOTIFICAR_SANDBOX=false`), `sandbox` (renderiza/valida mas nao envia; usado em dev sem chave), `desligado` (kill switch `NOTIFICAR_HABILITADO=false`). `modo_atual()` expoe a decisao para UI/logs.
- Template unico `app/notificacoes/templates/email_notificacao.{html,txt}` que muda intro/CTA por `tipo`. HTML usa tabelas + estilos inline para sobreviver Outlook (sem elemento HTML details, sem flexbox).
- Links no email: `link_upload` (`/relatorios/{rel}/secoes/{sec}/upload-conteudo`), `link_dotx` (`/relatorios/{rel}/secoes/{sec}/modelo.dotx` — endpoint autenticado em `app/routes/notificacoes.py` que serve do `modelos_upload_doc_canonicos/`), `link_relatorio_painel` (`/relatorios/{rel}`), `link_modelos_word_ajuda` (`/modelos-word-importacao`), `link_login_sra` (`/login`), `link_painel_upload` (`/painel-upload`). Hosts derivados de `APP_BASE_URL`.
- Prazos no corpo do email (`prazos_mensagem_relatorio` em `app/notificacoes/service.py`): usa o **mes e ano** de `periodo_fim` do relatorio; `prazo_limite_conteudo_autor` = **dia 8** desse mes 23:59; `prazo_envio` (coordenacao) = **dia 10** desse mes 23:59. Aviso em destaque no HTML e no texto plano.
- Arvore no email: `arvore_secoes_links` (lista aninhada com `numero`, `titulo`, `link_upload`, `link_dotx`, `filhos`), montada por `arvore_secoes_com_links` em `app/notificacoes/email_context_arvore.py` (ordenacao por partes numericas de `numero` + `ordem`, nao so `ordem`, para o empilhamento pai/filho ser correto mesmo se o DB nao estiver em pre-ordem); texto plano dos modelos: `arvore_modelos_dotx_texto` via `format_arvore_secoes_email_plaintext(..., apenas_dotx=True)`. No HTML, lista de modelos usa o elemento `details` de forma recursiva (fechado por padrao; nivel 1 visivel como linha de sumario). Clientes de e-mail sem suporte ao elemento `details` podem exibir a arvore aberta. Preview sem BD e ficheiros em `tmp/email_preview_*.html`: arvore completa via `arvore_secoes_padrao_para_preview` (sumario `SECOES_PADRAO` em `app/models.py`, IDs sinteticos 10000+); regerar com `scripts/export_tmp_email_previews.py`.

Cron (Track 5):

- CLIs em `app/cron/`: `python -m app.cron.abrir_periodo [--force]`, `python -m app.cron.enviar_lembretes --tipo {lembrete|ultima_chamada} [--relatorio-id N]`, `python -m app.cron.retry_falhas`. Cada um abre `SessionLocal()` proprio e fecha.
- HTTP em `/admin/cron/{abrir-periodo,notificar-autores-abertura?relatorio_id=N,lembretes,retry}`: equivalente JSON, exige header `X-Cron-Token == settings.CRON_TOKEN`. Token vazio = 503 (fail-closed). Comparacao em tempo constante.
- Teste prático dos mesmos contratos: `scripts/teste_http_cron_notificacao.py` (`--http` contra `APP_BASE_URL` ou `--in-process` chamando o serviço direto; `--cadeia-atribuir` simula atribuir uma seção e disparar Mensagem 1). E2E completo de notificações: `scripts/_e2e_notificacoes.py`.
- Schedules sugeridas (UTC, comentadas em `render.yaml`): abrir `0 6 1 * *` (03:00 BRT dia 1), lembretes `0 12 5 * *` e `0 12 8 * *`, ultima chamada `0 12 10 * *`, retry `*/30 * * * *`. Cron services no Render sao pagos no plano free; alternativa: cron externo (cron-job.org) batendo nos endpoints HTTP com `X-Cron-Token`.

Variaveis de ambiente (`.env.example` / `render.yaml`): `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `SENDGRID_FROM_NAME`, `APP_BASE_URL`, `NOTIFICAR_HABILITADO`, `NOTIFICAR_SANDBOX`, `CRON_TOKEN`.

Fonte unica do nome de ficheiro `.dotx` em `app/notificacoes/modelos.py` (`slug_titulo`, `filename_para`, `caminho_para`); `scripts/build_canonical_upload_dotx.py` importa daqui para garantir que o ficheiro gerado e o link no email coincidem. Mudou regra de naming? Ajuste so este modulo.

E2E manual: `.\\.venv\\Scripts\\python.exe scripts/_e2e_notificacoes.py` cria usuarios de teste em domínio `@notif-test.local`, exercita os 4 pontos de entrada + acoes coord, e limpa o estado ao final. Idempotente.

Teste ponta a ponta com **conteudo real** (mesmo relatorio/secoes da base e mesmo pipeline que producao): `scripts/teste_real_ciclo_notificacao.py` — opcionalmente lista seções (`--listar-secoes`), pode abrir período (`--criar-periodo`) ou usar `--relatorio-id`, atribui responsáveis por codigos (`--secoes`), imprime preview via `preview_*` em `email_sender.py` e chama `notificar_autores_abertura`. Envio efetivo exige `--usuario-email`, opcional `--usuario-role` (padrao `autor`), `--confirmar` e obedece `NOTIFICAR_*` / SendGrid como na app.

### PDF Final

`app/pdf_render.py` transforma blocos em estrutura para `app/templates/pdf/relatorio.html`.

`app/routes/pdf.py`: `GET /relatorios/{id}/pdf` publica eventos de processo (geracao). `GET /relatorios/{id}/pdf?embed=1` devolve o mesmo PDF **sem** `process_start` / `process_done` — usar em iframes da pre-visualizacao lateral para nao repetir o fluxo de feedback ao carregar/recarregar a pagina. Links "Abrir PDF" / exportacao seguem sem `embed`.

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

Para tarefas de performance, use o skill **`/performance-agility`** (`.cursor/skills/performance-agility/SKILL.md`): mudancas cirurgicas, ganho verificavel, releitura completa dos arquivos alterados e testes antes de concluir.

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

Alem do papel canonico descrito no inicio deste arquivo, atualize-o na mesma mudanca sempre que uma alteracao significativa:

- criar, remover ou mudar fluxo funcional relevante;
- alterar modelo de dominio, permissao, status, persistencia ou contrato de dados;
- mudar arquitetura, rotas, templates principais, importacao, PDF, tarefas de desenvolvimento ou deploy;
- introduzir convencao nova que agentes futuros precisam conhecer.

Nao atualize este documento para ajustes puramente internos, correcoes pequenas de lint, textos triviais ou refatoracoes sem mudanca de comportamento. Quando atualizar, prefira editar secoes existentes em vez de duplicar informacao.

## Linting E Formatacao

O projeto tem linters integrados ao Cursor/VSCode via extensoes oficiais. Toda mudanca em codigo deve respeitar essas regras antes de concluir a tarefa. A configuracao canonica esta em `pyproject.toml` e `.vscode/settings.json`. Indentacao e charset entre editores alinham-se com `.editorconfig` na raiz (Python 4 espacos; HTML, CSS, JS, JSON, YAML 2 espacos; Markdown sem `trim_trailing_whitespace` para nao quebrar hard breaks). NAO altere essas configs sem motivo claro.

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
