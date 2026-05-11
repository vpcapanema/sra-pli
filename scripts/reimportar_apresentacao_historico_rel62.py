"""Reimporta seções 1 (Apresentação) e 2 (Histórico do Contrato) do rel. 62.

Lê a referência ``relatorios_entregues/D20-13 - R00 1.docx`` via
``docx_clone_extractor`` (que já emite rich HTML preservando negrito,
alinhamento e o callout ``.sra-docx-callout``), e reescreve os blocos
correspondentes no relatório 62 no banco.

Operação destrutiva controlada: apenas blocos das seções "1" e "2" do
relatório 62 são substituídos. Demais seções ficam intactas.
"""

from __future__ import annotations

from app.db import SessionLocal
from app.docx_clone_extractor import extrair_relatorio_docx_disponivel
from app.models import Bloco, Secao
from app.services.relatorios import _conteudo_apresentacao_clone

ARQUIVO_REF = "D20-13 - R00 1.docx"
REL_ID = 62
SECOES_ALVO = ("1", "2")


def main() -> None:
    secoes_ref = {
        (sec.get("secao_numero") or "").strip(): sec for sec in extrair_relatorio_docx_disponivel(ARQUIVO_REF)
    }
    db = SessionLocal()
    try:
        from app.models import Relatorio

        rel = db.get(Relatorio, REL_ID)
        if rel is None:
            raise SystemExit(f"Relatório {REL_ID} não encontrado.")
        for numero in SECOES_ALVO:
            sec = db.query(Secao).filter(Secao.relatorio_id == REL_ID, Secao.numero == numero).one_or_none()
            if sec is None:
                print(f"[skip] seção {numero} não existe no rel {REL_ID}")
                continue

            db.query(Bloco).filter(Bloco.secao_id == sec.id).delete(synchronize_session=False)
            db.flush()

            if numero == "1":
                conteudo = _conteudo_apresentacao_clone(rel)
                db.add(
                    Bloco(
                        secao_id=sec.id,
                        tipo="texto",
                        ordem=0,
                        conteudo=conteudo,
                        origem="clone_canonico",
                    )
                )
                print("[ok] seção 1: aplicado conteúdo canônico (rich HTML + callout)")
                continue

            ref_sec = secoes_ref.get(numero)
            if not ref_sec:
                print(f"[warn] referência não tem seção {numero}")
                continue
            blocos_ref = ref_sec.get("blocos") or []
            ordem = 0
            for b in blocos_ref:
                tipo = b.get("tipo") or "texto"
                if tipo == "figura":
                    continue
                conteudo = b.get("conteudo") or ""
                if not conteudo.strip():
                    continue
                db.add(
                    Bloco(
                        secao_id=sec.id,
                        tipo=tipo,
                        ordem=ordem,
                        conteudo=conteudo,
                        legenda=(b.get("legenda") or None),
                        fonte=(b.get("fonte") or None),
                        origem="docx_import",
                    )
                )
                ordem += 1
            print(f"[ok] seção {numero}: {ordem} blocos reimportados de {ARQUIVO_REF}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
