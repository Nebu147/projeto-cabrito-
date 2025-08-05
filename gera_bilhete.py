"""
gera_bilhete.py – cada parte usa seu próprio tamanho (pt)
========================================================
• Linhas centrais concatenadas mas respeitam `pt` individual de rótulo e valor.
• Basta editar o `pt` de qualquer item no coords_controle.json e rodar.

Requisitos: reportlab, PyPDF2
"""

import json
from io import BytesIO
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from PyPDF2 import PdfReader, PdfWriter

# Página 80 × 130 mm
PAGE_W_MM = 80
PAGE_H_MM = 130
PAGE_W_PT = PAGE_W_MM * mm
PAGE_H_PT = PAGE_H_MM * mm

# Arquivos
FILE_DATA   = Path("controle.json")
FILE_COORDS = Path("coords_controle.json")
FILE_BG     = Path("bg_controle.pdf")
FILE_OUT    = Path("controle_80x130.pdf")

# Grupos a centralizar (rótulo + valores)
GRUPOS = [
    ("origem_label",  "origem_valor"),
    ("destino_label", "destino_valor"),
    ("data_label",    "data_valor", "horario_label", "horario_valor"),
    ("poltrona_label", "poltrona_valor", "plataforma_label", "plataforma_valor"),
    ("prefixo_label", "prefixo_valor", "linha_label", "linha_valor_1", "linha_valor_2"),
    ("tipo_label", "tipo_valor")
]

# ----------------------------------------------------------------------

def draw_mixed(c: canvas.Canvas, partes, fontes, pts, y_mm):
    """Centraliza linha somando larguras individuais."""
    total = sum(stringWidth(t, f, p) for t, f, p in zip(partes, fontes, pts))
    x_pt = (PAGE_W_PT - total) / 2
    for texto, fonte, pt in zip(partes, fontes, pts):
        c.setFont(fonte, pt)
        c.drawString(x_pt, y_mm * mm, texto)
        x_pt += stringWidth(texto, fonte, pt)

# ----------------------------------------------------------------------

def gerar_overlay(dados: dict, coords: dict) -> BytesIO:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W_PT, PAGE_H_PT))

    usados = set()
    # --- centralizados ---
    for grupo in GRUPOS:
        partes, fontes, pts = [], [], []
        for chave in grupo:
            meta = coords[chave]
            texto = meta["texto"]
            if chave.endswith("_valor"):
                campo = chave.replace("_valor", "")
                texto = dados.get(campo, texto)
                fontes.append("Helvetica-Bold")
            else:
                fontes.append("Helvetica")
            partes.append(texto)
            pts.append(meta.get("pt", 8))
            usados.add(chave)
        y_top_mm = coords[grupo[0]]["pos"][1]
        y_mm = PAGE_H_MM - y_top_mm
        draw_mixed(c, partes, fontes, pts, y_mm)

    # --- demais campos (passageiro) ---
    for chave, meta in coords.items():
        if chave in usados:
            continue
        texto = meta["texto"]
        fonte = meta.get("font", "Helvetica")
        tamanho = meta.get("pt", 8)
        align = meta.get("align", "left")
        x_mm, y_top_mm = meta["pos"]
        y_mm = PAGE_H_MM - y_top_mm
        if "_valor" in chave:
            campo = chave.replace("_valor", "").replace("_1", "").replace("_2", "_2")
            texto = dados.get(campo, texto)
        if not texto.strip():
            continue
        c.setFont(fonte, tamanho)
        if align == "center":
            c.drawCentredString(PAGE_W_PT/2, y_mm*mm, texto)
        else:
            c.drawString(x_mm*mm, y_mm*mm, texto)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

# ----------------------------------------------------------------------

def aplicar_fundo(overlay: BytesIO, fundo: Path, destino: Path):
    page_bg = PdfReader(str(fundo)).pages[0]
    page_ov = PdfReader(overlay).pages[0]
    page_bg.merge_page(page_ov)
    writer = PdfWriter()
    writer.add_page(page_bg)
    with destino.open("wb") as f:
        writer.write(f)

# ----------------------------------------------------------------------

if __name__ == "__main__":
    data   = json.loads(FILE_DATA.read_text(encoding="utf-8"))
    coords = json.loads(FILE_COORDS.read_text(encoding="utf-8"))
    overlay = gerar_overlay(data, coords)
    aplicar_fundo(overlay, FILE_BG, FILE_OUT)
    print("✅ PDF gerado com tamanhos individuais:", FILE_OUT)
