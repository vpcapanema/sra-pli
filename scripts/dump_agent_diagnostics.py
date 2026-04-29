#!/usr/bin/env python3
"""Gera um relatorio de lint ortografico e estatico para anexar ao agente no Cursor.

O Cursor nao expoe a aba Problemas a scripts externos. Este ficheiro reproduz no
terminal o que o projeto ja valida (flake8, pylint, djlint, cspell,
markdownlint-cli2 em `.cursor/**/*.mdc`) e escreve tudo
em artifacts/agent-diagnostics.txt — pode usar @artifacts/agent-diagnostics.txt
no chat.

Gravar buffers do editor: use Save All (Ctrl+K S) ou ative files.autoSave nas
definicoes de utilizador; nenhum script pode gravar por si os separadores abertos.

Uso (na raiz do repositorio):
  .\\.venv\\Scripts\\python.exe scripts\\dump_agent_diagnostics.py
  .\\.venv\\Scripts\\python.exe scripts\\dump_agent_diagnostics.py --paths app/routes/foo.py app/templates/bar.html
  .\\.venv\\Scripts\\python.exe scripts\\dump_agent_diagnostics.py --no-pylint
  .\\.venv\\Scripts\\python.exe scripts\\dump_agent_diagnostics.py --no-markdownlint

Saida: artifacts/agent-diagnostics.txt (cria a pasta artifacts se preciso).
Codigo de saida: 0 se todas as ferramentas passarem; 1 se alguma falhar.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _append_header(lines: list[str], title: str) -> None:
    lines.append("")
    lines.append(f"=== {title} ===")
    lines.append("")


def _run_capture(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return 1, f"(erro ao executar: {exc})\n"
    out = (proc.stdout or "") + (proc.stderr or "")
    if not out.endswith("\n") and out:
        out += "\n"
    return proc.returncode, out


def _npm_executable() -> str | None:
    if sys.platform == "win32":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which("npm")


def _git_optional(cwd: Path) -> str:
    code, out = _run_capture(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=cwd,
    )
    if code != 0:
        return ""
    sha = (out or "").strip().splitlines()
    return sha[0] if sha else ""


def _split_paths(root: Path, paths: list[str]) -> tuple[list[str], list[str]]:
    py_rel: list[str] = []
    html_rel: list[str] = []
    for raw in paths:
        p = (root / raw).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            continue
        rel = p.relative_to(root).as_posix()
        if p.suffix.lower() == ".py" and p.is_file():
            py_rel.append(rel)
        elif p.suffix.lower() in {".html", ".htm"} and p.is_file():
            html_rel.append(rel)
    return py_rel, html_rel


def _report_header_lines(root: Path) -> list[str]:
    lines = [
        "SRA — diagnostico para agente (terminal, nao e a aba Problemas do IDE)",
        f"Gerado em: {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"Repo: {root}",
    ]
    sha = _git_optional(root)
    if sha:
        lines.append(f"Git HEAD: {sha}")
    lines.append("")
    return lines


def _lint_targets(
    root: Path,
    paths: list[str],
) -> tuple[list[str], list[str], list[str], str | None]:
    if not paths:
        return ["app"], ["app"], ["app/templates"], None
    py_rel, html_rel = _split_paths(root, paths)
    warn = None
    if not py_rel and not html_rel:
        warn = (
            "Aviso: --paths nao resolveu a ficheiros .py/.html dentro do repo; "
            "corra sem --paths para varredura completa.\n"
        )
    flake8_t = py_rel if py_rel else []
    pylint_t = py_rel if py_rel else []
    djlint_t = html_rel if html_rel else []
    return flake8_t, pylint_t, djlint_t, warn


def _run_module(
    lines: list[str],
    root: Path,
    module: str,
    module_args: list[str],
    targets: list[str],
) -> bool:
    _append_header(lines, f"{module} ({' '.join(targets)})")
    code, out = _run_capture(
        [sys.executable, "-m", module, *module_args, *targets],
        cwd=root,
    )
    lines.append(out or "(sem saida)\n")
    return code == 0


def _npm_run_script(lines: list[str], root: Path, script_name: str, title: str) -> bool:
    npm = _npm_executable()
    _append_header(lines, title)
    if not npm:
        lines.append("npm nao encontrado no PATH.\n")
        return False
    code, out = _run_capture(
        [npm, "run", script_name],
        cwd=root,
        env=os.environ.copy(),
    )
    lines.append(out or "(sem saida)\n")
    return code == 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera artifacts/agent-diagnostics.txt")
    parser.add_argument(
        "--paths",
        nargs="*",
        default=[],
        metavar="PATH",
        help="Ficheiros relativos ao repo (.py e/ou .html); se omitido, corre lint completo.",
    )
    parser.add_argument("--no-pylint", action="store_true", help="Pula pylint (mais rapido).")
    parser.add_argument("--no-djlint", action="store_true", help="Pula djlint.")
    parser.add_argument("--no-spell", action="store_true", help="Pula npm run spell.")
    parser.add_argument(
        "--no-markdownlint",
        action="store_true",
        help="Pula npm run mdlint (regras .mdc em .cursor/).",
    )
    return parser.parse_args()


def main() -> int:
    root = _repo_root()
    args = _parse_args()
    out_path = root / "artifacts" / "agent-diagnostics.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = _report_header_lines(root)
    flake8_t, pylint_t, djlint_t, path_warn = _lint_targets(root, args.paths)
    if path_warn:
        lines.append(path_warn)

    ok = True
    if flake8_t:
        ok = _run_module(lines, root, "flake8", [], flake8_t) and ok
    else:
        _append_header(lines, "flake8 (omitido — sem alvos .py)")
        lines.append("")

    if args.no_pylint:
        _append_header(lines, "pylint (omitido por --no-pylint)")
        lines.append("")
    elif pylint_t:
        ok = (
            _run_module(
                lines,
                root,
                "pylint",
                ["--rcfile=pyproject.toml"],
                pylint_t,
            )
            and ok
        )
    else:
        _append_header(lines, "pylint (omitido — sem alvos .py)")
        lines.append("")

    if args.no_djlint:
        _append_header(lines, "djlint (omitido por --no-djlint)")
        lines.append("")
    elif djlint_t:
        ok = _run_module(lines, root, "djlint", [], djlint_t) and ok
    else:
        _append_header(lines, "djlint (omitido — sem alvos .html)")
        lines.append("")

    _npm_optional_sections = (
        (
            args.no_spell,
            "cspell / npm run spell (omitido por --no-spell)",
            "spell",
            "npm run spell (cspell)",
        ),
        (
            args.no_markdownlint,
            "markdownlint (omitido por --no-markdownlint)",
            "mdlint",
            "npm run mdlint (markdownlint-cli2)",
        ),
    )
    for skip, omit_header, script, title in _npm_optional_sections:
        if skip:
            _append_header(lines, omit_header)
            lines.append("")
        else:
            ok = _npm_run_script(lines, root, script, title) and ok

    lines.extend(["", "=== fim ===", ""])
    text = "\n".join(lines)
    out_path.write_text(text, encoding="utf-8")
    print(f"Escrito: {out_path.relative_to(root)} ({len(text)} caracteres)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
