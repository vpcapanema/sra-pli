# Instruções Do Projeto (SRA)

## Como Usar Este Documento

Fonte canônica de domínio, stack, permissões, fluxos, PDF e ciclo de notificações. Atualize na mesma entrega quando mudar comportamento persistente, modelo de dados, rotas, templates principais, importação, PDF, deploy ou tarefas do Cursor. Não atualize por correções triviais.

Estrutura de `.cursor/`: `rules/*.mdc` (regras editor), `skills/*/SKILL.md` (workflows `/nome-do-skill`), `agents/*.md` (subagentes `/nome`). Encerramento de tarefa: `.cursor/rules/task-completion.mdc`. Índice resumido para agentes: `AGENTS.md`.

## O Que É Esta Aplicação

SRA (Sistema de Relatórios de Atividades) do contrato PLI/SP-2050. Plataforma web interna para produção semi-automática dos Relatórios Mensais D20 do consórcio Concremat-Transplan, no contexto SEMIL/DER-SP. Autores preenchem suas seções com blocos estruturados; coordenadores e admins controlam relatórios, seções, responsáveis, revisão e geração do PDF final.

Modo de produção real: sem mocks, dados fictícios ou atalhos.

## Stack E Arquitetura

- Backend: FastAPI; ORM: SQLAlchemy 2; Banco: PostgreSQL real (geralmente remoto no Render).
- Templates: Jinja2 com HTML tradicional. Frontend: HTML/CSS/JS simples — **não migrar para React**.
- PDF: WeasyPrint a partir de `app/templates/pdf/relatorio.html`.
- Sessão assinada via `SessionMiddleware`; senha com `bcrypt`. Uploads de figura ficam no banco em `Figura.dados` (binário).
- Deploy: Docker e Render.

### Arquivos Centrais

- `app/main.py`: cria FastAPI, registra middleware, estáticos e routers. `SraAutorRouteGuardMiddleware` + `SessionMiddleware` (ordem em `add_middleware`); middlewares `@app.middleware("http")` ficam por fora da sessão. `sra_http_audit_log` registra `metodo/path/status/duracao(ms)` para `/relatorios`, `/usuarios`, URLs com sufixo `upload-conteudo` e rotas com `/importar/` (logger `app.http`).
- `app/access_control.py`: URLs permitidas a `autor` e `SraAutorRouteGuardMiddleware`.
- `app/db.py`: engine SQLAlchemy, normaliza `DATABASE_URL` para `postgresql+psycopg2`, configura pool/latência para Postgres remoto.
- `app/models.py`: `User`, `Relatorio`, `Secao`, `Bloco`, `Figura`, `EntregaRelatorio`, `NotificacaoEnvio`, `SECOES_PADRAO`.
- `app/bootstrap.py`: inicialização leve do banco, seed do admin, ajustes de esquema simples.
- `app/auth.py`: usuário atual, validação de roles, regras de nome/senha.
- `app/routes/`: rotas de páginas, relatórios, blocos, figuras, importação e PDF.
- `app/pdf_render.py`: monta contexto e converte blocos para HTML/PDF.
- `app/list_lines.py`: detecção/renderização de listas em texto bruto (parágrafos + listas; HTML para PDF e ramo de bloco `lista`).
- `app/templates/complementos/*.html`: páginas Jinja servidas pelas rotas. `base.html` permanece em `app/templates/`. PDF (`pdf/`) e e-mail (`notificacoes/templates/`) mantêm caminhos próprios.
- `app/templates/complementos/secao_edit_conteudo_upload.html`: única UI de edição/gestão por seção — coordenação (responsável/status), importação assistida com revisão, tabela de blocos com aprovação em lote, editor e pré-visualização PDF. Ao escolher uma seção como alvo, **blocos, contagens de figura/tabela, iframe de PDF e caixas da exportação** incluem **toda a subárvore PLI** (âncora + descendentes `N.*`, ver `secao_ids_na_subarvore` em `app/numeracao.py`).
- `app/routes/mapa_aplicacao.py` + `app/templates/mapa_aplicacao.html`: `GET /mapa-aplicacao` (sessão obrigatória) lista cartões de ficheiros em `complementos/` com rota de exemplo, restrição e "em uso". Metadados em `app/mapa_aplicacao_catalog.py`; `mapa_da_aplicacao.html` na raiz é cópia estática para consulta offline.

