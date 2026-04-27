"""
Atualiza o sqltools.connections do Cursor a partir de .env (DATABASE_URL) e
do URL local documentado no README. Grava em %APPDATA%\\Cursor\\User\\settings.json
(nada de segredos no .vscode versionado). Requer: pip install -r requirements.txt
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import json5
except ImportError:  # pragma: no cover
    print("Instale: .venv\\Scripts\\pip install json5", file=sys.stderr)
    sys.exit(1)

LOCAL_CONNECT = {
    "name": "SRA Postgres local (Docker, README)",
    "driver": "PostgreSQL",
    "connectString": "postgresql://postgres:sra@localhost:5432/sra",
    "askForPassword": False,
    "connectionTimeout": 20,
}
REMOTE_NAME = "SRA (DATABASE_URL do .env)"


def _load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _to_sqltools_postgres_uri(django_style: str) -> str:
    s = django_style.strip()
    if s.startswith("postgres://"):
        s = "postgresql://" + s[len("postgres://") :]
    elif s.startswith("postgresql+psycopg2://"):
        s = "postgresql://" + s[len("postgresql+psycopg2://") :]
    elif s.startswith("postgresql://"):
        pass
    else:
        msg = f"So Postgres. Recebido: {s[:30]!r}..."
        raise ValueError(msg)
    if "://" not in s:
        raise ValueError("URL invalida")
    return s


def _cursor_user_settings() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("APPDATA nao definido (esperado no Windows).", file=sys.stderr)
        sys.exit(1)
    return Path(appdata) / "Cursor" / "User" / "settings.json"


def _merge_sqltools(connections: list) -> None:
    path = _cursor_user_settings()
    if not path.exists():
        data: dict = {}
    else:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json5.loads(raw)
        except (OSError, ValueError) as e:
            print(f"Falha ao ler {path}: {e}", file=sys.stderr)
            sys.exit(1)
    if not isinstance(data, dict):
        data = {}
    data["sqltools.connections"] = connections
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    print(f"Atualizado: {path}")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    connections: list[dict] = [dict(LOCAL_CONNECT)]
    if env_path.is_file():
        try:
            env = _load_env(env_path)
        except (OSError, ValueError) as e:
            print(f"Aviso: nao li .env: {e}", file=sys.stderr)
        else:
            url = env.get("DATABASE_URL", "").strip()
            if url:
                try:
                    connect_string = _to_sqltools_postgres_uri(url)
                except ValueError as e:
                    print(f"Aviso: DATABASE_URL ignorado: {e}", file=sys.stderr)
                else:
                    remote: dict = {
                        "name": REMOTE_NAME,
                        "driver": "PostgreSQL",
                        "connectString": connect_string,
                        "askForPassword": False,
                        "connectionTimeout": 20,
                    }
                    if "render.com" in connect_string or "sslmode=require" in connect_string:
                        remote["pgOptions"] = {
                            "ssl": {
                                "rejectUnauthorized": True,
                            },
                        }
                    connections.append(remote)
    _merge_sqltools(connections)
    print(
        "Reinicie ou recarregue o Cursor: Ctrl+Shift+P > Developer: Reload Window. "
        "As ligacoes aparecem em SQLTools > Connections (Explorador)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
