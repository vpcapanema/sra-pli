"""Teste completo de todos os tipos de email do sistema.

Envia todos os tipos de notificacao configurados para um destinatario especifico.

Uso:
    python scripts/teste_todos_emails.py destino@exemplo.com
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.notificacoes.email_sender import (  # noqa: E402
    enviar_notificacao,
    modo_atual,
)
from app.notificacoes.email_context_arvore import (  # noqa: E402
    format_arvore_secoes_email_plaintext,
)


def _contexto_base(destinatario_nome: str) -> dict:
    """Contexto comum para todos os tipos de email."""
    base_url = "https://sra-pli-starter.onrender.com"
    arvore = [
        {
            "numero": "4.1",
            "titulo": "Coordenação",
            "link_upload": f"{base_url}/relatorios/1/secoes/10/upload-conteudo",
            "link_dotx": f"{base_url}/relatorios/1/secoes/10/modelo.dotx",
            "filhos": [],
        },
        {
            "numero": "4.4.1",
            "titulo": "Acompanhamento técnico em reuniões",
            "link_upload": f"{base_url}/relatorios/1/secoes/15/upload-conteudo",
            "link_dotx": f"{base_url}/relatorios/1/secoes/15/modelo.dotx",
            "filhos": [],
        },
    ]
    return {
        "destinatario_nome": destinatario_nome,
        "relatorio_codigo": "D20-14",
        "mes_referencia": "Abril/2026",
        "prazo_envio": "10/05/2026 23:59",
        "prazo_limite_conteudo_autor": "08/05/2026 23:59",
        "link_relatorio_painel": f"{base_url}/relatorios/1",
        "link_modelos_word_ajuda": f"{base_url}/modelos-word-importacao",
        "link_login_sra": f"{base_url}/login",
        "link_painel_upload": f"{base_url}/painel-upload",
        "arvore_secoes_links": arvore,
        "arvore_modelos_dotx_texto": format_arvore_secoes_email_plaintext(
            arvore, apenas_dotx=True
        ),
        "minhas_secoes": [
            {
                "numero": "4.1",
                "titulo": "Coordenação",
                "contexto": "4 - Atividades do Período",
                "link_upload": f"{base_url}/relatorios/1/secoes/10/upload-conteudo",
                "link_dotx": f"{base_url}/relatorios/1/secoes/10/modelo.dotx",
            },
        ],
    }


def _contexto_boas_vindas(destinatario_nome: str) -> dict:
    """Contexto específico para email de boas-vindas."""
    base_url = "https://sra-pli-starter.onrender.com"
    return {
        "destinatario_nome": destinatario_nome,
        "destinatario_email": "vinicius.capanema@concremat-transplan.com.br",
        "link_login_sra": f"{base_url}/login",
        "link_modelos_word_ajuda": f"{base_url}/modelos-word-importacao",
        "link_painel_upload": f"{base_url}/painel-upload",
        "senha_inicial": "SRA2026!temp",
    }


def _contexto_customizado(destinatario_nome: str) -> dict:
    """Contexto específico para email customizado."""
    base_url = "https://sra-pli-starter.onrender.com"
    return {
        "destinatario_nome": destinatario_nome,
        "assunto": "Teste de email customizado",
        "corpo_mensagem": "<p>Esta é uma <strong>mensagem customizada</strong> de teste do sistema SRA.</p><p>Pode conter formatação HTML.</p>",
        "link_login_sra": f"{base_url}/login",
        "link_relatorio_painel": f"{base_url}/relatorios/1",
    }


TIPOS_EMAIL = {
    "abertura": ("Abertura de período", _contexto_base),
    "lembrete": ("Lembrete (D-5)", _contexto_base),
    "ultima_chamada": ("Última chamada (D-2)", _contexto_base),
    "manual": ("Notificação manual", _contexto_base),
    "defcon_nivel1": ("DEFCON Nível 1 (prazo encerrado)", _contexto_base),
    "defcon_nivel2": ("DEFCON Nível 2 (entrega atrasada)", _contexto_base),
    "boas_vindas": ("Boas-vindas", _contexto_boas_vindas),
    "customizado": ("Email customizado", _contexto_customizado),
}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Teste completo de todos os tipos de email do sistema"
    )
    p.add_argument("destinatario", help="Email de destino")
    p.add_argument(
        "--nome",
        default="Vinícius Capanema",
        help="Nome do destinatário (default: Vinícius Capanema)",
    )
    args = p.parse_args()

    print("=" * 80)
    print(f"TESTE DE ENVIO DE EMAILS - SRA")
    print(f"Destinatário: {args.nome} <{args.destinatario}>")
    print(f"Modo atual: {modo_atual()}")
    print("=" * 80)
    print()

    resultados = []
    for tipo, (descricao, contexto_fn) in TIPOS_EMAIL.items():
        print(f"[{tipo}] {descricao}...")
        contexto = contexto_fn(args.nome)
        res = enviar_notificacao(
            destinatario_email=args.destinatario,
            destinatario_nome=args.nome,
            tipo=tipo,
            contexto=contexto,
        )
        
        status = "[OK]" if res.sucesso else "[FALHA]"
        print(f"  {status} | modo={res.modo} | message_id={res.message_id}")
        if res.erro:
            print(f"  Erro: {res.erro}")
        print()
        
        resultados.append((tipo, descricao, res))

    print("=" * 80)
    print("RESUMO")
    print("=" * 80)
    sucessos = sum(1 for _, _, r in resultados if r.sucesso)
    falhas = sum(1 for _, _, r in resultados if not r.sucesso)
    print(f"Total: {len(resultados)} emails")
    print(f"Sucessos: {sucessos}")
    print(f"Falhas: {falhas}")
    print()

    if falhas > 0:
        print("Emails com falha:")
        for tipo, descricao, res in resultados:
            if not res.sucesso:
                print(f"  - [{tipo}] {descricao}: {res.erro}")
        return 1

    print("[OK] Todos os emails foram enviados com sucesso!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