### Mapa De Rotas

- `app/routes/auth.py`: login, logout, gestão de usuários.
- `app/routes/pages.py`: dashboard, detalhe do relatório, páginas de seção (`upload-conteudo`; `GET /relatorios/{id}/secoes/{sid}` redireciona `303` para `upload-conteudo`).
- `app/routes/relatorios.py`: criação, edição, status, versão, duplicação, reversão e gestão de seções; `GET /relatorios/{id}/secoes/{sid}/status` redireciona `303` para `upload-conteudo`. `GET /relatorios/{id}/blocos-confirmados.json` (admin/coord) e `POST /relatorios/{id}/blocos/excluir-todos-confirmados` (helpers `_exigir_relatorio_editavel` + `_pode_editar_status` importados de `blocos.py`).
- `app/routes/relatorio_exclusao.py`: `POST /relatorios/{id}/excluir` e `POST /relatorios/{id}/secoes/{sid}/excluir` (mesmo prefixo no `main`); resposta HTML após transação.
- `app/routes/blocos.py`: criação, edição, confirmação/bloqueio, exclusão, movimentação e ações em lote; leitura JSON e mutações aceitam blocos de qualquer seção na **subárvore** da seção da URL (âncora).
- `app/routes/figuras.py`: upload de figuras e entrega dos binários.
- `app/routes/importacao.py`: análise e confirmação da importação assistida de TXT/DOCX (limite por pedido na análise: `IMPORTACAO_ANALISAR_MAX_BYTES` em `app/config.py`, padrão 20 MiB).
- `app/routes/pdf.py`: PDF final, preview HTML e exportação por escopo.
- `app/routes/notificacoes.py`: toggle do opt-out (`notificacoes_ativas`), painel de entregas (`/relatorios/{id}/entregas`), ações do coord (status / reenvio manual) e download autenticado dos modelos `.dotx`.
- `app/routes/cron_admin.py`: endpoints `POST /admin/cron/...` token-protegidos (`X-Cron-Token`); equivalentes HTTP dos jobs CLI.
- `app/notificacoes/`: orquestração do ciclo mensal — `service.py` (`abrir_periodo`, `notificar_autores_abertura`, `enviar_lembretes`, `retry_falhas`, `recompute_status_enviado`, `alterar_status_entrega`, `reenviar_manual`), `email_sender.py`, `modelos.py`, `templates/email_notificacao.{html,txt}`.
- `app/cron/`: pontos de entrada CLI dos jobs (`abrir_periodo`, `enviar_lembretes`, `retry_falhas`) — `python -m app.cron.NOME_DO_JOB` no Render Cron ou cron externo.
- `app/sumario_extractor.py`: extração de sumário a partir de PDFs entregues/disponíveis.
- `app/numeracao.py`: renumeração hierárquica (`renumerar_relatorio`), consolidação de referências para marcadores estáveis (`consolidar_referencias`) e `secao_ids_na_subarvore` (âncora + descendentes pelo número).
- `app/templates/`: telas Jinja; `app/templates/pdf/relatorio.html` é o template do PDF final.
- `app/static/`: CSS e assets.

Layout autenticado: em `base.html`, o documento autenticado aplica a classe `sra-app` no elemento raiz (`padding-left: var(--sw)` em `app/static/css/app.css` reserva a largura da sidebar fixa). Classes por página usam o bloco Jinja `body_class` (substitui o antigo `body_attrs`). A sidebar lista apenas páginas completas, agrupadas por semelhança em menus suspensos; não adicione links para âncoras internas (`#...`) nem árvore de seções no menu lateral.

`app/routes/dev_ui.py`: `GET /dev/modais` (preview local de `window.confirm` via `SRAComplementos`); `GET /dev/preview-emails-notificacao` (página com as 3 mensagens — abertura/lembrete/última chamada); `GET /dev/preview-email-notificacao` (uma mensagem só, iframe `data:text/html;base64,...`); `?raw=1` devolve só o HTML; query opcional `tipo=...`, `relatorio_id=N`. Requer login; ativo com `APP_ENV=development` ou `SRA_MODAL_PREVIEW=1`; `SRA_MODAL_PREVIEW=0` força desligado.

### Confirmação No Browser

