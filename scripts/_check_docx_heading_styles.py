"""Extrai formatação de estilos do DOCX D20-13."""

import zipfile
import xml.etree.ElementTree as ET

with zipfile.ZipFile("relatorios_entregues/D20-13 - R00 1.docx") as z:
    styles_xml = z.read("word/styles.xml")

root = ET.fromstring(styles_xml)
ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# Lista todos os estilos relevantes
for style_id in ["Ttulo1", "Ttulo2", "Ttulo3", "Ttulo4", "Nvel1", "Nvel11"]:
    for style in root.findall(".//w:style", ns):
        sid = style.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}styleId", "")
        if sid == style_id:
            name = style.find(".//w:name", ns)
            name_val = (
                name.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
                if name is not None
                else ""
            )
            rpr = style.find(".//w:rPr", ns)
            size = None
            bold = False
            italic = False
            font = None
            if rpr is not None:
                sz = rpr.find(".//w:sz", ns)
                if sz is not None:
                    size = int(sz.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")) / 2
                b = rpr.find(".//w:b", ns)
                bold = b is not None
                i = rpr.find(".//w:i", ns)
                italic = i is not None
                f = rpr.find(".//w:rFonts", ns)
                if f is not None:
                    font = f.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii", "")
            basedOn = style.find(".//w:basedOn", ns)
            basedOn_val = (
                basedOn.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
                if basedOn is not None
                else ""
            )
            print(
                f"{style_id} ({name_val}): size={size}pt bold={bold} italic={italic} font={font} basedOn={basedOn_val}"
            )
            break
