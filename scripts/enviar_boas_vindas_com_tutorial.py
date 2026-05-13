"""Gera PDF do tutorial e envia email de boas-vindas com anexo para todos os autores.

Uso:
    python scripts/enviar_boas_vindas_com_tutorial.py [--dry-run]
"""
from __future__ import annotations

import argparse
import base64
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
from app.config import settings  # noqa: E402
from sendgrid.helpers.mail import (  # noqa: E402
    Attachment,
    FileContent,
    FileName,
    FileType,
    Disposition,
)

# Importar funcoes de email
import logging  # noqa: E402
import uuid  # noqa: E402
from jinja2 import Environment, FileSystemLoader  # noqa: E402
from sendgrid import SendGridAPIClient  # noqa: E402
from sendgrid.helpers.mail import Mail, Email, To, Content  # noqa: E402

log = logging.getLogger(__name__)

# Mapeamento de senhas iniciais
SENHAS_INICIAIS = {
    "andre.fernando@concremat-transplan.com.br": ",::W}x+93iL0",
    "cristina.ikonomidis@concremat-transplan.com.br": "38iTA67P{0DQ",
    "joseane.queiroz@concremat-transplan.com.br": "3)\"r[VBqLjvU",
    "karin.bilt@concremat-transplan.com.br": "I{T'%<Ypzwdc",
    "silvio.ichihara@concremat-transplan.com.br": "6@PUe6okY:ld",
    "vitor.porto@concremat-transplan.com.br": "i9`1:OIa!J>v",
}


