"""Análise linguística (ortografia/gramática) sob demanda — Seção 2.

Estratégia em três camadas, sempre cai pra trás sem travar:
  1) `language_tool_python` (gramática + estilo + ortografia, requer Java).
  2) `pyspellchecker` PT-BR (só ortografia, dicionário offline).
  3) Modo "desligado" — devolve aviso explicando como ligar.

A análise corre apenas sobre texto plano de blocos `texto`, `lista` e sobre
legenda/fonte de blocos `figura`/`tabela`. HTML/JSON é despido com regex
simples — bom o suficiente para o nosso conteúdo.
"""
from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ...models import Bloco, Relatorio, Secao
from .checagens_globais import autor_rotulo_secao
from .relatorio_secoes_load import load_relatorio_secoes_blocos_responsavel

log = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_REF_RE = re.compile(r"\[\[REF:[^\]]+\]\]")
_MULTI_WS_RE = re.compile(r"\s+")
_PALAVRA_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,}")

# Termos próprios do projeto que pyspellchecker não conhece — adicionados ao
# vocabulário para reduzir ruído. Lista propositalmente curta; expandir só
# com termos que aparecerem como falso positivo recorrente.
_VOCAB_PROJETO = (
    "PLI",
    "SEMIL",
    "VDMA",
    "SRA",
    "DAEE",
    "ANA",
    "SP",
    "DER",
    "PMSP",
    "Codgi",
)


@dataclass(slots=True)
class AchadoLing:
    regra: str
    mensagem: str
    trecho: str
    sugestoes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SecaoLing:
    secao_numero: str
    secao_titulo: str
    responsavel_rotulo: str
    achados: list[AchadoLing] = field(default_factory=list)


@dataclass(slots=True)
class ResultadoLing:
    motor: str  # 'languagetool' | 'pyspellchecker' | 'desligado'
    motor_rotulo: str
    aviso_motor: str
    secoes: list[SecaoLing] = field(default_factory=list)

    @property
    def total_avisos(self) -> int:
        return sum(len(s.achados) for s in self.secoes)


def _texto_plano_do_bloco(b: Bloco) -> str:
    partes: list[str] = []
    if b.tipo in ("texto", "lista") and b.conteudo:
        partes.append(b.conteudo)
    if b.legenda:
        partes.append(b.legenda)
    if b.fonte:
        partes.append(b.fonte)
    bruto = " ".join(partes)
    bruto = _REF_RE.sub("", bruto)
    bruto = _HTML_TAG_RE.sub(" ", bruto)
    bruto = _MULTI_WS_RE.sub(" ", bruto).strip()
    return bruto


def _coletar_textos_por_secao(rel: Relatorio) -> list[tuple[Secao, str]]:
    """Devolve [(seção, texto_concatenado)] preservando ordem do relatório.
    Seção sem texto utilizável é omitida."""
    out: list[tuple[Secao, str]] = []
    for sec in sorted(rel.secoes, key=lambda s: s.ordem):
        textos = [_texto_plano_do_bloco(b) for b in sec.blocos]
        texto = " ".join(t for t in textos if t).strip()
        if texto:
            out.append((sec, texto))
    return out


def _detectar_motor() -> str:
    """Retorna o motor a usar. Detecção barata (só checa imports)."""
    if importlib.util.find_spec("language_tool_python") is not None:
        return "languagetool"
    if importlib.util.find_spec("spellchecker") is not None:
        return "pyspellchecker"
    return "desligado"


# ---------------------------------------------------------------------------
# Backend: LanguageTool (qualidade alta; requer Java + ~500 MB no primeiro uso)
# ---------------------------------------------------------------------------
_LT_INSTANCE: Any = None


def _lt_instance() -> Any:
    """Cria/retorna instância singleton de LanguageTool. Reduz custo da JVM
    a uma única inicialização por processo."""
    global _LT_INSTANCE  # pylint: disable=global-statement
    if _LT_INSTANCE is None:
        import language_tool_python  # type: ignore  # pylint: disable=import-outside-toplevel,import-error
        _LT_INSTANCE = language_tool_python.LanguageTool("pt-BR")
    return _LT_INSTANCE


