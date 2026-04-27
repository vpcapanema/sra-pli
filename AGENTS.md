# Agentes IA — Convencao Do Projeto

Este projeto e o SRA (Sistema de Relatorios de Atividades) do contrato PLI/SP-2050. Toda aplicacao roda em modo de producao real — nao crie mocks, dados ficticios ou atalhos.

## Onde Ler As Instrucoes

As instrucoes canonicas estao em:

- **`.github/copilot-instructions.md`** — fonte unica de verdade. Cobre stack, modelo de dominio, regras de permissao, fluxos principais, banco/performance, frontend, **linting**, e **validacao obrigatoria**. Leia integralmente antes de mudar qualquer arquivo.
- **`.github/agents/*.agent.md`** — agentes especializados:
  - `application-text-intelligence.agent.md` — extracao/classificacao de texto, importacao assistida.
  - `performance-agility.agent.md` — postura para tarefas de performance.
- **`.cursor/rules/*.mdc`** — regras especificas do Cursor IDE (linting, etc.).

## O Que Toda Mudanca Deve Respeitar

1. **Convencoes de codigo e dominio** descritas em `.github/copilot-instructions.md` (secoes "Convencoes De Codigo", "Modelo De Dominio", "Regras De Permissao", "Fluxos Principais").
2. **Linters configurados** (`flake8`, `pylint`, `djlint`) com configuracao canonica em `pyproject.toml`. A aba Problemas do Cursor deve ficar zerada para os arquivos alterados antes de concluir. Detalhes na secao "Linting E Formatacao".
3. **Validacao obrigatoria** descrita na secao "Validacao Obrigatoria" do mesmo arquivo: releitura integral dos arquivos alterados, checagem de Problemas, validacao objetiva (import, render, snippet) e relato final do que foi feito.
4. **Documentacao viva**: se uma mudanca alterar funcionalidade, dominio, permissao, arquitetura, rotas, importacao, PDF, deploy ou tarefas de desenvolvimento de modo relevante, atualize `.github/copilot-instructions.md` na mesma entrega.
5. **Ferramentas de navegador**: para tarefas de UI/fluxo web, use MCP de navegador, Playwright ou Puppeteer quando disponiveis, conforme o padrao em `.github/copilot-instructions.md`.

## Setup Local Minimo

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import app.main; print('ok')"
```

O Cursor deve usar o intérprete `./.venv/Scripts/python.exe`, ja apontado em `.vscode/settings.json`. Apos clonar e instalar, rode `Developer: Reload Window` para as extensoes (`flake8`, `pylint`, `djlint`, `jinjahtml`) carregarem corretamente.