- `sra_process_ui.js`: formulários com `data-sra-confirm` (+ `data-sra-title/lead/detail/ask`) disparam `window.confirm` no `submit` via `SRAComplementos`. Em `relatorio_criar`, a fonte do sumário entra no texto da confirmação.
- Operações longas não publicam eventos no servidor.
- `data-sra-iniciar-acompanhamento="1"`: após `window.confirm`, registra em `SRA_LOG`, mostra faixa inferior fixa e desativa botões até receber resposta. `data-sra-busy-msg` para o texto.
- Chaves de fluxo: `importacao_assistida_analise/confirmar`, `relatorio_criar/excluir`, `exportar_relatorio`, `secao_excluir`, `bloco_confirmar/excluir`, `blocos_lote_excluir/aprovar`.
- `window.SRAComplementos`: `init`, `carregarChave`, `confirmarComChave`, `abrirDireto`, `fecharConfirm`.
- Scripts em `base.html`: `sra_log.js` (`SRA_LOG` no console; verbose com `APP_ENV=development` ou hostname loopback), `sra_auth_fetch.js` (em verbose loga cada `fetch`), `sra_process_ui.js`.

## Funcionalidades Atuais

- Sessão e roles `admin`, `coordenador`, `autor`. No `User`, mesmo e-mail pode existir mais de uma vez se o **perfil** for diferente: unicidade `(email, role)`. Login (`POST /login`) exige e-mail + senha + perfil. Recuperação de senha: `GET/POST /recuperar-senha` e `GET/POST /recuperar-senha/definir`; passo válido fica em sessão (`sra_pwd_reset_*`) por até 1h; rotas públicas no guard de autor.
- Cadastro/edição de relatórios D20 com período, mês de referência, número de medição, versão e status.
- Criação a partir de sumário de PDF (entregue/disponível ou upload).
- Criação automática e gestão de seções padrão (subseções, responsáveis e status por seção).
- Edição por blocos estruturados (`texto`, `lista`, `figura`, `tabela`) com ordem, autor, bloqueio e ações em lote.
- Inserção manual de figuras/tabelas por marcadores no conteúdo, com contagem coerente por seção e global.
- Numeração hierárquica consolidada: ao mutar estrutura, o sistema reescreve `Secao.numero/ordem` em DFS e troca "Figura X.Y" / "Tabela X.Y" / "Secao X.Y" por marcadores `[[REF:tipo|id]]`, resolvidos no render.
- Subseções podem ser movidas cima/baixo na tela de detalhe; relatórios `finalizado` bloqueiam mutações estruturais.
- Upload e reuso de figuras armazenadas no banco.
- Importação assistida de TXT/DOCX com revisão humana antes da persistência.
- Geração, preview e exportação de PDF no padrão visual do contrato.
- Ciclo mensal de notificações (detalhes em **Ciclo De Notificações** abaixo).
- Tarefas de dev no Cursor: `.vscode/tasks.json` → **SRA: backend (8001) + abrir / e /mapa-aplicacao** chama `scripts/sra_backend_dev.ps1`. Job em background `sra-open`.

## Modelo De Domínio

`Relatorio`: D20 mensal, código tipo `D20-15`, período, mês de referência, medição, versão `R00/R01/...`, status.

`Secao`: `numero` (`String(16)`, `UniqueConstraint(relatorio_id, numero)`) e `ordem` (DFS) definem hierarquia. Numeração é semântica (não decoração): direciona ordenação, importação, sumário, contadores e referências. Mutação estrutural exige `consolidar_referencias` ANTES e `renumerar_relatorio` DEPOIS, em transação explícita (`tx_session`). Top-level (`4`, `5`, ...) é preservado; só subníveis reescritos em sequência 1..N por DFS.

`Bloco` (em ordem dentro da seção):

- `texto`: suporte leve a `#`, `##`, listas e marcadores de figura/tabela.
- `lista`: linhas iniciadas por `-`.
- `figura`: referência opcional a `Figura`, com legenda e fonte.
- `tabela`: tabular em texto, separado por `|`, com legenda e fonte.
- `origem`: `manual` por padrão; importação assistida grava `upload`, usado pelo escopo de exportação "Somente seções importadas".

`Figura`: nome, MIME, binário, legenda, fonte. Pode vir de upload manual ou DOCX.

