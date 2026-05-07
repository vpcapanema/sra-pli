MAX_STEPS = 5
history = []

def safe_agent_run(task, llm):
    global history
    for step in range(MAX_STEPS):
        response = llm.chat(task, history[-3:])
        if "SUCESSO:" in response or "FINALIZADO" in response:
            return response
        if "FALHA:" in response or "LIMITE ATINGIDO" in response:
            return response
        history.append(response)
    return f"LIMITE {MAX_STEPS} passos. Último: {history[-1] if history else 'sem histórico'}"
