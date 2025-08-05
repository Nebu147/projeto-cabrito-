"""
gera_bilhete.py  –  versão alinhada ao seu projeto
=================================================
Arquivos esperados na mesma pasta:
    • bg_controle.pdf          → fundo oficial (faixa, logo, QR, linhas)
    • controle.json            → só os dados variáveis (origem, destino…)
    • coords_controle.json     → layout: pos, font, pt, align

Gera controle_80x130.pdf idêntico ao modelo.

Requisitos:
    pip install reportlab PyPDF2
"""

import json
from io import BytesIO
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from PyPDF2 import PdfReader, PdfWriter

# --------------------------------------------------
# Parâmetros do cupom (80 × 130 mm)
PAGE_W_MM = 80
PAGE_H_MM = 130
PAGE_W_PT = PAGE_W_MM * mm
PAGE_H_PT = PAGE_H_MM * mm

# Arquivos
FILE_DATA   = Path("controle.json")
FILE_COORDS = Path("coords_controle.json")
FILE_BG     = Path("bg_controle.pdf")
FILE_OUT    = Path("controle_80x130.pdf")

# --------------------------------------------------

def gerar_overlay(dados: dict, coords: dict) -> BytesIO:
    """Cria PDF em memória contendo apenas o texto vetorial."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W_PT, PAGE_H_PT))

    for chave, meta in coords.items():
        texto   = meta.get("texto", "")
        fonte   = meta.get("font", "Helvetica")
        tamanho = meta.get("pt", 8)
        align   = meta.get("align", "left")
        x_mm, y_top_mm = meta["pos"]
        y_mm = PAGE_H_MM - y_top_mm  # GIMP → ReportLab

        # ---- substituição dinâmica ----------------------------------
        if chave.endswith("_valor"):
            campo = chave.replace("_valor", "")
            texto = dados.get(campo, texto)
        elif chave.endswith("_valor_1"):
            campo = chave.replace("_valor_1", "")
            texto = dados.get(campo, texto)
        elif chave.endswith("_valor_2"):
            campo = chave.replace("_valor_2", "_2")
            texto = dados.get(campo, texto)

        if not texto.strip():
            continue

        c.setFont(fonte, tamanho)
        if align == "center":
            c.drawCentredString(PAGE_W_PT / 2, y_mm * mm, texto)
        else:
            c.drawString(x_mm * mm, y_mm * mm, texto)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

# --------------------------------------------------

def aplicar_fundo(overlay: BytesIO, fundo_pdf: Path, destino_pdf: Path):
    """Mescla overlay ao fundo e salva no destino."""
    fundo   = PdfReader(str(fundo_pdf))
    sobre   = PdfReader(overlay)
    writer  = PdfWriter()

    pagina = fundo.pages[0]
    pagina.merge_page(sobre.pages[0])
    writer.add_page(pagina)

    with destino_pdf.open("wb") as f:
        writer.write(f)

# --------------------------------------------------

if __name__ == "__main__":
    # 1) Ler JSONs
    data   = json.loads(FILE_DATA.read_text(encoding="utf-8"))
    layout = json.loads(FILE_COORDS.read_text(encoding="utf-8"))

    # 2) Overlay de texto
    overlay_stream = gerar_overlay(data, layout)

    # 3) Fundo + texto
    aplicar_fundo(overlay_stream, FILE_BG, FILE_OUT)

    print(f"✅ Bilhete gerado: {FILE_OUT}")
