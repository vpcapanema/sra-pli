"""Teste funcional do custom_email_sender.py.

Este script testa a execução de alertas configuráveis usando o custom_email_sender.
Modo sandbox para não enviar emails reais.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.auth import get_db
from app.models import Alerta, AlertaFluxo, User
from app.services.central_notificacoes.custom_email_sender import (
    executar_fluxo_alerta,
    executar_alerta_completo,
)


def criar_dados_teste(db: Session) -> tuple[Alerta, AlertaFluxo]:
    """Cria alerta e fluxo de teste."""
    # Verifica se já existe usuário admin
    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        print("ERRO: Nenhum usuário admin encontrado. Crie um admin primeiro.")
        sys.exit(1)

    # Cria alerta de teste
    alerta = Alerta(
        nome="Teste Custom Email Sender",
        descricao="Alerta de teste para validar custom_email_sender.py",
        status="ativo",
        frequencia="unico",
        timezone="America/Sao_Paulo",
        inicio_alerta=datetime.now(timezone.utc),
        fim_alerta=datetime.now(timezone.utc) + timedelta(days=1),
        condicao_encerramento="manual",
        criado_por_id=admin.id,
    )
    db.add(alerta)
    db.flush()

    # Cria fluxo de teste
    fluxo = AlertaFluxo(
        alerta_id=alerta.id,
        ordem=1,
        tipo_mensagem="alerta_configuravel",
        perfis_destinatarios_json='["admin"]',
        dia_no_ciclo=1,
        hora_disparo="09:00",
        ativo=True,
    )
    db.add(fluxo)
    db.commit()
    db.refresh(alerta)
    db.refresh(fluxo)

    print(f"Alerta criado: ID={alerta.id}, Nome={alerta.nome}")
    print(f"Fluxo criado: ID={fluxo.id}, Tipo={fluxo.tipo_mensagem}")

    return alerta, fluxo


def testar_execucao_fluxo(db: Session, alerta_id: int, fluxo_id: int):
    """Testa execução de um fluxo."""
    print("\n=== Testando execução de fluxo ===")
    try:
        execucao = executar_fluxo_alerta(db, alerta_id, fluxo_id)
        print(f"Execução concluída: ID={execucao.id}")
        print(f"Status: {execucao.status}")
        print(f"Sucesso: {execucao.sucesso}")
        if execucao.erro:
            print(f"Erro: {execucao.erro}")
        return execucao
    except Exception as e:
        print(f"ERRO na execução: {e}")
        import traceback

        traceback.print_exc()
        return None


def testar_execucao_completa(db: Session, alerta_id: int):
    """Testa execução completa de um alerta."""
    print("\n=== Testando execução completa ===")
    try:
        execucoes = executar_alerta_completo(db, alerta_id)
        print(f"Execuções criadas: {len(execucoes)}")
        for e in execucoes:
            print(f"  - ID={e.id}, Status={e.status}, Sucesso={e.sucesso}")
        return execucoes
    except Exception as e:
        print(f"ERRO na execução completa: {e}")
        import traceback

        traceback.print_exc()
        return None


def limpar_dados_teste(db: Session, alerta_id: int):
    """Remove dados de teste."""
    print("\n=== Limpando dados de teste ===")
    alerta = db.get(Alerta, alerta_id)
    if alerta:
        db.delete(alerta)
        db.commit()
        print(f"Alerta {alerta_id} removido.")


def main():
    """Executa testes."""
    print("Iniciando testes do custom_email_sender.py")
    print("Modo: SANDBOX (não envia emails reais)")

    # Configura modo sandbox
    os.environ["NOTIFICAR_SANDBOX"] = "true"
    os.environ["NOTIFICAR_HABILITADO"] = "true"

    db = next(get_db())

    try:
        # Cria dados de teste
        alerta, fluxo = criar_dados_teste(db)

        # Testa execução de fluxo
        execucao_fluxo = testar_execucao_fluxo(db, alerta.id, fluxo.id)

        # Testa execução completa
        execucoes_completas = testar_execucao_completa(db, alerta.id)

        print("\n=== Resumo ===")
        print(f"Execução fluxo: {'OK' if execucao_fluxo and execucao_fluxo.sucesso else 'FALHOU'}")
        print(
            f"Execução completa: {'OK' if execucoes_completas and all(e.sucesso for e in execucoes_completas) else 'FALHOU'}"
        )

    finally:
        # Limpa dados de teste
        limpar_dados_teste(db, alerta.id)
        db.close()


if __name__ == "__main__":
    main()
