"""Zera as tabelas notificacao_envio e entrega_relatorio."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal
from app.models import NotificacaoEnvio, EntregaRelatorio

db = SessionLocal()

print("Zerando tabelas de notificações...")
print("=" * 70)

# Contar registros antes
count_notif = db.query(NotificacaoEnvio).count()
count_entrega = db.query(EntregaRelatorio).count()

print("Registros antes:")
print(f"  NotificacaoEnvio: {count_notif}")
print(f"  EntregaRelatorio: {count_entrega}")
print()

# Deletar na ordem correta (primeiro notificacao_envio devido à FK)
db.query(NotificacaoEnvio).delete(synchronize_session=False)
db.query(EntregaRelatorio).delete(synchronize_session=False)
db.commit()

# Contar registros depois
count_notif_after = db.query(NotificacaoEnvio).count()
count_entrega_after = db.query(EntregaRelatorio).count()

print("Registros depois:")
print(f"  NotificacaoEnvio: {count_notif_after}")
print(f"  EntregaRelatorio: {count_entrega_after}")
print()
print("Tabelas zeradas com sucesso.")

db.close()
