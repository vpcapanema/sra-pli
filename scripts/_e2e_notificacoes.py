"""E2E manual da Track 4 (notificações). Não é teste pytest. Roda direto:

  .\\.venv\\Scripts\\python.exe scripts/_e2e_notificacoes.py

Cria usuários de teste, dispara abertura/lembretes/recompute, valida, e
limpa tudo no final. Idempotente: pode rodar várias vezes.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Bloco,
    EntregaRelatorio,
    NotificacaoEnvio,
    Relatorio,
    Secao,
    User,
)
from app.notificacoes.service import (  # noqa: E402
    abrir_periodo,
    alterar_status_entrega,
    enviar_lembretes,
    notificar_autores_abertura,
    recompute_status_enviado,
    reenviar_manual,
    retry_falhas,
)

EMAIL_DOMAIN = "@notif-test.local"
DATA_TESTE = date(2076, 5, 1)


def _cleanup(db) -> None:
    """Apaga em ordem reversa de FK. Encontra os relatorios via duas vias:
    codigo prefix 'TEST-' e relatorios referenciados por test users."""
    test_user_ids = [
        uid for (uid,) in db.query(User.id).filter(
            User.email.like(f"%{EMAIL_DOMAIN}")
        ).all()
    ]
    rel_ids: set[int] = {
        rid for (rid,) in db.query(Relatorio.id).filter(
            Relatorio.codigo.like("TEST-%")
        ).all()
    }
    if test_user_ids:
        rel_ids.update(
            rid for (rid,) in db.query(EntregaRelatorio.relatorio_id).filter(
                EntregaRelatorio.user_id.in_(test_user_ids)
            ).all()
        )
        rel_ids.update(
            rid for (rid,) in db.query(Secao.relatorio_id).filter(
                Secao.responsavel_id.in_(test_user_ids)
            ).all()
        )
    if rel_ids:
        sec_ids = [
            sid for (sid,) in db.query(Secao.id).filter(
                Secao.relatorio_id.in_(rel_ids)
            ).all()
        ]
        db.query(NotificacaoEnvio).filter(
            NotificacaoEnvio.entrega.has(
                EntregaRelatorio.relatorio_id.in_(rel_ids)
            )
        ).delete(synchronize_session=False)
        db.query(EntregaRelatorio).filter(
            EntregaRelatorio.relatorio_id.in_(rel_ids)
        ).delete(synchronize_session=False)
        if sec_ids:
            db.query(Bloco).filter(Bloco.secao_id.in_(sec_ids)).delete(
                synchronize_session=False
            )
        db.query(Secao).filter(Secao.relatorio_id.in_(rel_ids)).delete(
            synchronize_session=False
        )
        db.query(Relatorio).filter(Relatorio.id.in_(rel_ids)).delete(
            synchronize_session=False
        )
    db.query(NotificacaoEnvio).filter(
        NotificacaoEnvio.destinatario_email.like(f"%{EMAIL_DOMAIN}")
    ).delete(synchronize_session=False)
    if test_user_ids:
        db.query(EntregaRelatorio).filter(
            EntregaRelatorio.user_id.in_(test_user_ids)
        ).delete(synchronize_session=False)
        db.query(Secao).filter(
            Secao.responsavel_id.in_(test_user_ids)
        ).delete(synchronize_session=False)
    db.query(User).filter(User.email.like(f"%{EMAIL_DOMAIN}")).delete(
        synchronize_session=False
    )
    db.commit()


def _setup(db) -> tuple[User, User, User, Relatorio]:
    print("=== Setup E2E ===")
    _cleanup(db)
    u1 = User(
        email=f"joao.test{EMAIL_DOMAIN}",
        email2=f"joao.alt{EMAIL_DOMAIN}",
        nome="Joao da Silva",
        password_hash=hash_password("x" * 8), role="autor",
    )
    u2 = User(
        email=f"maria.test{EMAIL_DOMAIN}",
        email2=f"maria.alt{EMAIL_DOMAIN}",
        nome="Maria de Souza",
        password_hash=hash_password("x" * 8), role="autor",
    )
    u3 = User(
        email=f"ferias.test{EMAIL_DOMAIN}",
        email2=f"ferias.alt{EMAIL_DOMAIN}",
        nome="Pedro de Ferias",
        password_hash=hash_password("x" * 8), role="autor",
        notificacoes_ativas=False,
    )
    db.add_all([u1, u2, u3])
    db.flush()
    rel_base = Relatorio(
        codigo="TEST-D20-99", titulo="Base Teste",
        mes_referencia="Marco/2026",
        periodo_inicio=date(2026, 2, 11),
        periodo_fim=date(2026, 3, 11),
        numero_medicao=99, versao="R00", status="finalizado",
    )
    db.add(rel_base)
    db.flush()
    db.add_all([
        Secao(relatorio_id=rel_base.id, numero="4", titulo="Visao Geral", ordem=0),
        Secao(relatorio_id=rel_base.id, numero="4.4", titulo="Atividades Apoio Tecnico", ordem=1),
        Secao(relatorio_id=rel_base.id, numero="4.4.1", titulo="Apoio Tecnico A", ordem=2, responsavel_id=u1.id),
        Secao(relatorio_id=rel_base.id, numero="4.4.7", titulo="Padronizacao", ordem=3, responsavel_id=u2.id),
        Secao(relatorio_id=rel_base.id, numero="5", titulo="Equipe", ordem=4, responsavel_id=u3.id),
    ])
    db.commit()
    print(
        f"  users: {u1.id}/{u2.id}/{u3.id}(opt-out) "
        f"rel_base id={rel_base.id}"
    )
    return u1, u2, u3, rel_base


def _fase_abertura(db, u1: User, u2: User, u3: User) -> tuple[int, int]:
    print("\n=== abrir_periodo + notificar_autores_abertura ===")
    n_autor_notif = (
        db.query(User)
        .filter(User.role == "autor", User.notificacoes_ativas.is_(True))
        .count()
    )
    r1 = abrir_periodo(db, data_referencia=DATA_TESTE)
    print(
        f"  criou={r1.criou_relatorio} rel={r1.relatorio_codigo} "
        f"entregas_cron={r1.entregas_criadas} env_cron={r1.emails_enviados}"
    )
    assert r1.criou_relatorio
    assert r1.entregas_criadas == n_autor_notif
    assert r1.emails_enviados == n_autor_notif
    novo_id = r1.relatorio_id
    assert novo_id is not None
    for u in (u1, u2):
        ent = (
            db.query(EntregaRelatorio)
            .filter_by(relatorio_id=novo_id, user_id=u.id)
            .one_or_none()
        )
        assert ent is not None
    assert (
        db.query(EntregaRelatorio)
        .filter_by(relatorio_id=novo_id, user_id=u3.id)
        .one_or_none()
        is None
    )
    db.query(Secao).filter_by(relatorio_id=novo_id, numero="4.4.1").update(
        {"responsavel_id": u1.id}
    )
    db.query(Secao).filter_by(relatorio_id=novo_id, numero="4.4.7").update(
        {"responsavel_id": u2.id}
    )
    db.query(Secao).filter_by(relatorio_id=novo_id, numero="5").update(
        {"responsavel_id": u3.id}
    )
    db.commit()
    n1 = notificar_autores_abertura(db, novo_id)
    print(
        f"  notificar_autores: env={n1.emails_enviados} "
        f"pulados={n1.pulados_ja_enviados}"
    )
    assert n1.emails_enviados == 0 and n1.emails_falhados == 0
    assert n1.pulados_ja_enviados == n_autor_notif
    n1b = notificar_autores_abertura(db, novo_id)
    assert n1b.emails_enviados == 0 and n1b.pulados_ja_enviados == n_autor_notif
    r1b = abrir_periodo(db, data_referencia=DATA_TESTE)
    assert r1b.pulada_idempotencia
    print(f"  idempotencia ok: pulada={r1b.pulada_idempotencia}")
    return novo_id, n_autor_notif


def _fase_lembrete(db, novo_rel_id: int, u1: User, n_autor_notif: int) -> None:
    print("\n=== enviar_lembretes ===")
    db.query(NotificacaoEnvio).filter(
        NotificacaoEnvio.entrega.has(
            EntregaRelatorio.relatorio_id == novo_rel_id
        )
    ).update(
        {"enviada_em": datetime.utcnow() - timedelta(hours=24)},
        synchronize_session=False,
    )
    db.commit()
    r2 = enviar_lembretes(
        db,
        tipo="lembrete",
        relatorio_id=novo_rel_id,
        ignorar_calendario=True,
    )
    print(f"  env={r2.emails_enviados} pul_intervalo={r2.pulados_intervalo}")
    assert r2.emails_enviados == n_autor_notif
    e1 = db.query(EntregaRelatorio).filter_by(
        relatorio_id=novo_rel_id, user_id=u1.id,
    ).one()
    assert e1.status == "aguardando_envio"
    print(f"  u1 status apos 2 notif: {e1.status} ok")
    r2b = enviar_lembretes(
        db,
        tipo="lembrete",
        relatorio_id=novo_rel_id,
        ignorar_calendario=True,
    )
    assert r2b.pulados_intervalo == n_autor_notif and r2b.emails_enviados == 0
    print(f"  janela 22h: pulados={r2b.pulados_intervalo} ok")


def _fase_recompute(db, novo_rel_id: int, u1: User) -> EntregaRelatorio:
    print("\n=== recompute_status_enviado ===")
    sec_u1 = db.query(Secao).filter_by(
        relatorio_id=novo_rel_id, responsavel_id=u1.id,
    ).one()
    db.add(Bloco(secao_id=sec_u1.id, tipo="texto", ordem=0, conteudo="abc", bloqueado=False))
    db.add(Bloco(secao_id=sec_u1.id, tipo="texto", ordem=1, conteudo="def", bloqueado=True))
    db.commit()
    assert not recompute_status_enviado(db, u1.id, novo_rel_id)
    print("  com 1/2 bloqueado: nao avanca ok")
    db.query(Bloco).filter_by(secao_id=sec_u1.id, ordem=0).update({"bloqueado": True})
    db.commit()
    assert recompute_status_enviado(db, u1.id, novo_rel_id)
    e1 = db.query(EntregaRelatorio).filter_by(
        relatorio_id=novo_rel_id, user_id=u1.id,
    ).one()
    assert e1.status == "enviado" and e1.data_envio is not None
    print(f"  com 2/2 bloqueado: status={e1.status} data_envio={e1.data_envio:%Y-%m-%d %H:%M}")
    return e1


def _fase_ultima_chamada(db, novo_rel_id: int, n_autor_notif: int) -> None:
    db.query(NotificacaoEnvio).filter(
        NotificacaoEnvio.entrega.has(
            EntregaRelatorio.relatorio_id == novo_rel_id
        )
    ).update(
        {"enviada_em": datetime.utcnow() - timedelta(hours=24)},
        synchronize_session=False,
    )
    db.commit()
    r3 = enviar_lembretes(
        db,
        tipo="ultima_chamada",
        relatorio_id=novo_rel_id,
        ignorar_calendario=True,
    )
    print(
        f"\n=== ultima_chamada com u1=enviado: env={r3.emails_enviados} "
        f"(deve ser {n_autor_notif - 1})"
    )
    assert r3.emails_enviados == n_autor_notif - 1


def _fase_acoes_coord(db, novo_rel_id: int, u2: User, e1: EntregaRelatorio) -> None:
    print("\n=== acoes coord ===")
    coord = User(
        email=f"coord.test{EMAIL_DOMAIN}",
        email2=f"coord.alt{EMAIL_DOMAIN}",
        nome="Coord Teste",
        password_hash=hash_password("x" * 8), role="coordenador",
    )
    db.add(coord)
    db.flush()
    e2 = db.query(EntregaRelatorio).filter_by(
        relatorio_id=novo_rel_id, user_id=u2.id,
    ).one()
    alterar_status_entrega(db, e2, "validado", coord=coord)
    db.refresh(e2)
    assert e2.status == "validado" and e2.validado_por_id == coord.id
    print(f"  alterar_status -> validado ok (validado_por={e2.validado_por_id})")
    assert reenviar_manual(db, e2)
    print("  reenviar_manual: ok")

    print("\n=== retry_falhas ===")
    fake = NotificacaoEnvio(
        entrega_id=e1.id, tipo="lembrete",
        destinatario_email=f"joao.test{EMAIL_DOMAIN}",
        sucesso=False, erro="simulated failure",
    )
    db.add(fake)
    db.commit()
    r4 = retry_falhas(db)
    print(
        f"  tentativas={r4.tentativas} sucessos={r4.sucessos} "
        f"falhas={r4.falhas} desistencias={r4.desistencias}"
    )


def main() -> int:
    db = SessionLocal()
    try:
        u1, u2, u3, _base = _setup(db)
        novo_rel_id, n_autor_notif = _fase_abertura(db, u1, u2, u3)
        _fase_lembrete(db, novo_rel_id, u1, n_autor_notif)
        e1 = _fase_recompute(db, novo_rel_id, u1)
        _fase_ultima_chamada(db, novo_rel_id, n_autor_notif)
        _fase_acoes_coord(db, novo_rel_id, u2, e1)
    finally:
        print("\n=== cleanup ===")
        _cleanup(db)
        db.close()
    print("--- E2E PASS ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
