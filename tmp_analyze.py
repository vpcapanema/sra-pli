import sys, json, io
sys.path.insert(0, r'd:\sistema_relatorio_mensal_atividades')
from pathlib import Path

pdf_path = Path(r'd:\sistema_relatorio_mensal_atividades\relatorios_entregues\D20-12 - R01.pdf')

# (A) Estrutura que o extrator atual produz
from app.sumario_extractor import extrair_completo_pdf_disponivel
result = extrair_completo_pdf_disponivel('D20-12 - R01.pdf')
print('=== EXTRACAO ATUAL ===')
print(f'Total secoes: {len(result)}')
for s in result[:20]:
    tipos = [b.get('tipo') for b in s['blocos']]
    print(f"  {s['secao_numero']!r} | {s['secao_titulo']!r} | blocos_tipos={tipos}")
    for i, b in enumerate(s['blocos']):
        c = (b.get('conteudo') or '')[:120].replace('\n', ' ')
        print(f"      [{i}] tipo={b.get('tipo')!r} preview={c!r}")

# (B) Layout espacial com PyMuPDF (tamanho de fonte por bloco, bbox)
import fitz
doc = fitz.open(str(pdf_path))
print(f'\n=== PyMuPDF blocks (pag 0-3, primeiras 20 linhas) ===')
for pno in range(min(4, len(doc))):
    page = doc[pno]
    d = page.get_text('dict')
    print(f'--- Pagina {pno+1} ---')
    n_blk = 0
    for blk in d.get('blocks', []):
        if blk.get('type') != 0:  # 0 = texto
            continue
        for line in blk.get('lines', []):
            for span in line.get('spans', []):
                txt = span.get('text','').strip()
                if not txt: continue
                print(f"  size={span.get('size'):.1f} font={span.get('font')!r} flags={span.get('flags')} bbox={tuple(round(x,1) for x in span.get('bbox',()))} text={txt[:90]!r}")
                n_blk += 1
                if n_blk > 20: break
            if n_blk > 20: break
        if n_blk > 20: break

# (C) Inventário tipográfico: quantas sizes diferentes, qual é "corpo", qual é "heading"
print(f'\n=== INVENTARIO TIPOGRAFICO ===')
from collections import Counter
sizes = Counter()
fonts = Counter()
for page in doc:
    d = page.get_text('dict')
    for blk in d.get('blocks', []):
        if blk.get('type') != 0: continue
        for line in blk.get('lines', []):
            for span in line.get('spans', []):
                if span.get('text','').strip():
                    sizes[round(span.get('size', 0), 1)] += 1
                    fonts[span.get('font', '')] += 1
print('Top sizes:', sizes.most_common(10))
print('Top fonts:', fonts.most_common(5))

# (D) Procurar padrões "Figura X.Y:" e "Tabela X.Y:" no texto
print(f'\n=== LEGENDAS FIGURA/TABELA ===')
import re
full = ''
for page in doc:
    full += page.get_text('text') + '\n'
figs = re.findall(r'Figura\s+\d+(?:\.\d+)?\s*[:\-\u2013\u2014].*', full)[:10]
tabs = re.findall(r'Tabela\s+\d+(?:\.\d+)?\s*[:\-\u2013\u2014].*', full)[:10]
fontes = re.findall(r'Fonte:.*', full)[:10]
print('Figuras:', figs)
print('Tabelas:', tabs)
print('Fontes:', fontes)

doc.close()
