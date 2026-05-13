"""Conversão de posições de ciclo para expressões cron."""

from datetime import datetime
from typing import Optional


def posicao_para_cron(
    subtipo_recorrencia: str,
    posicao_inicio: Optional[int],
    posicao_fim: Optional[int],
    hora: str,
    data_base: Optional[datetime] = None,
) -> str:
    """
    Converte posição no ciclo para expressão cron.

    Args:
        subtipo_recorrencia: horaria, diaria, semanal, quinzenal, mensal, anual
        posicao_inicio: posição de início no ciclo (dia do mês, dia da semana, etc)
        posicao_fim: posição de fim no ciclo (opcional)
        hora: hora de disparo no formato HH:MM
        data_base: data base para calcular o próximo ciclo (opcional)

    Returns:
        Expressão cron no formato: minuto hora dia_mes mes dia_semana
    """
    minuto, hora_int = hora.split(":")

    if subtipo_recorrencia == "horaria":
        # Executa a cada X minutos
        return f"{minuto} * * * *" if posicao_inicio else f"{minuto} * * * *"

    elif subtipo_recorrencia == "diaria":
        # Executa todos os dias à hora especificada
        return f"{minuto} {hora_int} * * *"

    elif subtipo_recorrencia == "semanal":
        # Executa no dia da semana especificado (1=Seg, 7=Dom)
        dia = posicao_inicio or 1
        return f"{minuto} {hora_int} * * {dia}"

    elif subtipo_recorrencia == "quinzenal":
        # Executa a cada 15 dias (dia 1 e 15)
        return f"{minuto} {hora_int} 1,15 * *"

    elif subtipo_recorrencia == "mensal":
        # Executa no dia do mês especificado
        dia = posicao_inicio or 1
        return f"{minuto} {hora_int} {dia} * *"

    elif subtipo_recorrencia == "anual":
        # Executa no dia e mês especificados (formato DDMM)
        if data_base:
            dia = data_base.day
            mes = data_base.month
        else:
            dia = (posicao_inicio // 100) or 1
            mes = (posicao_inicio % 100) or 1
        return f"{minuto} {hora_int} {dia} {mes} *"

    elif subtipo_recorrencia == "customizada":
        # Para customizada, usa a posição como dia do mês
        dia = posicao_inicio or 1
        return f"{minuto} {hora_int} {dia} * *"

    # Padrão: diário
    return f"{minuto} {hora_int} * * *"


def calcular_proxima_execucao(
    cron_expression: str,
    data_base: Optional[datetime] = None,
) -> datetime:
    """
    Calcula a próxima execução baseada na expressão cron.

    Args:
        cron_expression: expressão cron no formato: minuto hora dia_mes mes dia_semana
        data_base: data base para cálculo (padrão: agora)

    Returns:
        Datetime da próxima execução
    """
    # TODO: Implementar cálculo real usando croniter ou similar
    # Por enquanto, retorna data_base + 1 hora como placeholder
    from datetime import timedelta

    base = data_base or datetime.now()
    return base + timedelta(hours=1)


def validar_posicao_ciclo(
    subtipo_recorrencia: str,
    posicao: int,
) -> bool:
    """
    Valida se a posição é válida para o tipo de recorrência.

    Args:
        subtipo_recorrencia: tipo de recorrência
        posicao: posição a validar

    Returns:
        True se válido, False caso contrário
    """
    if subtipo_recorrencia == "semanal":
        return 1 <= posicao <= 7  # 1=Seg, 7=Dom
    elif subtipo_recorrencia == "mensal":
        return 1 <= posicao <= 31
    elif subtipo_recorrencia == "anual":
        return 101 <= posicao <= 1231  # 0101 a 3112 (DDMM)
    elif subtipo_recorrencia == "horaria":
        return 0 <= posicao <= 59  # minuto
    return True
