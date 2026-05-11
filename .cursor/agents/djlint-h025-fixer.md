---
description: Corrige erros H025 (Tag seems to be an orphan) do djlint em templates Jinja2/HTML
---

# Agente: djlint-h025-fixer

## Quando usar

Use este agente quando o djlint reportar erro H025 "Tag seems to be an orphan" em templates HTML/Jinja2.

## Causa comum do H025

O erro H025 ocorre quando o parser do djlint não consegue identificar corretamente a estrutura de tags HTML, geralmente devido a:

- Jinja2 colocado entre a tag de abertura e o fechamento
- Espaços extras em tags
- Tags HTML não fechadas corretamente

## Solução padrão

Mova o código Jinja2 para dentro do atributo HTML.

Exemplo: coloque a condicional Jinja2 inline no atributo value da tag option

## Passos para corrigir

1. Identifique a linha com erro H025
2. Verifique se há código Jinja2 entre a tag de abertura e o fechamento
3. Mova o Jinja2 para dentro do atributo HTML
4. Remova espaços extras desnecessários nas tags HTML
5. Execute djlint check para verificar se o erro foi resolvido

## Exemplos de correção

### Caso 1: Atributo condicional

Antes: input com Jinja2 fora do atributo

Depois: input com Jinja2 inline no atributo type

### Caso 2: Espaço extra em tag

Antes: tag tr com espaço antes do fechamento

Depois: tag tr sem espaço extra

## Comandos úteis

Verificar erros H025 em um arquivo:

```bash
.venv/Scripts/python.exe -m djlint app/templates/NOME_DO_ARQUIVO.html --check
```

Auto-corrigir formatação (cuidado: pode alterar estilo):

```bash
.venv/Scripts/python.exe -m djlint app/templates/NOME_DO_ARQUIVO.html --reformat
```

## Notas

- Não use `--reformat` automaticamente sem revisão, pois pode alterar o estilo do template
- Priorize correções manuais que mantenham a legibilidade
- Após corrigir, verifique se não introduziu outros erros de lint
