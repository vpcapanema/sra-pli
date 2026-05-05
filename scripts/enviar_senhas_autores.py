"""Envia emails com novas senhas para todos os autores."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal
from app.models import User
from app.notificacoes.email_sender import _enviar_real

# Senhas geradas anteriormente
senhas = {
    "andre.fernando@concremat-transplan.com.br": ",::W}x+93iL0",
    "cristina.ikonomidis@concremat-transplan.com.br": "38iTA67P{0DQ",
    "joseane.queiroz@concremat-transplan.com.br": '3)"r[VBqLjvU',
    "karin.bilt@concremat-transplan.com.br": "I{T'%<Ypzwdc",
    "silvio.ichihara@concremat-transplan.com.br": "6@PUe6okY:ld",
    "vitor.porto@concremat-transplan.com.br": "i9`1:OIa!J>v",
    "vinicius.capanema@concremat-transplan.com.br": "K`_*EG`LYQvy",
}

db = SessionLocal()

print("Enviando emails com novas senhas:")
print("=" * 70)

autores = db.query(User).filter(User.role == "autor").all()

for u in autores:
    senha = senhas.get(u.email)
    if not senha:
        print(f"ERRO: Senha não encontrada para {u.email}")
        continue

    html = f"""
<h2>Acesso ao Sistema de Relatórios de Atividades - SRA</h2>

<p>Olá {u.nome},</p>

<p>Informamos que a partir de agora utilizaremos o Sistema de Relatórios de Atividades (SRA) para o envio das atividades por e-mail.</p>

<p><strong>Dados de acesso:</strong></p>
<ul>
  <li>Usuário: {u.email}</li>
  <li>Senha: {senha}</li>
</ul>

<p><strong>Link de acesso:</strong></p>
<p><a href="https://sra-pli-starter.onrender.com/login">https://sra-pli-starter.onrender.com/login</a></p>

<p><strong>Instruções importantes:</strong></p>
<ul>
  <li>Ao fazer o primeiro acesso, por favor altere sua senha para uma senha pessoal de sua preferência.</li>
  <li>Utilize o sistema para enviar suas atividades conforme os prazos estabelecidos.</li>
</ul>

<p>Em caso de dúvidas, entre em contato com a coordenação.</p>

<p>Atenciosamente,<br>Coordenação SRA - PLI-SP</p>
    """

    texto = f"""
Acesso ao Sistema de Relatórios de Atividades - SRA

Olá {u.nome},

Informamos que a partir de agora utilizaremos o Sistema de Relatórios de Atividades (SRA) para o envio das atividades por e-mail.

Dados de acesso:
Usuário: {u.email}
Senha: {senha}

Link de acesso:
https://sra-pli-starter.onrender.com/login

Instruções importantes:
- Ao fazer o primeiro acesso, por favor altere sua senha para uma senha pessoal de sua preferência.
- Utilize o sistema para enviar suas atividades conforme os prazos estabelecidos.

Em caso de dúvidas, entre em contato com a coordenação.

Atenciosamente,
Coordenação SRA - PLI-SP
    """

    resultado = _enviar_real(
        {
            "destinatario_email": u.email,
            "destinatario_nome": u.nome,
            "assunto": "Acesso ao Sistema de Relatórios de Atividades - SRA",
            "html": html,
            "texto": texto,
            "tipo": "manual",
        }
    )

    status = "✓" if resultado.sucesso else "✗"
    print(f"{status} {u.nome} ({u.email})")
    if not resultado.sucesso:
        print(f"   Erro: {resultado.erro}")

db.close()
print()
print("Envio concluído.")
