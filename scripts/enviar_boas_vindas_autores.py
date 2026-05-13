"""Envia email de boas-vindas para todos os autores cadastrados.

Uso:
    python scripts/enviar_boas_vindas_autores.py [--dry-run] [--tutorial-url URL]

Opcoes:
    --dry-run: Simula o envio sem enviar de fato (modo sandbox)
    --tutorial-url: URL da pagina de tutorial (opcional)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Forcar modo sandbox se --dry-run
if "--dry-run" in sys.argv:
    os.environ["NOTIFICAR_SANDBOX"] = "true"

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.notificacoes.email_sender import (  # noqa: E402
    enviar_notificacao,
    modo_atual,
)
from app.config import settings  # noqa: E402


# Mapeamento de senhas iniciais (do arquivo senhas_autores.txt)
SENHAS_INICIAIS = {
    "andre.fernando@concremat-transplan.com.br": ",::W}x+93iL0",
    "cristina.ikonomidis@concremat-transplan.com.br": "38iTA67P{0DQ",
    "joseane.queiroz@concremat-transplan.com.br": "3)\"r[VBqLjvU",
    "karin.bilt@concremat-transplan.com.br": "I{T'%<Ypzwdc",
    "silvio.ichihara@concremat-transplan.com.br": "6@PUe6okY:ld",
    "vitor.porto@concremat-transplan.com.br": "i9`1:OIa!J>v",
}


def _contexto_boas_vindas(user: User, tutorial_url: str | None) -> dict:
    """Monta o contexto para o email de boas-vindas."""
    base_url = settings.APP_BASE_URL
    senha = SENHAS_INICIAIS.get(user.email, "*** SENHA NAO ENCONTRADA ***")
    
    ctx = {
        "destinatario_nome": user.nome,
        "destinatario_email": user.email,
        "link_login_sra": f"{base_url}/login",
        "link_modelos_word_ajuda": f"{base_url}/modelos-word-importacao",
        "link_painel_upload": f"{base_url}/painel-upload",
        "senha_inicial": senha,
    }
    
    if tutorial_url:
        ctx["link_tutorial"] = tutorial_url
    
    return ctx


def main() -> int:
    p = argparse.ArgumentParser(
        description="Envia email de boas-vindas para todos os autores"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula o envio sem enviar de fato (modo sandbox)",
    )
    p.add_argument(
        "--tutorial-url",
        help="URL da pagina de tutorial (opcional)",
    )
    args = p.parse_args()

    print("=" * 80)
    print("ENVIO DE EMAIL DE BOAS-VINDAS PARA AUTORES")
    print(f"Modo: {modo_atual()}")
    if args.tutorial_url:
        print(f"Tutorial URL: {args.tutorial_url}")
    print("=" * 80)
    print()

    db = SessionLocal()
    try:
        # Buscar todos os usuarios com role 'autor'
        autores = db.query(User).filter(User.role == "autor").all()
        
        if not autores:
            print("[AVISO] Nenhum autor encontrado no banco de dados.")
            return 0
        
        print(f"Encontrados {len(autores)} autores cadastrados:")
        for autor in autores:
            print(f"  - {autor.nome} <{autor.email}>")
        print()
        
        if args.dry_run:
            print("[DRY-RUN] Modo simulacao ativado. Nenhum email sera enviado de fato.")
            print()
        else:
            confirmacao = input("Deseja prosseguir com o envio? (sim/nao): ").strip().lower()
            if confirmacao not in ("sim", "s", "yes", "y"):
                print("Envio cancelado pelo usuario.")
                return 0
            print()
        
        sucessos = 0
        falhas = 0
        
        for autor in autores:
            print(f"[{autor.email}] Enviando...")
            
            # Verificar se temos a senha inicial
            if autor.email not in SENHAS_INICIAIS:
                print(f"  [AVISO] Senha inicial nao encontrada para {autor.email}")
                print(f"  Pulando envio para este usuario.")
                falhas += 1
                continue
            
            contexto = _contexto_boas_vindas(autor, args.tutorial_url)
            res = enviar_notificacao(
                destinatario_email=autor.email,
                destinatario_nome=autor.nome,
                tipo="boas_vindas",
                contexto=contexto,
            )
            
            if res.sucesso:
                print(f"  [OK] Enviado | message_id={res.message_id}")
                sucessos += 1
            else:
                print(f"  [FALHA] {res.erro}")
                falhas += 1
            print()
        
        print("=" * 80)
        print("RESUMO")
        print("=" * 80)
        print(f"Total de autores: {len(autores)}")
        print(f"Enviados com sucesso: {sucessos}")
        print(f"Falhas: {falhas}")
        
        if falhas > 0:
            return 1
        
        print()
        print("[OK] Todos os emails foram enviados com sucesso!")
        return 0
        
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
