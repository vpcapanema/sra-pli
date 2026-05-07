# TODO - Correção fluxo confirm + diagnóstico de falhas no envio manual

- [x] 1. Levantar contexto do problema no frontend e backend
  - [x] Confirmar origem do log `[fluxo confirm] cancelado — POST não enviado`
  - [x] Confirmar origem dos contadores `emails_enviados/emails_falhados/pulados_ja_enviados`
- [ ] 2. Atualizar `app/static/js/sra_process_ui.js`
  - [ ] Adicionar trava anti-reentrância no submit com confirmação
  - [ ] Fixar chave/action do submit atual para evitar corrida
  - [ ] Garantir limpeza da trava em cancelamento e envio
- [ ] 3. Atualizar `app/notificacoes/service.py`
  - [ ] Melhorar logs diagnósticos em `notificar_autores_abertura`
  - [ ] Melhorar logs diagnósticos em `_processar_destinatario` (destinos, modo, erro)
- [ ] 4. Validar resultado esperado
  - [ ] Confirm não cancelar indevidamente quando usuário confirma
  - [ ] Logs explicarem claramente causa de `emails_falhados`
