"""
gera_bilhete.py – central + negrito + quebra de linha
====================================================
• Cada item usa seu próprio `pt` (tamanho).
• Valores (_valor, _valor_1, _valor_2) saem em **Helvetica‑Bold**.
• Grupo ‘Prefixo / Linha’ NÃO inclui `linha_valor_2` → essa segunda linha
  é desenhada depois, respeitando seu Y, permitindo a quebra como no gabarito.

Para quebrar linhas, mantenha `linha_valor_1` e `linha_valor_2` em coords_controle.json
com Y diferentes (73.5 e 76.5 mm).  Basta adicionar espaço final nos rótulos
(“Prefixo: ”, “Linha ”) para evitar texto colado.

Requisitos:  reportlab  •  PyPDF2
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

# Caminhos
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
    ("prefixo_label", "prefixo_valor", "linha_label", "linha_valor_1"),   # _2 fora
    ("tipo_label", "tipo_valor"),
    ("passageiro_label", "passageiro_valor_1")   # CPF+nome na mesma linha
]

# ----------------------------------------------------------------------

def draw_mixed(c: canvas.Canvas, partes, fontes, pts, y_mm):
    """Centraliza linha somando larguras de cada trecho."""
    total = sum(stringWidth(t, f, p) for t, f, p in zip(partes, fontes, pts))
    x_pt = (PAGE_W_PT - total) / 2
    for texto, fonte, pt in zip(partes, fontes, pts):
        c.setFont(fonte, pt)
        c.drawString(x_pt, y_mm*mm, texto)
        x_pt += stringWidth(texto, fonte, pt)

# ----------------------------------------------------------------------

def gerar_overlay(data: dict, coords: dict) -> BytesIO:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W_PT, PAGE_H_PT))
    usados = set()

    # --- Linhas centrais ---
    for grupo in GRUPOS:
        partes, fontes, pts = [], [], []
        for chave in grupo:
            meta = coords[chave]
            texto = meta["texto"]
            if "_valor" in chave:               # qualquer valor fica Bold
                campo = chave.replace("_valor", "").replace("_1", "").replace("_2", "_2")
                texto = data.get(campo, texto)
                fontes.append("Helvetica-Bold")
            else:
                fontes.append("Helvetica")
            partes.append(texto)
            pts.append(meta.get("pt", 8))
            usados.add(chave)
        y_mm = PAGE_H_MM - coords[grupo[0]]["pos"][1]
        draw_mixed(c, partes, fontes, pts, y_mm)

    # --- Demais itens (linha_valor_2 + passageiro) ---
    for chave, meta in coords.items():
        if chave in usados:
            continue
        texto = meta["texto"]
        if "_valor" in chave:
            campo = chave.replace("_valor", "").replace("_1", "").replace("_2", "_2")
            texto = data.get(campo, texto)
        if not texto.strip():
            continue
        fonte   = meta.get("font", "Helvetica")
        tamanho = meta.get("pt", 8)
        align   = meta.get("align", "left")
        x_mm, y_top_mm = meta["pos"]
        y_mm = PAGE_H_MM - y_top_mm
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

def aplicar_fundo(overlay: BytesIO, bg_pdf: Path, out_pdf: Path):
    page_bg = PdfReader(str(bg_pdf)).pages[0]
    page_ov = PdfReader(overlay).pages[0]
    page_bg.merge_page(page_ov)
    writer = PdfWriter()
    writer.add_page(page_bg)
    with out_pdf.open("wb") as f:
        writer.write(f)

# ----------------------------------------------------------------------

if __name__ == "__main__":
    data   = json.loads(FILE_DATA.read_text(encoding="utf-8"))
    coords = json.loads(FILE_COORDS.read_text(encoding="utf-8"))
    ovl = gerar_overlay(data, coords)
    aplicar_fundo(ovl, FILE_BG, FILE_OUT)
    print("✅ PDF gerado →", FILE_OUT)
