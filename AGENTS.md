# Agentes IA — Convencao Do Projeto

Este projeto e o SRA (Sistema de Relatorios de Atividades) do contrato PLI/SP-2050. Toda aplicacao roda em modo de producao real — nao crie mocks, dados ficticios ou atalhos.

## Onde Ler As Instrucoes Canonicas

- **`.cursor/project-instructions.md`** — fonte **unica de verdade** no repositorio: stack, modelo de dominio, permissoes, fluxos, banco, PDF, frontend, linting e validacao obrigatoria. No inicio do arquivo ha o indice da pasta `.cursor/` (rules, skills e agents). Leia integralmente antes de mudar qualquer comportamento persistente ou contrato de dados.

## Complementos No Cursor

- **`.cursor/rules/*.mdc`** — regras do editor sempre aplicadas ou condicionadas (linting, postura codigo minimo, browser, documentacao). Encerramento de tarefa: **`.cursor/rules/task-completion.mdc`** — obrigatorio executar `scripts/dump_agent_diagnostics.py`, ler `artifacts/agent-diagnostics.txt`, corrigir até saida limpa; depois lints do agente e aba Problemas do humano; releitura integral dos arquivos alterados.
- **`.cursor/skills/*/SKILL.md`** — workflows especializados; usar `/nome-do-skill` na conversa em modo Agent:
  - `application-text-intelligence` — texto, documentos e importacao assistida.
  - `performance-agility` — mudancas cirurgicas de performance.
  - `code-sanitization-efficiency` — checklist flake8/pylint/djlint sob demanda (`/`; a versao curta esta em `.cursor/rules`).
  - `melhorar-upload-conteudo` — melhorias no fluxo `importacao`/upload.
- **`.cursor/agents/*.md`** — subagentes do Cursor (prompt + frontmatter); no modo **Agent**, invoque com **`/nome`** (ex.: `/code-sanitization-efficiency`) ou peca delegacao. Alinhados a skills e regras:
  - `application-text-intelligence`, `performance-agility`, `code-sanitization-efficiency`, `melhorar-upload-conteudo`
  - `browser-tools`, `context-documentation`, `cursor-workbench-ui` (este ultimo: consulta de layout IDE, somente leitura)
- **“Switch agent mode” (Agent / Ask / Plan / Debug):** esse selector e para o **modo de conversa** do Cursor, **nao** para escolher um ficheiro de `.cursor/agents/`. Os subagentes personalizados **nao** passam a aparecer ai por configuracao do repositorio — e limitacao/comportamento do produto, nao algo que o projeto possa registar num menu.
- **Onde escolher subagentes e skills:** no **modo Agent**, no campo do chat, prima **`/`** — lista de **comandos** (skills, subagentes, etc.) para filtrar ou clicar; ou escreva `/nome` (ex.: `/browser-tools`). Com **`@`** pode anexar skills como contexto (ver documentacao Cursor). O que aparece depende da versao do Cursor.

Os caminhos em `.github/agents/` e `.github/prompts/` e o antigo **`copilot-instructions.md`** foram removidos; o contexto de dominio ficou apenas em `.cursor/` para evitar duplicacao e dependencia do GitHub Copilot.

## O Que Toda Mudanca Deve Respeitar

1. Convencoes descritas em **`.cursor/project-instructions.md`** (secoes "Convencoes De Codigo", "Modelo De Dominio", "Regras De Permissao", "Fluxos Principais").
2. Linters em `pyproject.toml`; a aba Problemas zerada para os arquivos alterados. Secao "Linting E Formatacao" no project-instructions.
3. Validacao obrigatoria na mesma secao do project-instructions.
4. **Documentacao viva**: mudancas relevantes de dominio, rotas ou arquitetura exigem atualizar **`.cursor/project-instructions.md`** na mesma entrega.

## Setup Local Minimo

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import app.main; print('ok')"
```

O Cursor deve usar o interpretador `./.venv/Scripts/python.exe`, ja em `.vscode/settings.json`. Apos clonar e instalar, rode `Developer: Reload Window` para flake8, pylint, djlint e jinja-html.
