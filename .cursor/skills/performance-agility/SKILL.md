---
name: performance-agility
description: >-
  Otimizar performance e agilidade, reduzir latencia, remover gargalos, estabilizar rotinas lentas,
  revisar consultas, caches, importacao, render, PDF, banco, FastAPI ou SQLAlchemy com mudancas
  cirurgicas e ganho verificavel.
---

# Performance Agility (SRA)

Melhoria de performance e agilidade preservando comportamento funcional e regras de negocio.

## Prioridades

- Mudancas cirurgicas apenas onde ha gargalo real ou latencia verificavel.
- Preservar seguranca, dados, compatibilidade e legibilidade.
- Preferir: menos round-trips, trabalho menos repetido, consultas mais diretas, cache controlado, menor render, menos I/O, parsing eficiente, sem esperas desnecessarias.
- Sem arquitetura nova ou dependencias novas sem necessidade objetiva.

## Fluxo

1. Mapeie fluxo antes de editar: entradas, consultas, loops, I/O externos, templates.
2. Identifique causa provavel do gargalo com evidencia (consultas repetidas, N+1, serializacao, render, chamadas remotas).
3. Implemente mudancas pequenas e verificaveis; grandes tarefas em etapas.
4. Apos editar: releia integralmente cada arquivo alterado e corrija inconsistencias que afetem eficiencia, estabilidade ou comportamento.
5. Zere Problemas nos arquivos alterados ou registre precisamente excecoes preexistentes fora do escopo.
6. Teste fluxo alterado com evidencia objetiva (import app, endpoints, tests existentes ou snippets focados).

## Regras De Edicao

- Padroes do repositorio; codigo minimo; mudancas minimas.
- Nao revertir alteracoes do usuario nem operacoes destrutivas no git sem pedido explicito.
- Sem mocks substituindo comportamento real de producao.
- Sem TODOs, logs temporarios ou instrumentacao improvisada sem necessidade.

## Referencia Formal

Este skill complementa `.cursor/project-instructions.md` (banco e performance onde aplicavel).

## Formato Da Resposta Final

Em pt-BR e direto: o que foi acelerado ou estabilizado; arquivos alterados; validacoes realizadas; se Problemas foi zerado; riscos residuais quando existirem.
