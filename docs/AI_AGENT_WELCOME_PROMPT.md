# Boas-vindas — agente de IA (SRA)

Este ficheiro é **agnóstico de IDE** (não depende de Cursor, VS Code, Copilot, etc.). Vive em `docs/` para não se misturar com pastas de configuração do editor (`.cursor/`, `.vscode/`, …).

**Como usar:** no início de uma sessão, peça ao agente para **ler primeiro** este documento e, em seguida, as leituras listadas em [Ordem sugerida de leitura](#ordem-sugerida-de-leitura). Opcionalmente pode **copiar/colar** secções relevantes para o chat.

---

## O que é a aplicação

**SRA** (Sistema de Relatórios de Atividades) — contrato **PLI/SP-2050**. Plataforma web interna para relatórios mensais D20: autores preenchem secções com blocos estruturados; coordenação e administração gerem relatórios, entregas, validação e **PDF/DOCX** finais.

**Objetivos principais:** produção semi-automática do relatório, governança de conteúdo, ciclo de notificações por e-mail, importação assistida com revisão humana, exportação alinhada ao contrato visual.

**Modo de trabalho do repo:** produção real — evitar mocks, dados fictícios ou atalhos que escondam comportamento.

---

## Arquitetura (resumo)

| Camada | Tecnologia |
|--------|------------|
| API / páginas | **FastAPI** + **Jinja2** (HTML tradicional; não há SPA React) |
| Dados | **PostgreSQL** via **SQLAlchemy 2** |
| PDF/Entrega | Preview HTML A4 (`app/templates/pdf/relatorio.html`) + **DOCX** via `python-docx` |
| Sessão | Cookies assinados (`SECRET_KEY`, middleware de sessão) |
| E-mail | **SendGrid** (envio + webhook de eventos) |
| Deploy típico | **Docker** + **Render** (`render.yaml` na raiz) |
| Jobs agendados | HTTP `POST /admin/cron/...` com **`X-Cron-Token`** (cron externo, ex. cron-job.org) ou CLI em `app/cron/` |

---

## Estrutura de pastas (onde procurar)

| Caminho | Conteúdo |
|---------|-----------|
| `app/main.py` | Entrada FastAPI, middlewares, montagem de rotas |
| `app/routes/` | Rotas HTTP (páginas, API, PDF, notificações, cron admin) |
| `app/models.py` | Modelo ORM |
| `app/config.py` | **Mapeamento env → `Settings`** (nomes exatos das variáveis) |
| `app/templates/` | Jinja (UI, PDF, e-mails) |
| `app/static/` | CSS/JS |
| `app/notificacoes/` | Serviço de notificações e templates de e-mail |
| `app/services/` | Lógica de domínio (validação, importação, etc.) |
| `scripts/` | PowerShell/Python de deploy, diagnóstico, testes |
| `render.yaml` | Blueprint Render (plano de instância, `envVars`; segredos com `sync: false`) |
| `.env.example` | **Lista de referência** de variáveis de ambiente (sem valores reais) |
| `.cursor/project-instructions.md` | Domínio, rotas, permissões, fluxos (fonte longa de referência do projeto) |

---

## Serviços externos ligados ao sistema

| Serviço | Uso no SRA | Variáveis / ficheiros relevantes |
|----------|------------|-----------------------------------|
| **PostgreSQL** | Base de dados da aplicação | `DATABASE_URL` (`.env.example`, `app/config.py`) |
| **SendGrid** | Envio de e-mails do ciclo de notificações; webhook de eventos | `SENDGRID_API_KEY`, `SENDGRID_FROM_*`, `SENDGRID_EVENT_WEBHOOK_TOKEN`, `APP_BASE_URL`, `NOTIFICAR_*` |
| **Render** (ou outro PaaS) | Hospedagem do container, envs de produção | `render.yaml`; no painel: mesmas chaves que `.env.example` onde `sync: false` |
| **cron-job.org** (opcional) | Painel de governança mostra estado dos jobs HTTP | `CRONJOB_ORG_API_KEY`, `CRONJOB_ORG_JOB_*` |
| **Render CLI** (opcional, máquina do developer) | Script de commit/deploy consulta API | `RENDER_API_KEY` e `RENDER_SERVICE_ID` (ver `scripts/sra_commit_deploy.ps1`; **não** versionar valores) |
| **Quill 2** (CDN jsDelivr) | Editor WYSIWYG na UI | Sem chave de API; dependência de rede pública |

**Nota:** revisão linguística pode usar **LanguageTool** local (Java no PATH); não é um “serviço cloud” obrigatório com API key no repo.

---

## Onde estão credenciais, chaves e tokens (mapa)

**Regra de ouro:** valores reais **nunca** devem ir para o Git. O repo só mantém **nomes** de variáveis e placeholders.

### 1. Esquema oficial de variáveis (sem segredos)

| Ficheiro | Função |
|----------|--------|
| **`.env.example`** | Lista **todas** as variáveis que a app e scripts esperam; comentários explicam sandbox SendGrid, `CRON_TOKEN`, webhook, etc. **Copiar para `.env`** local e preencher — `.env` está no **`.gitignore`**. |
| **`app/config.py`** | Classe `Settings` (`pydantic_settings`): lê `os.environ` / ficheiro **`.env`** (`env_file=".env"`). Aqui vê-se o **nome exato** de cada variável consumida pela aplicação. |

### 2. Segredos locais (máquina do developer)

| Local | Função |
|-------|--------|
| **`.env`** (raiz, **não versionado**) | `DATABASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD`, chaves SendGrid, tokens de cron/webhook, etc. **Não listar nem copiar para chats/issues.** |
| **Variáveis de utilizador do SO** | Ex.: `RENDER_API_KEY` para a pipeline de deploy — exigida por `scripts/sra_commit_deploy.ps1` quando se espera o passo Render (ver comentários no script). |

### 3. Produção / staging (hospedagem)

| Local | Função |
|-------|--------|
| **Painel Render → Web Service → Environment** | Valores reais de `DATABASE_URL`, `SECRET_KEY`, `SENDGRID_API_KEY`, `CRON_TOKEN`, `SENDGRID_EVENT_WEBHOOK_TOKEN`, etc. Chaves declaradas em `render.yaml` com `sync: false` **não** vêm do Git; definem-se só no painel ou API do Render. |
| **`render.yaml`** | Documenta **quais** chaves existem no serviço; valores sensíveis: `sync: false`. Não coloque segredos em claro no YAML versionado. |

### 4. Scripts que assumem segredos no ambiente

| Ficheiro | O que espera |
|----------|----------------|
| `scripts/sra_commit_deploy.ps1` | `RENDER_API_KEY` (e opcionalmente `RENDER_SERVICE_ID`) no ambiente para polling de deploy |
| `scripts/teste_http_cron_notificacao.py` | `CRON_TOKEN`, URL do serviço |
| `scripts/e2e_numeracao_playwright.py`, `scripts/teste_real_ciclo_notificacao.py`, etc. | Tipicamente `DATABASE_URL` e credenciais alinhadas ao `.env` |

### 5. Rotas internas que usam tokens (não são ficheiros, mas são “superfícies” de segredo)

- **`X-Cron-Token`** → deve coincidir com `CRON_TOKEN` (`app/config.py`). Endpoints em `app/routes/cron_admin.py`.
- **Webhook SendGrid** → query `token=` alinhada a `SENDGRID_EVENT_WEBHOOK_TOKEN` (ver rotas em `cron_admin` / notificações conforme implementação atual).

Se alterar nomes de variáveis, atualize **`.env.example`**, **`app/config.py`** e a documentação de deploy em conjunto.

---

## Ordem sugerida de leitura

1. **Este ficheiro** (`docs/AI_AGENT_WELCOME_PROMPT.md`) — contexto, segredos, serviços.
2. **`.env.example`** — contrato completo de configuração local.
3. **`app/config.py`** — o que a app carrega de facto.
4. **`.cursor/project-instructions.md`** — domínio, rotas, PDF, notificações, convenções (ficheiro longo; fonte principal do produto).
5. **`AGENTS.md`** (raiz) — convenções de agentes **neste** repo (lint, `project-instructions`, skills em `.cursor/`).
6. **`render.yaml`** — se a tarefa for deploy/infra.

---

## Boas práticas (segredos e operação)

- **Nunca** commitar `.env`, chaves API, tokens de produção, nem saídas de logs com passwords.
- **Não** colar valores reais em issues, PRs, chats públicos ou screenshots.
- Tratar **`SECRET_KEY`**, **`CRON_TOKEN`**, **`SENDGRID_EVENT_WEBHOOK_TOKEN`** e **`DATABASE_URL`** como credenciais de mesmo nível de sensibilidade que passwords.
- Preferir **rotação** se um valor tiver sido exposto (SendGrid: revogar key no painel; cron: gerar novo token e atualizar Render + cron-job.org).
- Em **PRs**, usar `.env.example` só com placeholders; diff mínimo em ficheiros de configuração.
- Para **SendGrid sem enviar** em desenvolvimento: deixar `SENDGRID_API_KEY` vazio ou usar `NOTIFICAR_SANDBOX=true` conforme comentários em `.env.example`.

---

## Prompt mínimo para colar no chat (opcional)

O mesmo texto, já formatado para copiar/colar, está na raiz do repo: **`AI_AGENT_INITIAL_COMMAND.txt`**.

```text
Estás no repositório SRA (FastAPI, Postgres, SendGrid, preview HTML A4 + DOCX).
Lê primeiro docs/AI_AGENT_WELCOME_PROMPT.md, depois .env.example e app/config.py.
Não lês nem reproduzas .env. Segue AGENTS.md e .cursor/project-instructions.md para domínio e regras do repo.
```

---

*Última dica:* se a tarefa for só domínio/rotas/UI, a profundidade está em **`.cursor/project-instructions.md`**; se for integração externa, segurança ou deploy, cruze sempre com **`.env.example`**, **`render.yaml`** e **`app/config.py`**.
