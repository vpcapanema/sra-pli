import bcrypt
import re
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from .db import get_db
from .models import User


# Padrão estilo "Vinicius do Prado Capanema":
# cada palavra começa com maiúscula seguida de minúsculas (acentos permitidos),
# exceto partículas (do/da/de/dos/das/du/e/di/del/la/von/van) que ficam em minúsculas.
# Mínimo de 2 palavras.
_PARTICULAS = {"do", "da", "de", "dos", "das", "du", "e", "di", "del", "la", "von", "van"}
_NOME_PALAVRA_RE = re.compile(r"^[A-ZÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ][a-záàâãäéèêëíìîïóòôõöúùûüçñ]+$")


def formatar_nome_pessoa(raw: str) -> str:
    """Normaliza um nome para o padrão 'Vinicius do Prado Capanema'.

    Remove espaços extras, capitaliza cada palavra e mantém partículas em
    minúsculas (exceto se forem a primeira palavra). Lança ValueError se o
    resultado não obedecer ao padrão (mín. 2 palavras, sem números/símbolos).
    """
    if not raw:
        raise ValueError("Nome vazio.")
    palavras = [p for p in re.split(r"\s+", raw.strip()) if p]
    if len(palavras) < 2:
        raise ValueError("Informe nome e sobrenome.")
    out: list[str] = []
    for i, p in enumerate(palavras):
        baixa = p.lower()
        if i > 0 and baixa in _PARTICULAS:
            out.append(baixa)
        else:
            out.append(baixa[:1].upper() + baixa[1:])
    for w in out:
        if w in _PARTICULAS:
            continue
        if not _NOME_PALAVRA_RE.match(w):
            raise ValueError(
                "Nome inválido. Use apenas letras (ex.: 'Vinicius do Prado Capanema')."
            )
    return " ".join(out)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("user_id")
    if not uid:
        return None
    return db.get(User, uid)


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Para rotas que renderizam HTML/redirecionam: 303 -> /login."""
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_user_api(request: Request, db: Session = Depends(get_db)) -> User:
    """Para endpoints JSON (fetch/XHR): 401 com detalhe — o cliente deve
    interpretar e redirecionar manualmente para /login. Evita o pitfall do
    `fetch` seguir um 303 para a página HTML do login (e quebrar o JSON.parse).
    """
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(status_code=403, detail="Acesso restrito a coordenadores/admin")
    return user
