---
name: melhorar-upload-conteudo
description: >-
  Melhorar upload e importacao assistida de conteudo SRA (TXT/DOCX, revisao antes de persistir).
  Foco em importacao.py, secao_edit.html e fluxo existente — nao redesenhar a app inteira.
model: inherit
---

# Upload e importacao de conteudo (subagente SRA)

- **Workflow:** seguir [SKILL.md](../skills/melhorar-upload-conteudo/SKILL.md).
- **Ficheiros prioritarios:** `app/routes/importacao.py`, `app/templates/secao_edit.html`; quando necessario `app/models.py`, templates PDF e [project-instructions.md](../project-instructions.md).
- **Regras:** sem numeracao fixa de secao no codigo; taxonomia vem do relatorio; revisao humana antes de persistir; HTML/Jinja2 sem React.
- **Texto e parsers (visao larga):** alinhar com o subagente `/application-text-intelligence`.
- **Encerramento:** [task-completion.mdc](../rules/task-completion.mdc); testes objetivos com TXT e DOCX.
- **Resposta:** pt-BR (mudancas; ficheiros; validacoes; Problemas).
