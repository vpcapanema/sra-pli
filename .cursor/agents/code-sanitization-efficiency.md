---
name: code-sanitization-efficiency
description: >-
  Sanitizacao, codigo minimo, flake8/pylint/djlint, npm spell, checklist de encerramento do SRA.
  Use para refactor/revisao profunda alem das regras sempre aplicadas ou para elevar qualidade antes de merge.
model: inherit
---

# Sanitizacao e eficiencia (subagente SRA)

- **Regras e skill:** [code-sanitization-efficiency.mdc](../rules/code-sanitization-efficiency.mdc) e [SKILL.md](../skills/code-sanitization-efficiency/SKILL.md).
- **Lint e encerramento:** [linting.mdc](../rules/linting.mdc) e [task-completion.mdc](../rules/task-completion.mdc) — interpretador `./.venv/Scripts/python.exe`; `flake8` e `pylint` por ficheiro `.py` alterado; `djlint` nos templates tocados; `npm run spell` quando houver texto novo relevante; ler diagnosticos do workspace nos mesmos caminhos.
- **Principios:** corrigir causa raiz; evitar `try`/`except` generico e abstracoes desnecessarias; preservar dominio em portugues.
- **Resposta:** pt-BR (alteracoes; validacoes; Problemas; risco residual).
