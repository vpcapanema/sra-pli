# Agentes IA — Convenção Do Projeto

SRA (Sistema de Relatórios de Atividades) — contrato PLI/SP-2050. Aplicação roda em produção real: sem mocks, dados fictícios ou atalhos.

## Onde Ler O Que

- **`.cursor/project-instructions.md`** — fonte canônica: stack, modelo de domínio, permissões, fluxos, banco, PDF, frontend. Leia antes de mudar comportamento persistente ou contrato de dados.
- **`.cursor/rules/*.mdc`** — regras (linting, sanitização, encerramento de tarefa, browser, documentação viva). `alwaysApply: true` carrega em toda mensagem; demais ativam por descrição/glob.
- **`.cursor/skills/*/SKILL.md`** — workflows especializados; ative com `/nome-do-skill` no modo Agent.
- **`.cursor/agents/*.md`** — subagentes; invoque com `/nome` no modo Agent.

## O Que Toda Mudança Deve Respeitar

1. Convenções de domínio em `project-instructions.md`.
2. Linters de `pyproject.toml`; aba Problemas zerada nos arquivos alterados (ver `.cursor/rules/linting.mdc` e `task-completion.mdc`).
3. Mudança relevante de domínio/rotas/arquitetura → atualizar `project-instructions.md` na mesma entrega.

## Setup Local Mínimo

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import app.main; print('ok')"
```

Cursor usa `./.venv/Scripts/python.exe` (já em `.vscode/settings.json`). Após clonar e instalar: `Developer: Reload Window` para flake8, pylint, djlint, jinja-html.

## Cursor Cloud specific instructions

### Services

| Service | How to start | Port |
|---------|-------------|------|
| PostgreSQL 16 | `docker start sra-pg` (or `docker run -d --name sra-pg -e POSTGRES_PASSWORD=sra -e POSTGRES_DB=sra -p 5432:5432 postgres:16`) | 5432 |
| FastAPI (uvicorn) | `.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001` | 8001 |

### Startup sequence

1. Start Docker daemon: `dockerd &>/tmp/dockerd.log &` (wait ~3s)
2. Start PostgreSQL: `docker start sra-pg` (container already exists after first setup)
3. Wait for PG: `docker exec sra-pg pg_isready -U postgres`
4. Start the app: `.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001`

The app auto-creates tables and seeds the admin user on first request (bootstrap).

### Environment

- `.env` at repo root with `DATABASE_URL=postgresql+psycopg2://postgres:sra@localhost:5432/sra`
- Admin credentials: `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`
- Login form field for role is `role` (not `perfil`), values: `admin`, `coordenador`, `autor`

### Linting (Linux paths)

```bash
.venv/bin/python -m flake8 app
.venv/bin/python -m pylint --rcfile=pyproject.toml app
.venv/bin/python -m djlint app/templates --check
npm run spell
```

### Key gotchas

- The "Criar relatório" form in the UI requires selecting a base PDF from `relatorios_entregues/` or uploading one. The directory ships with existing PDFs.
- WeasyPrint needs system libs (Pango, Cairo, fonts) — already present in the VM image.
- `djlint --check` reports formatting suggestions (exit code 1) for pre-existing template style; this is not a blocking error.
- Node.js (`npm install`) is only for cspell/markdownlint dev tooling, not for the application itself.
