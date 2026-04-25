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
- `app/templates/secao_edit.html`: tela principal de edicao de secoes, tabela de blocos, importacao assistida e editor manual.

## Modelo De Dominio

Um `Relatorio` representa um D20 mensal, com codigo como `D20-15`, periodo, mes de referencia, numero de medicao, versao `R00/R01/...` e status.

Cada relatorio possui varias `Secao`, criadas a partir de `SECOES_PADRAO`. A numeracao e parte essencial do documento final, por exemplo `4`, `4.4`, `4.4.7`, `10.1`. Nao trate numero de secao como texto decorativo: ele direciona ordenacao, importacao e sumario.

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

### PDF Final

`app/pdf_render.py` transforma blocos em estrutura para `app/templates/pdf/relatorio.html`.

Cuidados importantes:

- O PDF deve preservar sumario, numeracao de secoes, legendas, fontes, figuras, tabelas, cabecalho/rodape e pagina de assinaturas.
- Marcadores em texto como `[[FIGURA:...]]` e `[[TABELA...]]` ainda precisam ser suportados por compatibilidade.
- Blocos `figura` sem imagem associada podem renderizar placeholder, mas o fluxo ideal de DOCX deve importar a imagem real.
- Contadores de figuras e tabelas seguem o primeiro nivel da secao, como `4.1`, `4.2`, etc.

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

## Convencoes De Codigo

- Mudancas devem ser minimas, focadas e compativeis com o estilo existente.
- Nao reverta alteracoes do usuario.
- Nao adicione dependencia nova sem necessidade clara.
- Nao crie abstracoes grandes para resolver ajuste pequeno.
- Preserve nomes e conceitos do dominio em portugues: relatorio, secao, bloco, figura, legenda, fonte, medicao.
- Para novas rotas, siga o padrao de `APIRouter`, `Depends(get_db)`, `current_user` e `RedirectResponse`/`JSONResponse` conforme o fluxo.
- Para templates, mantenha Jinja2 simples e evite logica complexa demais quando puder preparar dados na rota.

## Validacao Obrigatoria

Antes de concluir qualquer tarefa de implementacao neste repositorio:

- Releia integralmente todos os arquivos alterados apos a ultima edicao.
- Procure inconsistencias em todo o arquivo relido, estejam elas diretamente ligadas ou nao a alteracao feita.
- Corrija inconsistencias encontradas na releitura sempre que estiverem no arquivo alterado e puderem afetar eficiencia, estabilidade, legibilidade ou comportamento.
- Rode checagem da aba Problemas no workspace e deixe zerada.
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
python -c "import app.main; print('ok')"
```
