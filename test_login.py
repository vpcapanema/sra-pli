import requests
import json
from urllib.parse import urljoin

BASE_URL = "http://localhost:8001"
session = requests.Session()

# Login com o admin
login_data = {
    "email": "admin@concremat.local",
    "role": "admin",
    "password": "change-me"
}

# Fazer login
resp_login = session.post(f"{BASE_URL}/login", data=login_data)
print(f"Login status: {resp_login.status_code}")
print(f"Cookies: {session.cookies}")

# Verificar se login foi bem-sucedido (redirect)
if resp_login.history:
    print(f"Redirects: {[(r.status_code, r.url) for r in resp_login.history]}")

# Tentar acessar dashboard
resp_dash = session.get(f"{BASE_URL}/dashboard")
print(f"Dashboard status: {resp_dash.status_code}")
if resp_dash.status_code == 200:
    print("Login successful!")
else:
    print(f"Dashboard response: {resp_dash.text[:500]}")