def gerar_pdf_tutorial() -> bytes:
    """Gera PDF do tutorial usando markdown2pdf ou reportlab."""
    tutorial_md = ROOT / "docs" / "TUTORIAL_AUTOR.md"
    
    try:
        # Tentar usar markdown-pdf (precisa ter instalado)
        import markdown  # noqa: PLC0415
        from weasyprint import HTML, CSS  # noqa: PLC0415
        
        # Ler markdown
        with open(tutorial_md, "r", encoding="utf-8") as f:
            md_content = f.read()
        
        # Converter para HTML
        html_content = markdown.markdown(
            md_content,
            extensions=["tables", "fenced_code", "toc"]
        )
        
        # Template HTML com estilo
        html_template = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Tutorial do Autor - Sistema SRA</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm;
            @bottom-right {{
                content: "Pagina " counter(page) " de " counter(pages);
                font-size: 9pt;
                color: #666;
            }}
        }}
        body {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #1a1a2e;
        }}
        h1 {{
            color: #1c3d59;
            font-size: 20pt;
            border-bottom: 3px solid #3ec26e;
            padding-bottom: 8px;
            margin-top: 24px;
        }}
        h2 {{
            color: #1c3d59;
            font-size: 16pt;
            margin-top: 20px;
            border-bottom: 1px solid #d5dce6;
            padding-bottom: 4px;
        }}
        h3 {{
            color: #2a5a7a;
            font-size: 13pt;
            margin-top: 16px;
        }}
        code {{
            background: #f5f7fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 10pt;
        }}
        pre {{
            background: #f5f7fa;
            padding: 12px;
            border-left: 4px solid #3ec26e;
            overflow-x: auto;
            font-size: 9pt;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 12px 0;
            font-size: 10pt;
        }}
        th, td {{
            border: 1px solid #d5dce6;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background: #1c3d59;
            color: white;
            font-weight: bold;
        }}
        blockquote {{
            border-left: 4px solid #3ec26e;
            padding-left: 12px;
            margin-left: 0;
            color: #2a5a7a;
            font-style: italic;
        }}
        .cover {{
            text-align: center;
            padding: 100px 0;
        }}
        .cover h1 {{
            font-size: 28pt;
            border: none;
        }}
        .cover p {{
            font-size: 14pt;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="cover">
        <h1>Tutorial do Autor</h1>
        <p>Sistema de Relatorios de Atividades (SRA)</p>
        <p>PLI/SP-2050 - Consorcio Concremat-Transplan</p>
        <p style="margin-top: 40px; font-size: 12pt;">Versao 1.0 - Abril/2026</p>
    </div>
    <div style="page-break-after: always;"></div>
    {html_content}
</body>
</html>
"""
        
        # Gerar PDF
        pdf_bytes = HTML(string=html_template).write_pdf()
        return pdf_bytes
        
    except ImportError:
        print("[AVISO] weasyprint nao instalado. Gerando PDF simples com reportlab...")
        # Fallback: PDF simples com reportlab
        from reportlab.lib.pagesizes import A4  # noqa: PLC0415
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # noqa: PLC0415
        from reportlab.lib.units import cm  # noqa: PLC0415
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak  # noqa: PLC0415
        from io import BytesIO  # noqa: PLC0415
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []
        
        # Capa
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='#1c3d59',
            spaceAfter=30,
            alignment=1  # Center
        )
        story.append(Spacer(1, 3*cm))
        story.append(Paragraph("Tutorial do Autor", title_style))
        story.append(Paragraph("Sistema de Relatorios de Atividades (SRA)", styles['Normal']))
        story.append(Paragraph("PLI/SP-2050", styles['Normal']))
        story.append(PageBreak())
        
        # Conteudo simplificado
        with open(tutorial_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    story.append(Spacer(1, 0.3*cm))
                elif line.startswith("# "):
                    story.append(Paragraph(line[2:], styles['Heading1']))
                elif line.startswith("## "):
                    story.append(Paragraph(line[3:], styles['Heading2']))
                elif line.startswith("### "):
                    story.append(Paragraph(line[4:], styles['Heading3']))
                else:
                    story.append(Paragraph(line, styles['Normal']))
        
        doc.build(story)
        return buffer.getvalue()


def enviar_email_com_anexo(
    destinatario_email: str,
    destinatario_nome: str,
    senha_inicial: str,
    pdf_bytes: bytes,
    modo_sandbox: bool = False
) -> tuple[bool, str | None, str | None]:
    """Envia email de boas-vindas com PDF anexo."""
    base_url = settings.APP_BASE_URL
    
    # Renderizar template
    templates_dir = ROOT / "app" / "notificacoes" / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    
    contexto = {
        "destinatario_nome": destinatario_nome,
        "destinatario_email": destinatario_email,
        "senha_inicial": senha_inicial,
        "link_login_sra": f"{base_url}/login",
        "link_modelos_word_ajuda": f"{base_url}/modelos-word-importacao",
        "link_painel_upload": f"{base_url}/painel-upload",
    }
    
    html = env.get_template("email_boas_vindas.html").render(**contexto)
    texto = env.get_template("email_boas_vindas.txt").render(**contexto)
    
    if modo_sandbox:
        message_id = f"sandbox-{uuid.uuid4()}"
        log.info(f"[sandbox] Email para {destinatario_email} com anexo tutorial.pdf")
        return True, message_id, None
    
    # Enviar via SendGrid
    try:
        message = Mail(
            from_email=Email(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
            to_emails=To(destinatario_email, destinatario_nome),
            subject="[SRA] Bem-vindo ao Sistema de Relatorios de Atividades",
        )
        message.add_content(Content("text/plain", texto))
        message.add_content(Content("text/html", html))
        
        # Adicionar anexo PDF
        encoded_pdf = base64.b64encode(pdf_bytes).decode()
        attachment = Attachment(
            FileContent(encoded_pdf),
            FileName("Tutorial_Autor_SRA.pdf"),
            FileType("application/pdf"),
            Disposition("attachment")
        )
        message.add_attachment(attachment)
        
        client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = client.send(message)
        
        message_id = response.headers.get("X-Message-Id")
        if 200 <= response.status_code < 300:
            return True, message_id, None
        return False, message_id, f"status={response.status_code}"
        
    except Exception as exc:
        return False, None, str(exc)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Envia email de boas-vindas com tutorial em PDF para todos os autores"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula o envio sem enviar de fato",
    )
    args = p.parse_args()

    print("=" * 80)
    print("ENVIO DE EMAIL DE BOAS-VINDAS COM TUTORIAL (PDF)")
    print(f"Modo: {'sandbox' if args.dry_run else 'real'}")
    print("=" * 80)
    print()

    # Gerar PDF
    print("[1/3] Gerando PDF do tutorial...")
    try:
        pdf_bytes = gerar_pdf_tutorial()
        print(f"  [OK] PDF gerado: {len(pdf_bytes)} bytes")
    except Exception as exc:
        print(f"  [ERRO] Falha ao gerar PDF: {exc}")
        return 1
    print()

    # Buscar autores
    print("[2/3] Buscando autores no banco de dados...")
    db = SessionLocal()
    try:
        autores = db.query(User).filter(User.role == "autor").all()
        
        if not autores:
            print("[AVISO] Nenhum autor encontrado.")
            return 0
        
        print(f"  Encontrados {len(autores)} autores:")
        for autor in autores:
            senha = SENHAS_INICIAIS.get(autor.email, "*** CONTATE O COORDENADOR ***")
            status = 'OK' if autor.email in SENHAS_INICIAIS else 'PLACEHOLDER'
            print(f"    - {autor.nome} <{autor.email}> [senha: {status}]")
        print()
        
        if not args.dry_run:
            confirmacao = input("Deseja prosseguir com o envio? (sim/nao): ").strip().lower()
            if confirmacao not in ("sim", "s", "yes", "y"):
                print("Envio cancelado.")
                return 0
            print()
        
        # Enviar emails
        print("[3/3] Enviando emails...")
        sucessos = 0
        falhas = 0
        
        for autor in autores:
            senha = SENHAS_INICIAIS.get(autor.email, "*** CONTATE O COORDENADOR ***")
            
            print(f"  [{autor.email}] Enviando...")
            sucesso, msg_id, erro = enviar_email_com_anexo(
                autor.email,
                autor.nome,
                senha,
                pdf_bytes,
                args.dry_run
            )
            
            if sucesso:
                print(f"    [OK] message_id={msg_id}")
                sucessos += 1
            else:
                print(f"    [FALHA] {erro}")
                falhas += 1
        
        print()
        print("=" * 80)
        print("RESUMO")
        print("=" * 80)
        print(f"Total: {len(autores)}")
        print(f"Enviados: {sucessos}")
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
