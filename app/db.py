from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from contextlib import contextmanager
from .config import settings

# Banco real é Postgres no Render. Normalizamos o esquema para psycopg2.
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://") and "+psycopg2" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

if not db_url.startswith("postgresql+psycopg2://"):
    raise RuntimeError(
        "DATABASE_URL deve apontar para Postgres (postgres:// ou postgresql://). "
        f"Recebido: {settings.DATABASE_URL[:40]}..."
    )

# Postgres remoto (Render Oregon): cada round-trip custa ~190ms do Brasil.
# - pool grande para reaproveitar conexões (handshake TLS custa ~3 RTTs).
# - pool_recycle < keep-alive do Render (5 min) para não pegar conexões mortas.
# - pool_pre_ping desligado (evita 1 RTT extra por checkout).
# - tcp keepalives mantêm a conexão viva atravessando NAT/firewall.
# - isolation_level=AUTOCOMMIT remove os BEGIN/COMMIT implícitos por request,
#   reduzindo latência de ~570ms (3 RTTs) para ~190ms (1 RTT). Endpoints que
#   precisam de atomicidade multi-statement devem usar `with db.begin():`.
engine = create_engine(
    db_url,
    future=True,
    pool_size=10,
    max_overflow=5,
    pool_recycle=280,
    pool_pre_ping=False,
    isolation_level="AUTOCOMMIT",
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
        "connect_timeout": 10,
    },
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def tx_session():
    """Sessão com transação explícita (BEGIN/COMMIT/ROLLBACK) para operações
    multi-statement que exigem atomicidade. Sobrescreve o AUTOCOMMIT do engine
    abrindo uma conexão com isolation_level transacional."""
    conn = engine.connect().execution_options(isolation_level="READ COMMITTED")
    sess = Session(bind=conn, autoflush=False, future=True)
    try:
        sess.begin()
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
        conn.close()
