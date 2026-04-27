"""Textos padrão para o modal de confirmação (complemento), servidos em JSON."""

from __future__ import annotations

from typing import Any, TypedDict


class ConfirmacaoUI(TypedDict, total=False):
    """Payload do endpoint GET /processos/fluxo-confirmacao/{chave}."""

    title: str
    lead: str
    detail: str
    ask: str
    show_detail: bool


# Chaves alinhadas a process_key / ações (quando existir) para rastreio.
FLUXO_CONFIRMACAO: dict[str, ConfirmacaoUI] = {
    "importacao_assistida_analise": {
        "title": "Confirmar análise assistida",
        "lead": (
            "O ficheiro TXT ou DOCX é analisado; os blocos propostos serão exibidos para revisão. "
            "Nada é gravado no relatório neste passo."
        ),
        "detail": (
            "A duração depende do tamanho do documento (típico: segundos a cerca de um minuto). "
            "Mantém-se a sessão; pode sair de Importar conteúdo sem perder a revisão, desde que não confirme a gravação."
        ),
        "ask": "Iniciar a análise do ficheiro selecionado?",
        "show_detail": True,
    },
    "importacao_assistida_confirmar": {
        "title": "Confirmar gravação da importação",
        "lead": (
            "Os blocos selecionados serão inseridos no relatório em transação única, com eventuais ajustes de secções, "
            "quando a estrutura o exigir."
        ),
        "detail": "Operação de escrita: verifique a lista de revisão antes de continuar.",
        "ask": "Gravar no relatório os blocos selecionados?",
        "show_detail": True,
    },
    "relatorio_criar": {
        "title": "Confirmar criação do relatório",
        "lead": (
            "Será criado um novo D20 com as secções de acordo com a fonte de sumário indicada:"
        ),
        "detail": "Após a criação, o código não poderá ser alterado; a versão inicia em R00.",
        "ask": "Criar o relatório com estes parâmetros?",
        "show_detail": True,
    },
    "exportar_relatorio": {
        "title": "Confirmar exportação",
        "lead": "Gera-se o ficheiro (PDF ou DOCX) a partir do conteúdo atual do relatório, segundo o âmbito escolhido.",
        "detail": "O processo pode levar de alguns segundos a minutos, conforme o volume. O download abre noutro separador.",
        "ask": "Iniciar a exportação?",
        "show_detail": True,
    },
    "relatorio_excluir": {
        "title": "Confirmar exclusão do relatório",
        "lead": "O relatório e os dados associados serão removidos de forma definitiva. Esta ação não pode ser desfeita.",
        "detail": "",
        "ask": "Excluir definitivamente este relatório?",
        "show_detail": False,
    },
    "secao_excluir": {
        "title": "Confirmar exclusão da secção",
        "lead": "A subsecção e todos os respetivos blocos serão removidos. Esta ação não se pode anular de forma simples no sistema.",
        "detail": "",
        "ask": "Excluir definitivamente esta secção e o seu conteúdo?",
        "show_detail": False,
    },
    "bloco_confirmar": {
        "title": "Confirmar e bloquear bloco",
        "lead": "O bloco deixa de ser editável, passando a estado bloqueado para revisão, conforme o fluxo de coordenação.",
        "detail": "",
        "ask": "Bloquear este bloco para revisão?",
        "show_detail": False,
    },
    "bloco_excluir": {
        "title": "Confirmar exclusão do bloco",
        "lead": "O bloco será removido de forma definitiva. Contagens e numeração podem ser ajustadas automaticamente após a exclusão.",
        "detail": "",
        "ask": "Excluir permanentemente este bloco?",
        "show_detail": False,
    },
    "blocos_lote_excluir": {
        "title": "Confirmar exclusão em lote",
        "lead": "Os blocos selecionados serão excluídos. Verifique a seleção no quadro de blocos.",
        "detail": "",
        "ask": "Excluir definitivamente os blocos selecionados?",
        "show_detail": False,
    },
    "blocos_lote_aprovar": {
        "title": "Confirmar aprovação em lote",
        "lead": "Os blocos selecionados serão bloqueados para revisão, em sequência, uma única operação de escrita na base.",
        "detail": "",
        "ask": "Bloquear os blocos selecionados para revisão?",
        "show_detail": False,
    },
}


def resposta_fluxo_confirmacao(chave: str) -> dict[str, Any] | None:
    row = FLUXO_CONFIRMACAO.get(chave)
    if not row:
        return None
    out: dict[str, Any] = {
        "title": row.get("title", "Confirmar"),
        "lead": row.get("lead", ""),
        "detail": row.get("detail", ""),
        "ask": row.get("ask", "Deseja continuar?"),
        "show_detail": bool(row.get("show_detail", False) and (row.get("detail") or "").strip()),
    }
    return out