`Bloco.bloqueado`: bloco confirmado. Não editar/excluir/mover (exceto `POST /relatorios/{id}/blocos/excluir-todos-confirmados` para admin/coord). Bloquear bloco dispara `recompute_status_enviado` (hook `_hook_recompute_entrega` em `app/routes/blocos.py`): se todas as seções do responsável têm todos os blocos bloqueados, `EntregaRelatorio` avança para `enviado` com `data_envio`.

Notificações:

- `User.email` + `User.email2` (ambos obrigatórios): principal (login, unicidade `(email, role)` em `uq_users_email_role`) e **secundário**. Ciclo envia para ambos quando distintos; `EntregaRelatorio.status` evolui só com sucesso para o **principal**.
- `User.notificacoes_ativas` (bool, default true): só `role=autor` com true entram no ciclo. Opt-out em `/usuarios`.
- `EntregaRelatorio` (1 por par `relatorio` × `user`): `status` (`notificado`/`aguardando_envio`/`enviado`/`validado`), `data_envio`, `data_validacao`, `validado_por_id`, auditoria. Estado "finalizado" é do `Relatorio` inteiro.
- `NotificacaoEnvio` (1:N por `EntregaRelatorio`): `tipo` (`abertura`/`lembrete`/`ultima_chamada`/`manual`), `enviada_em`, `sucesso`, `erro`, `destinatario_email` (snapshot), `sendgrid_message_id`.

## Regras De Permissão

- `admin`: acesso amplo.
- `coordenador`: gestão/revisão.
- `autor`: edita só seções sem responsável ou em que seja responsável (regra por rota); **ao nível de URL**, restrito a fluxo de gestão de seção e upload — ver `app/access_control.py` (`SraAutorRouteGuardMiddleware`, `_AUTOR_PATH_RES`): `GET /`, `GET /painel-upload` (redireciona ao sumário do mais recente), `GET /relatorios/{id}` (sumário), `GET /modelos-word-importacao` (+ `baixar`), `GET /relatorios/{id}/secoes/{sid}/upload-conteudo`, `POST` `responsavel` (só si próprio) e `status`, APIs usadas pela página (blocos.json, importar, figuras, PDF) e login/logout. Após login bem-sucedido, destino do autor é `/relatorios/{id}` (`url_hub_autor` em `app/routes/pages.py`).

Sessão guarda `user_role` no login (`app/routes/auth.py`) para o guard não consultar banco em todo pedido; ao editar próprio perfil, `user_role` na sessão é atualizado se mudar.

Em `secao_edit_conteudo_upload.html`: cartão «Coordenação da seção» reúne seção alvo, responsável e status; mudar **Seção alvo** navega para o `upload-conteudo` dessa seção; **Confirmar** envia em sequência `POST .../responsavel` e `POST .../status` com `retorno=upload`. Indicadores verde/vermelho marcam alinhamento. Responsáveis que não sejam ele aparecem desabilitados; com seção `pendente`, sugere `em_andamento`. Em «Editar bloco existente», o seletor «Seção atual» do autor limita-se às seções em que pode atuar; «Todas (blocos confirmados)» e «Excluir todos os blocos» só para admin/coord.

Sempre reutilize `current_user`, `require_user`, `require_admin` e os checks locais. Novas rotas do fluxo de gestão de seção/upload precisam entrar em `path_allowed_for_autor` (ou middleware bloqueia autores).

Mutações estruturais em `relatorios.py`/`blocos.py` passam por guard de status: relatório `finalizado` rejeita. Use `_exigir_relatorio_editavel(rel)` em `relatorios.py` e `_check(..., exigir_editavel=True)` em `blocos.py`.

## Fluxos Principais

### Dashboard E Relatórios

Dashboard lista relatórios e sugere próximo D20 com base na última medição. Tela de detalhe mostra seções, responsáveis, status e acesso para edição.

### Edição De Seção

