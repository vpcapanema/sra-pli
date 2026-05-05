import sys, traceback
sys.path.insert(0, r'd:\sistema_relatorio_mensal_atividades')
try:
    from app.sumario_extractor import extrair_completo_pdf_disponivel
    r = extrair_completo_pdf_disponivel('D20-12 - R01.pdf')
    print(f'OK: {len(r)} secoes')
    for s in r[:5]:
        print(f"  {s['secao_numero']!r} | {s['secao_titulo']!r} | blocos={len(s['blocos'])}")
except Exception:
    traceback.print_exc()
