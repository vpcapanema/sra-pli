---
name: code-sanitization-efficiency
description: >-
  Fluxo profundo de sanitizacao, refactor minimo objetivo, otimizacao, comandos flake8/pylint/djlint/npm spell,
  e checklist deste projeto. Use quando quiser refactor/revisao extensa alem das regras sempre aplicadas (.cursor/rules).
disable-model-invocation: true
---

# Code Sanitization And Efficiency Specialist

Este skill e a versao expansiva das instrucoes de codigo minimo para o SRA.

O projeto ja aplica sempre uma regra resumida em `.cursor/rules/code-sanitization-efficiency.mdc`. Invocar **`/code-sanitization-efficiency`** carrega esta versao completa (checklist powershell abaixo, detalhes de banco/UI).

## Principios

- Verdade tecnica antes de concordancia: alerte se o pedido aumentar risco sem ganho proporcional.
- Menor solucao correta; sem duplicacao nem abstracao ornamental.
- Corrigir causa raiz; evitar fallback amplo, `try/except` generico, logs temporarios e TODO desnecessario.
- Preservar dados, permissoes e nomes de dominio em portugues.

## Descoberta De Regras Antes De Editar

- `.cursor/project-instructions.md`.
- `pyproject.toml`: flake8, pylint, djlint.
- `.vscode/settings.json`: interpretador, associacoes, diagnosticos.
- `cspell.json`, `.cspell/projeto.txt`, `package.json` para texto novo.
- Validacao Python sempre com `./.venv/Scripts/python.exe`.

## Fluxo De Trabalho

1. Escopo real: arquivos, entrada, dados e comportamento esperado.
2. Evidencia concreta: linter, bug reproduzivel, paths lentos ou duplicacao.
3. Mudanca minima verificavel com menor risco.
4. Simplifique apos corrigir: codigo morto, redundancia, nomes intermediarios inuteis onde estiver no escopo.
5. Releia integralmente os arquivos alterados.
6. Zerar ou justificar notificacoes dos arquivos alterados na aba Problemas.

## Regras De Performance (Resumo)

- Banco: lote, `selectinload`, `load_only`, agregacoes; evitar N+1 e commits em loop.
- Templates: mover calculos repetidos para a rota quando reduz trabalho sem obscurificar.
- JavaScript: evitar trabalho repetido no DOM onde houver ganho seguro simples.

## Validacao (ajuste Os Caminhos)

```powershell
.\.venv\Scripts\python.exe -m flake8 caminho/do/arquivo.py
.\.venv\Scripts\python.exe -m pylint --rcfile=pyproject.toml caminho/do/arquivo.py
.\.venv\Scripts\python.exe -m djlint app/templates
npm run spell
```

## Formato Da Resposta Final

Pt-BR, curto: o que foi corrigido ou otimizado; arquivos alterados; validacoes executadas; estado dos Problemas; risco residual se houver.
