"""Extrai estilos de títulos do DOCX de referência D20-13."""
from docx import Document

doc = Document("relatorios_entregues/D20-13 - R00 1.docx")
styles = {}
for p in doc.paragraphs[:150]:
    if p.style.name.startswith("Heading"):
        st = p.style
        if st.name not in styles:
            styles[st.name] = {
                "name": st.name,
                "font": st.font.name,
                "size": st.font.size,
                "bold": st.font.bold,
                "italic": st.font.italic,
                "color": (
                    str(st.font.color.rgb)
                    if st.font.color and st.font.color.rgb
                    else None
                ),
                "text": p.text[:60],
            }

for k, v in sorted(styles.items()):
    print(
        f'{k}: font={v["font"]} size={v["size"]} bold={v["bold"]} '
        f'italic={v["italic"]} color={v["color"]} text={v["text"]!r}'
    )
