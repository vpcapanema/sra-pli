# TODO - Ajustes seção 1.2.1 Notificação assistida de usuários

- [x] 1. Atualizar `app/services/governanca/execucao_manual_jobs.py`
  - [x] Tornar `abertura` idempotente (`force=False`)
  - [x] Adicionar aviso quando abertura já tiver sido disparada para o relatório
- [x] 2. Atualizar textos em `app/templates/complementos/governanca_relatorio.html`
  - [x] Remover menção de "força reenvio" em abertura
  - [x] Explicar exceção de idempotência para abertura e orientar uso de outro tipo
- [x] 3. Atualizar este TODO com progresso