- `/relatorios/{id}` (`relatorio_detail.html`, `page-rel-com-preview`): layout 2 colunas igual ao `upload-conteudo` — sumário/ações à esquerda (botão `+` por linha cria subseção inline como última filha via `POST /relatorios/{rel_id}/secoes/{sec_id}/subsecao`; servidor decide o número via `_proximo_numero_filho` e roda `consolidar_referencias`+`renumerar_relatorio`); preview PDF à direita. Classe combinada: `page-conteudo-upload page-rel-com-preview`.
- `GET /painel-upload`: redireciona `303` ao sumário `/relatorios/{id}` do mais recente.
- `GET /relatorios/{id}/secoes/{sec_id}` redireciona `303` para `…/upload-conteudo`.
- `GET /relatorios/{id}/secoes/{sec_id}/upload-conteudo`: serve `secao_edit_conteudo_upload.html` — gestão da seção (coordenação, importação assistida, tabela de blocos, editor) + preview PDF. Usa `_response_secao_page` e os mesmos `POST` de mutação.

A tela permite: visualizar blocos em tabela; criar bloco manual; editar pelo container inferior; confirmar/bloquear; excluir; importar TXT/DOCX; anexar/usar figuras; manter contagem coerente.

Importação **sempre** permite revisão assistida antes de criar blocos definitivos.

### Importação Assistida

`app/routes/importacao.py` analisa `.txt`/`.docx` e retorna blocos JSON para revisão.

Cuidados:

- `4.4.7Atividades...` ou `4.4.7 - Atividades...` representam destino de seção, não bloco repetido.
- Títulos `4.4.7.1 ...` podem virar subtítulos no conteúdo.
- Legendas `Figura 4-1: ... Fonte: ...` separam legenda e fonte.
- DOCX pode ter imagem em um parágrafo e legenda no seguinte: manter associação.
- Imagem embutida vira `Figura` real ao confirmar.
- Não repita o título da seção como `Bloco.titulo` em todos os blocos.
- Listas no conteúdo são **formatação local** (independente da numeração de seções): `app/list_lines.py` define o texto bruto com recuo em múltiplos de 2 espaços e marcadores (`-`, `1.`, `a)`, romano). DOCX com `w:numPr` + `word/numbering.xml` é normalizado para esse texto bruto. Barra de ferramentas em `secao_edit_conteudo_upload.html` atua só no textarea (com `import_texto_tools.js`).

### Modelo Canônico Word/TXT Para Preenchimento

Não restringe o importador, oferece ficheiro alinhado ao que a análise reconhece (regras seguem `importacao.py` e `list_lines.py`).

**`.txt`**: marcador exato `[SECAO:4.4.1]`; tabelas `[TABELA]` ... `[/TABELA]` com `Fonte:` dentro; linha vazia faz flush; `#`/`##` e subtítulo numerado via `_normalize_heading_line` (`_HEADING_RE` exige número com **2+ segmentos**).

**`.docx`** (foco do modelo recomendado):

- Ordem do corpo Word; evite caixas de texto.
- Seção/títulos: estilos reais (`Heading 1..N` / `Título 1..N`); passam por `_section_from_heading` ou viram blocos com `#`/`##`. Linhas "normais" também batem em `_match_secao_linha` se forem como `4.4.7  Título`.
- Listas: use **listas reais** Word — `w:numPr` + `word/numbering.xml` mapeia `bullet`/`decimal`/`lowerLetter`/`roman` etc. Estilos só de parágrafo "Lista" (sem `numPr`) são aproximados com hífen + espaço.
- Tabelas: nativas viram `| a | b |`; legenda na linha anterior com padrão `Tabela X.Y: ...` (`_TABELA_RE`); `Fonte:` na legenda ou parágrafo seguinte.
- Figuras: imagem **no próprio parágrafo** (incorporar imagem) — `_paragraph_images`. Legenda na linha que bate com `Figura`/`Fig.` + número + `:`/`-`/`.`/`…`; `Fonte:` na linha ou no parágrafo seguinte.

**Catálogo na aplicação**: `GET /modelos-word-importacao` (`app/routes/modelos_word.py`, template `complementos/modelos_word_importacao.html`) lista `SRA_todas_secoes.dotx` e `secao_*.dotx` permitidos. `GET /modelos-word-importacao/baixar/{arquivo}` serve apenas se o nome estiver na lista branca. Pasta `modelos_upload_doc_canonicos/` contém os ficheiros; regenerar com `scripts/build_canonical_upload_dotx.py` quando `SECOES_PADRAO` mudar.

### Ciclo De Notificações Mensais