def _analisar_lt(texto: str) -> list[AchadoLing]:
    tool = _lt_instance()
    out: list[AchadoLing] = []
    for m in tool.check(texto):
        trecho = texto[m.offset:m.offset + m.errorLength] if m.errorLength else ""
        out.append(
            AchadoLing(
                regra=m.ruleId,
                mensagem=m.message,
                trecho=trecho,
                sugestoes=list(m.replacements[:3]),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Backend: pyspellchecker (só ortografia; default sempre disponível)
# ---------------------------------------------------------------------------
_SP_INSTANCE: Any = None


def _sp_instance() -> Any:
    """Singleton do SpellChecker em PT, com vocabulário do projeto carregado."""
    global _SP_INSTANCE  # pylint: disable=global-statement
    if _SP_INSTANCE is None:
        from spellchecker import SpellChecker  # pylint: disable=import-outside-toplevel,import-error
        sp = SpellChecker(language="pt", distance=1)
        sp.word_frequency.load_words([t.lower() for t in _VOCAB_PROJETO])
        _SP_INSTANCE = sp
    return _SP_INSTANCE


def _analisar_sp(texto: str) -> list[AchadoLing]:
    sp = _sp_instance()
    achados_por_palavra: dict[str, AchadoLing] = {}
    palavras = _PALAVRA_RE.findall(texto)
    desconhecidas = sp.unknown(p.lower() for p in palavras)
    for original in palavras:
        chave = original.lower()
        if chave not in desconhecidas:
            continue
        if chave in achados_por_palavra:
            continue
        sugestoes_raw = sp.candidates(chave) or set()
        sugestoes = sorted(s for s in sugestoes_raw if s != chave)[:3]
        achados_por_palavra[chave] = AchadoLing(
            regra="ORTOGRAFIA",
            mensagem="Palavra possivelmente fora do dicionário PT-BR.",
            trecho=original,
            sugestoes=sugestoes,
        )
    return list(achados_por_palavra.values())


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
_ROTULOS = {
    "languagetool": "LanguageTool (gramática + estilo + ortografia; Java 8+)",
    "pyspellchecker": "pyspellchecker PT-BR (somente ortografia, offline)",
    "desligado": "desligado",
}
_AVISO_MOTOR = {
    "languagetool": "",
    "pyspellchecker": (
        "Apenas ortografia foi analisada. Para gramática e estilo, garanta "
        "**Java 8+** no PATH do servidor (o pacote language_tool_python já está no projeto — "
        "`pip install -r requirements.txt`). O sistema usa LanguageTool automaticamente quando a JVM responde."
    ),
    "desligado": (
        "Nenhum motor de revisão linguística foi encontrado. Instale "
        "'pyspellchecker' (incluído em requirements.txt) para ortografia, ou "
        "'language_tool_python' com Java 8+ no servidor para gramática e estilo também."
    ),
}


def analisar_relatorio(db: Session, rel: Relatorio) -> ResultadoLing:
    """Coleta texto por seção e roda no motor disponível, com fallback gracioso.

    Falhas no motor escolhido (ex.: LT travou no Java) caem para o pyspellchecker
    em vez de devolverem erro 500 — o coord precisa de algo, não de exceção.
    """
    rel_full = load_relatorio_secoes_blocos_responsavel(db, rel.id)
    motor = _detectar_motor()
    if motor == "desligado":
        return ResultadoLing(
            motor=motor,
            motor_rotulo=_ROTULOS[motor],
            aviso_motor=_AVISO_MOTOR[motor],
        )

    textos_por_secao = _coletar_textos_por_secao(rel_full)
    if not textos_por_secao:
        return ResultadoLing(
            motor=motor,
            motor_rotulo=_ROTULOS[motor],
            aviso_motor=(
                _AVISO_MOTOR[motor]
                or "Sem texto utilizável no relatório (apenas figuras/tabelas)."
            ),
        )

    secoes_resultado: list[SecaoLing] = []
    motor_efetivo = motor
    aviso_extra = ""
    for sec, texto in textos_por_secao:
        try:
            if motor_efetivo == "languagetool":
                achados = _analisar_lt(texto)
            else:
                achados = _analisar_sp(texto)
        except Exception as exc:  # noqa: BLE001
            # Falha do LT (Java ausente, JAR corrompido) é o caso comum aqui.
            # Cair para pyspellchecker uma única vez e seguir o relatório.
            log.warning("Motor %s falhou: %s — caindo para pyspellchecker.", motor_efetivo, exc)
            motor_efetivo = "pyspellchecker"
            aviso_extra = (
                "O LanguageTool falhou em tempo de execução (confirme Java 8+ no servidor); "
                "resultados a partir desta seção vieram do pyspellchecker (somente ortografia)."
            )
            try:
                achados = _analisar_sp(texto)
            except Exception as exc2:  # noqa: BLE001
                log.error("pyspellchecker também falhou: %s", exc2)
                return ResultadoLing(
                    motor="desligado",
                    motor_rotulo=_ROTULOS["desligado"],
                    aviso_motor=f"Falha em todos os motores: {exc} / {exc2}",
                )
        if achados:
            secoes_resultado.append(
                SecaoLing(
                    secao_numero=sec.numero,
                    secao_titulo=sec.titulo,
                    responsavel_rotulo=autor_rotulo_secao(sec),
                    achados=achados,
                )
            )

    aviso = _AVISO_MOTOR[motor_efetivo]
    if aviso_extra:
        aviso = (aviso + " " + aviso_extra).strip()
    return ResultadoLing(
        motor=motor_efetivo,
        motor_rotulo=_ROTULOS[motor_efetivo],
        aviso_motor=aviso,
        secoes=secoes_resultado,
    )


def resultado_para_dict(r: ResultadoLing) -> dict[str, Any]:
    """Serializador para a resposta JSON da rota."""
    return {
        "motor": r.motor,
        "motor_rotulo": r.motor_rotulo,
        "aviso_motor": r.aviso_motor,
        "total_avisos": r.total_avisos,
        "secoes": [
            {
                "secao_numero": s.secao_numero,
                "secao_titulo": s.secao_titulo,
                "responsavel_rotulo": s.responsavel_rotulo,
                "achados": [
                    {
                        "regra": a.regra,
                        "mensagem": a.mensagem,
                        "trecho": a.trecho,
                        "sugestoes": list(a.sugestoes),
                    }
                    for a in s.achados
                ],
            }
            for s in r.secoes
        ],
    }
