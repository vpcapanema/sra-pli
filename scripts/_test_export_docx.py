"""Testa novo endpoint docx_export."""

import base64
import json
import requests
from itsdangerous import TimestampSigner
from app.config import settings
from app.db import SessionLocal
from app.models import User, Relatorio


def admin_session_cookie() -> str:
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.role == "admin").first()
    finally:
        db.close()
    if u is None:
        raise SystemExit("Sem admin no DB.")
    payload = {"user_id": u.id, "user_role": "admin"}
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    signer = TimestampSigner(settings.SECRET_KEY)
    return signer.sign(data).decode()


# Busca relatório válido
db = SessionLocal()
try:
    rel = db.query(Relatorio).first()
    rel_id = rel.id if rel else None
    print(f"Relatório ID: {rel_id}")
finally:
    db.close()

if not rel_id:
    raise SystemExit("Nenhum relatório encontrado.")

cookie_value = admin_session_cookie()
session = requests.Session()
session.cookies.set("session", cookie_value, domain="127.0.0.1")

print("Testando autenticação com /dashboard...")
resp = session.get("http://127.0.0.1:8001/dashboard", timeout=10)
print(f"Dashboard status: {resp.status_code}")

if resp.status_code == 200:
    print("Autenticação OK. Testando novo endpoint /docx_export...")
    response = session.get(
        f"http://127.0.0.1:8001/relatorios/{rel_id}/docx_export",
        timeout=300,  # 5 minutos
    )
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    if response.status_code == 200 and "wordprocessingml" in response.headers.get("content-type", ""):
        print("Exportação DOCX via novo endpoint funcionou!")
    else:
        print(f"Body (primeiros 500 chars): {response.text[:500]}")
else:
    print("Autenticação falhou")