Persistência editável (coord/admin): tabela singleton `parametros_ciclo_notificacao` (`app/models.ParametrosCicloNotificacao`); carga/definição em `app/notificacoes/ciclo_params.py`. UI `GET /governanca-relatorio` (`app/routes/governanca_relatorio.py`, template `complementos/governanca_relatorio.html`): edição das tabelas `parametros_ciclo_notificacao`, `entrega_relatorio`, `notificacao_envio` e `users` (coordenador só vê autores e próprio perfil), status real opcional dos jobs do cron-job.org e filtro server-side por relatório em entregas/notificações (padrão: relatório mais recente). Chave SendGrid, kill-switch e chave opcional `CRONJOB_ORG_API_KEY` ficam em ambiente. Sidebar: «Governança» > «Governança do relatório».

Pontos de entrada (idempotentes) em `app/notificacoes/service.py`:

- `abrir_periodo(db, *, force=False, data_referencia=None)`: cria relatório do mês corrente (período via `periodo_referente_para_data` + parâmetros persistidos) clonando seções/blocos/figuras do último `finalizado`, ajusta texto do período/código, remapeia `[[REF:]]`. Sem `force` e sem relatório existente: só avança se dia BRT == `dia_abertura_novo_ciclo`; senão devolve aviso. `force=true` ignora calendário.
- `notificar_autores_abertura(db, rel_id)`: Mensagem 1 para autores ativos que ainda não receberam `abertura` com sucesso. Idempotente.
- `enviar_lembretes(db, *, tipo, relatorio_id=None, ignorar_calendario=False)`: Mensagem 2. `tipo ∈ {lembrete, ultima_chamada}`; padrão respeita calendário (lembrete em dias configurados; última chamada no dia configurado). `ignorar_calendario=true` (CLI `--ignorar-calendario`, query HTTP, chamadas Python E2E) contorna. Filtro: status `notificado`/`aguardando_envio`, último envio bem-sucedido > 22h. Após 2 envios bem-sucedidos status vai para `aguardando_envio`. `relatorio_id` restringe.
- `retry_falhas(db)`: reenvia falhas dos últimos 7 dias, até 3 tentativas por par `(entrega, tipo)`. Cria nova linha em `notificacao_envio` por tentativa (audit trail).
- `recompute_status_enviado(db, user_id, rel_id)`: avalia se entrega vai a `enviado` (todas as seções do user com pelo menos 1 bloco, todos `bloqueado=true`). Não regride a partir de `enviado`/`validado`. Hook chamado por `confirmar_bloco`/`aprovar_blocos_lote` em `blocos.py` via `_hook_recompute_entrega`.

Ações manuais do coord (`app/routes/notificacoes.py`):

- `POST /usuarios/{id}/notificacoes-toggle`: liga/desliga `notificacoes_ativas`.
- `POST /relatorios/{id}/entregas/{eid}/status` (`novo_status`): altera status; `validado` carimba `validado_por_id`/`data_validacao`.
- `POST /relatorios/{id}/entregas/{eid}/reenviar`: nova mensagem `manual`, ignora janela 22h.

E-mail (`app/notificacoes/email_sender.py`):

- Modos: `real` (`SENDGRID_API_KEY` + `NOTIFICAR_HABILITADO=true` + `NOTIFICAR_SANDBOX=false`), `sandbox` (renderiza/valida sem enviar), `desligado` (`NOTIFICAR_HABILITADO=false`). `modo_atual()` expõe a decisão.

- Template único `app/notificacoes/templates/email_notificacao.{html,txt}` que muda intro/CTA por `tipo`. HTML usa tabelas + estilos inline (sem `&lt;details&gt;`, sem flexbox) para Outlook).

- Links: `link_upload`, `link_dotx` (`/relatorios/{rel}/secoes/{sec}/modelo.dotx` autenticado em `notificacoes.py`), `link_relatorio_painel`, `link_modelos_word_ajuda`, `link_login_sra`, `link_painel_upload`. Hosts derivados de `APP_BASE_URL`.

- Prazos no corpo (`prazos_mensagem_relatorio` em `service.py`): mês/ano de `periodo_fim`; dias de autor e coordenação configuráveis (`prazo_autor_dia`, `prazo_coordenacao_dia`); horas exibidas 23:59.

