import re

with open(r'd:\sistema_relatorio_mensal_atividades\app\templates\complementos\_secao01_governanca.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix all broken multi-line Jinja2 conditional attributes

# Pattern 1: relatorio_filtro_id="" ="r.id" (already fixed by previous script, but just in case)
content = re.sub(
    r'<option\s*\n\s*value="\{\{ r\.id \}\}"\s*\n\s*\{%\s*\n\s*if\s*\n\s*relatorio_filtro_id=""\s*\n\s*="r\.id"\s*\n\s*%\}\s*\n\s*selected\{%\s*\n\s*endif\s*\n\s*%\}\s*\n\s*>',
    r'<option value="{{ r.id }}"{% if relatorio_filtro_id == r.id %} selected{% endif %}>',
    content
)

# Pattern 2: loop.first
content = re.sub(
    r'<option\s*\n\s*value="\{\{ r\.id \}\}"\s*\n\s*\{%\s*\n\s*if\s*\n\s*loop\.first\s*\n\s*%\}\s*\n\s*selected\{%\s*\n\s*endif\s*\n\s*%\}\s*\n\s*>',
    r'<option value="{{ r.id }}"{% if loop.first %} selected{% endif %}>',
    content
)

# Pattern 3: not relatorios_abertos (button disabled)
content = re.sub(
    r'<button\s*\n\s*type="submit"\s*\n\s*class="coord-btn-block"\s*\n\s*\{%\s*\n\s*if\s*\n\s*not\s*\n\s*relatorios_abertos\s*\n\s*%\}disabled\{%\s*\n\s*endif\s*\n\s*%\}\s*\n\s*>',
    r'<button\n                  type="submit"\n                  class="coord-btn-block"\n                  {% if not relatorios_abertos %}disabled{% endif %}\n                >',
    content
)

with open(r'd:\sistema_relatorio_mensal_atividades\app\templates\complementos\_secao01_governanca.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
