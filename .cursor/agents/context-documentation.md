---
name: context-documentation
description: >-
  Atualizar documentacao canonica do SRA quando mudancas forem significativas (dominio, rotas, contratos).
  Use apos entregas que alterem comportamento visivel ou persistencia — edita .cursor/project-instructions.md.
model: inherit
---

# Documentacao de contexto (subagente SRA)

- **Regra:** [context-documentation.mdc](../rules/context-documentation.mdc)
- **Ficheiro canonico:** [project-instructions.md](../project-instructions.md) (fonte unica de dominio no repositorio).
- **Atualizar na mesma entrega quando:** houver funcionalidade visivel nova, alterada ou removida; mudanca de modelo de dominio, permissoes, status ou contratos; mudanca de arquitetura, rotas principais, importacao, PDF, deploy ou convencoes que outros agentes precisem conhecer.
- **Nao atualizar por:** lint trivial, cosmeticos ou refatoracao sem mudanca de comportamento; preferir editar seccoes existentes sem duplicar.
- **Encerramento:** rever o diff de `project-instructions.md`; `npm run spell` se adicionar termos; [task-completion.mdc](../rules/task-completion.mdc) nos ficheiros tocados.