- Árvore: `arvore_secoes_links` (lista aninhada) montada por `arvore_secoes_com_links` em `app/notificacoes/email_context_arvore.py` (ordenação por partes numéricas de `numero` + `ordem`); texto plano via `format_arvore_secoes_email_plaintext(..., apenas_dotx=True)`. No HTML, lista de modelos usa `&lt;details&gt;` recursivo (fechado por padrão; nível 1 visível). Preview sem BD em `tmp/email_preview_*.html` via `arvore_secoes_padrao_para_preview` (IDs sintéticos 10000+); regerar com `scripts/export_tmp_email_previews.py`.

Cron (Track 5):

- CLI em `app/cron/`: `python -m app.cron.abrir_periodo [--force]`, `python -m app.cron.enviar_lembretes --tipo {lembrete|ultima_chamada} [--relatorio-id N]`, `python -m app.cron.retry_falhas`. Cada um abre `SessionLocal()` próprio.
- HTTP em `/admin/cron/{abrir-periodo,abrir-periodo-background,notificar-autores-abertura?relatorio_id=N,lembretes,retry}`: equivalente JSON, exige `X-Cron-Token == settings.CRON_TOKEN`. Token vazio → 503 (fail-closed). Comparação em tempo constante. Cron externo deve preferir `abrir-periodo-background`, pois a abertura mensal pode ultrapassar o timeout de 30s do cron-job.org quando clona conteúdo e envia e-mails.
- Teste prático: `scripts/teste_http_cron_notificacao.py` (`--http`/`--in-process`; `--no-force` imita produção; `--cadeia-atribuir` atribui seção e notifica). E2E completo: `scripts/_e2e_notificacoes.py`.
- Schedules externos espelham dias/horários guardados (`/governanca-relatorio` e `app/cron/*.py`).

