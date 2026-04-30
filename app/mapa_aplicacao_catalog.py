"""Metadados das páginas HTML em ``templates/complementos`` (mapa da aplicação)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaginaComplementoMeta:
    """Descrição de uma página servida a partir de ``complementos/*.html``."""

    arquivo: str
    nome_exibicao: str
    href_exemplo: str
    restricao: str
    rotas_resumo: str


PAGINAS_COMPLEMENTOS: tuple[PaginaComplementoMeta, ...] = (
    PaginaComplementoMeta(
        "login.html",
        "Login",
        "/login",
        "Público",
        "GET /login · POST /login",
    ),
    PaginaComplementoMeta(
        "dashboard.html",
        "Dashboard (relatórios)",
        "/dashboard",
        "Sessão; autores são desviados para o hub do relatório",
        "GET /dashboard",
    ),
    PaginaComplementoMeta(
        "relatorio_detail.html",
        "Sumário do relatório",
        "/relatorios/1",
        "Sessão",
        "GET /relatorios/{rel_id}",
    ),
    PaginaComplementoMeta(
        "secao_edit_conteudo_upload.html",
        "Gestão da secção e upload",
        "/relatorios/1/secoes/1/upload-conteudo",
        "Sessão; responsável da secção; guarda de rotas para perfil autor",
        "GET /relatorios/{rel_id}/secoes/{sec_id}/upload-conteudo",
    ),
    PaginaComplementoMeta(
        "modelos_word_importacao.html",
        "Modelos Word (.dotx)",
        "/modelos-word-importacao",
        "Sessão; conjunto de URLs permitidas para autor",
        "GET /modelos-word-importacao · GET …/baixar/{arquivo}",
    ),
    PaginaComplementoMeta(
        "usuarios.html",
        "Utilizadores",
        "/usuarios",
        "Sessão; admin e coordenador",
        "GET /usuarios · POST /usuarios",
    ),
    PaginaComplementoMeta(
        "usuario_edit.html",
        "Editar utilizador",
        "/usuarios/1/editar",
        "Sessão; regras em ``pode_editar_perfil_usuario``",
        "GET/POST /usuarios/{user_id}/editar",
    ),
    PaginaComplementoMeta(
        "governanca_relatorio.html",
        "Governança do relatório",
        "/governanca-relatorio",
        "Sessão; admin e coordenador",
        "GET /governanca-relatorio · POST …/parametros-ciclo, …/entrega/{id}, …/notificacao/{id}, …/usuario/{id}",
    ),
    PaginaComplementoMeta(
        "entregas_painel.html",
        "Painel de entregas",
        "/relatorios/1/entregas",
        "Sessão; coord/admin veem todos; autor só a sua entrega",
        "GET /relatorios/{rel_id}/entregas",
    ),
    PaginaComplementoMeta(
        "recuperar_senha.html",
        "Recuperar senha",
        "/recuperar-senha",
        "Público (POST usa cookie de sessão para o passo seguinte)",
        "GET/POST /recuperar-senha",
    ),
    PaginaComplementoMeta(
        "recuperar_senha_definir.html",
        "Definir nova senha",
        "/recuperar-senha/definir",
        "Público com sessão de recuperação válida (timeout)",
        "GET/POST /recuperar-senha/definir",
    ),
    PaginaComplementoMeta(
        "dev_modais.html",
        "Pré-visualização de modais (desenvolvimento)",
        "/dev/modais",
        "Sessão e ``modais_preview_allowed()`` (dev / SRA_MODAL_PREVIEW)",
        "GET /dev/modais",
    ),
)


def meta_por_arquivo() -> dict[str, PaginaComplementoMeta]:
    return {p.arquivo: p for p in PAGINAS_COMPLEMENTOS}
