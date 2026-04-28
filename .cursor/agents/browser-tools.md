---
name: browser-tools
description: >-
  Validacao de UI web, formularios, fluxo de importacao na tela, PDF preview, e2e. Preferir MCP navegador,
  depois Playwright; Puppeteer so se ja existir. Nao adicionar Playwright sem justificativa objetiva.
model: inherit
---

# Browser tools (subagente SRA)

- **Regra do projeto:** [browser-tools.mdc](../rules/browser-tools.mdc)
- **Ordem de preferencia:** (1) MCP de navegador, se configurado; (2) Playwright, para fluxos reproduziveis; (3) Puppeteer, apenas se ja existir no projeto.
- **Dependencies:** nao proponha Playwright nem Puppeteer como dependencia nova sem necessidade clara; confirme alternativas. Se nenhuma ferramenta estiver disponivel, declare a limitacao e sugira validacao proporcional ao risco.
- **Dominio:** alinhe rotas e permissoes com [project-instructions.md](../project-instructions.md).
- **Encerramento:** aplicar [task-completion.mdc](../rules/task-completion.mdc) nos ficheiros alterados.
