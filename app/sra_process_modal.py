"""Contrato de textos e metadados para modais de feedback de processo (SRA).

Cada processo de negocio com varias etapas deve:
- enviar `process_key` estavel (ex.: "importacao_docx", "gerar_pdf");
- preencher `titulo` (cabeçalho), `mensagem` (corpo principal);
- quando aplicavel, `detalhe` (segundo bloco) e, em falha, `recomendacao` (O que fazer);
- classificar o fim com `outcome` em success | partial | failure.

Os rotulos de slot (Detalhe, Ressalvas, O que fazer) vivem no HTML; este modulo
define chaves e helpers para o payload em `data` dos eventos SSE.
"""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict

Outcome = Literal["success", "partial", "failure"]


class ModalProcessoFimData(TypedDict, total=False):
    """Chaves em `event["data"]` para o modal de fim de processo (status).

    `channel` = "process" isola o fluxo do canal de notificacoes.
    """

    channel: str
    process_key: str
    titulo: str
    mensagem: str
    detalhe: str
    recomendacao: str
    outcome: str


# Rotulos de slot (documentacao; o HTML em complementos/ replica em pt-BR).
LEGENDA_DETALHE: Final[str] = "Detalhe"
LEGENDA_RESSALVAS: Final[str] = "Ressalvas"
LEGENDA_O_QUE_FAZER: Final[str] = "O que fazer"
LEGENDA_PERGUNTA_PADRAO: Final[str] = "Deseja continuar?"

# Confirmacao: slots opcionais preenchiveis via JS ou futuro `data` no evento.
# titulo, mensagem (lead), detalhe, pergunta (ultima linha antes dos botoes).


def outcome_resolvido(*, ok: bool, outcome: str | None) -> Outcome:
    """Deriva o resultado do modal. `outcome` explicito gana sobre `ok`."""
    if outcome in ("success", "partial", "failure"):
        return outcome  # type: ignore[return-value]
    return "success" if ok else "failure"


def nivel_e_status_por_outcome(resolved: Outcome) -> tuple[str, str]:
    """Retorna (level, status) usados no evento SSE (toast/log legado)."""
    if resolved == "failure":
        return "error", "danger"
    if resolved == "partial":
        return "success", "warning"
    return "success", "success"


def montar_data_modal_fim(  # pylint: disable=too-many-arguments
    *,
    process_key: str,
    titulo: str,
    mensagem: str,
    outcome: Outcome,
    detalhe: str = "",
    recomendacao: str = "",
) -> dict[str, Any]:
    """Monta o dict `data` para `process_done` / eventos de fim de processo."""
    row: dict[str, Any] = {
        "channel": "process",
        "process_key": process_key,
        "titulo": titulo,
        "mensagem": mensagem,
        "outcome": outcome,
    }
    if detalhe:
        row["detalhe"] = detalhe
    if recomendacao:
        row["recomendacao"] = recomendacao
    return row
