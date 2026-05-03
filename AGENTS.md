# Agentes IA — Convenção Do Projeto

SRA (Sistema de Relatórios de Atividades) — contrato PLI/SP-2050. Aplicação roda em produção real: sem mocks, dados fictícios ou atalhos.

## Onde Ler O Que

- **`docs/AI_AGENT_WELCOME_PROMPT.md`** — boas-vindas **agnósticas de IDE** (fora de `.cursor/`): objetivos, arquitetura, serviços externos, **mapa de credenciais** (onde estão e onde *não* estão) e ordem de leitura. Use no início da sessão ou com agentes que não carregam regras do Cursor.
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