Variáveis de ambiente (`.env.example` / `render.yaml`): `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `SENDGRID_FROM_NAME`, `APP_BASE_URL`, `NOTIFICAR_HABILITADO`, `NOTIFICAR_SANDBOX`, `CRON_TOKEN`; opcionais para status do cron externo: `CRONJOB_ORG_API_KEY` (`sync: false` no Render, valor só no ambiente) e `CRONJOB_ORG_JOB_*`.

Fonte única do nome `.dotx` em `app/notificacoes/modelos.py` (`slug_titulo`, `filename_para`, `caminho_para`); `scripts/build_canonical_upload_dotx.py` importa daqui.

E2E manual: `scripts/_e2e_notificacoes.py` (usuários `@notif-test.local`, exercita 4 entradas + ações coord, limpa estado). Idempotente. E2E com conteúdo real: `scripts/teste_real_ciclo_notificacao.py` (`--listar-secoes`, `--criar-periodo`/`--relatorio-id`, `--secoes`, preview via `email_sender.py`; envio efetivo exige `--usuario-email`, `--confirmar` e obedece `NOTIFICAR_*`/SendGrid).

### PDF Final

`app/pdf_render.py` transforma blocos em estrutura para `app/templates/pdf/relatorio.html`.

`app/routes/pdf.py`: `GET /relatorios/{id}/pdf` (opcional `secao_ids` na query para limitar escopo em iframes), `GET /relatorios/{id}/preview` (HTML), `GET /relatorios/{id}/exportar` (`pdf`/`docx`, escopo `inteiro`, `selecionadas` ou `importadas`).

Cuidados:

- PDF preserva sumário, numeração, legendas, fontes, figuras, tabelas, cabeçalho/rodapé e página de assinaturas.
- Marcadores `[[FIGURA:...]]`/`[[TABELA...]]` ainda suportados por compatibilidade.
- Bloco `figura` sem imagem renderiza placeholder; ideal é DOCX importar imagem real.
- Contadores de figuras/tabelas seguem o primeiro nível da seção (`4.1`, `4.2`).
- `idx` em `[[FIGURA:idx|...]]`/`[[TABELA:idx|...]]` é bimodal: com ponto (`4.1`) é "por seção" e usa contador atual; puramente numérico (`5`) é sequencial global e respeitado; vazio cai no contador local.
- 3 marcadores REF resolvidos em `_resolver_referencias` via `_MapasRef` (`_calcular_mapas_referencia`), sempre exibindo número atual. Alvo excluído → marcador permanece para sinalizar inconsistência (não gera "Figura None"):

  ```text
  [[REF:figura|ID_BLOCO]]
  [[REF:tabela|ID_BLOCO]]
  [[REF:secao|ID_SECAO]]
  ```

### Numeração Hierárquica E Referências Estáveis

`app/numeracao.py`:

- `renumerar_relatorio(db, rel_id)`: recalcula `Secao.numero/ordem` por DFS sobre a árvore (prefixo + ordem dos irmãos). Aplica em duas fases (prefixo temporário `__t` e UPDATE com `CASE`) para não colidir com `UniqueConstraint(relatorio_id, numero)`. Top-level preservado.
- `consolidar_referencias(db, rel_id)`: varre `Bloco.conteudo`/`Bloco.legenda`, troca "Figura X.Y"/"Tabela X.Y"/"Secao X.Y" (variantes com `-` e acentuação) por `[[REF:tipo|id]]`. Idempotente.
- `consolidar_e_renumerar(db, rel_id)`: atalho que faz na ordem correta.

Ordem obrigatória nas rotas que mutam estrutura: (1) `consolidar_referencias` ANTES (fixa alvo em ID estável); (2) executa mutação; (3) `renumerar_relatorio` DEPOIS. Tudo em `tx_session`. Já integrado em `relatorios.py` (criar/excluir/mover subseção), `blocos.py` (quando `_impacta_numeracao`) e `importacao.py` (após finalizar importação).

## Banco E Performance

Banco geralmente remoto (Render) com latência alta. `app/db.py` usa pool, keepalives e `isolation_level="AUTOCOMMIT"` para reduzir round-trips.

- Evite N+1 (`selectinload`, `load_only`, agregações, lote).
- Operações multi-statement com atomicidade real → `tx_session` ou `with db.begin()`.
- Não reative `pool_pre_ping` nem remova ajustes de pool sem medir impacto.
- Não conte/insira item a item quando lote resolve.

Skill `/performance-agility` (`.cursor/skills/performance-agility/SKILL.md`) para mudanças cirúrgicas com ganho verificável.

## Convenções De Frontend

- HTML/Jinja2/CSS/JavaScript simples. Sem React.
- Interface densa, utilitária, focada em produção/revisão de relatórios.
- Não fazer mudanças visuais amplas sem pedido direto.
- Em tabelas e controles da seção: preservar legibilidade, alinhamento, bordas e ações por ícones quando o padrão já existir.
- Sem texto explicativo excessivo dentro da interface.

## Convenções De Código

- Mudanças mínimas, focadas e compatíveis com o estilo existente. Não reverta alterações do usuário. Não adicione dependência sem necessidade clara. Não crie abstrações grandes para ajuste pequeno.
- Preserve nomes de domínio em português: relatório, seção, bloco, figura, legenda, fonte, medição.
- Novas rotas: `APIRouter`, `Depends(get_db)`, `current_user`, respostas HTML com `TemplateResponse` (200; reuse `response_dashboard`, `response_relatorio_detail`, `user_or_login_page`, `response_client_goto` em `app/routes/pages.py`) ou `JSONResponse` para API. **Não** use `RedirectResponse` (3xx) para fluxos de formulário; após `POST` devolva a página de destino em 200. **Exceção:** `POST /login` e `GET /logout` usam `response_client_goto` (JS `location.replace`) para alinhar URL e conteúdo.
- Templates: Jinja2 simples; prepare dados na rota.

## Linting, Validação E Encerramento

Configuração canônica em `pyproject.toml` e `.vscode/settings.json`. Indentação/charset alinham `.editorconfig` (Python 4 espaços; HTML/CSS/JS/JSON/YAML 2; Markdown sem `trim_trailing_whitespace`).

- **Regras detalhadas**: `.cursor/rules/linting.mdc` (Python/Jinja/cspell) e `.cursor/rules/code-sanitization-efficiency.mdc` (postura).
- **Encerramento de tarefa (obrigatório)**: `.cursor/rules/task-completion.mdc` — execute `scripts/dump_agent_diagnostics.py` (lê `artifacts/agent-diagnostics.txt`, corrige até saída 0), depois lints do agente nos arquivos tocados, releia integralmente.

Setup local mínimo:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Sanity check do app: `.\.venv\Scripts\python.exe -c "import app.main; print('ok')"`.
