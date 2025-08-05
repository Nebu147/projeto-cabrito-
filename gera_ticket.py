"""
gera_ticket.py – gera o ticket usando bg_ticket_full.pdf
-------------------------------------------------------
• Lê largura/altura REAIS da página do fundo.
• Coordenadas no coords_ticket.json devem estar em PONTOS
  (mesmos valores em px do GIMP, porque 1 px = 1 pt).
• Valores com _valor/_valor_1/_valor_2 saem em Helvetica-Bold.
"""

import json
from io import BytesIO
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

# Caminhos
FILE_BG     = Path("bg_ticket_full.pdf")
FILE_COORDS = Path("coords_ticket.json")
FILE_DATA   = Path("ticket.json")
FILE_OUT    = Path("ticket.pdf")

# ----------------------------------------------------------------------
# Descobre tamanho real do fundo
page_bg = PdfReader(str(FILE_BG)).pages[0]
PAGE_W_PT = float(page_bg.mediabox[2])
PAGE_H_PT = float(page_bg.mediabox[3])

# Grupos a centralizar  (exemplo – ajuste ao seu coords_ticket.json)
GRUPOS = [
    ("origem_label", "origem_valor"),
    ("destino_label", "destino_valor"),
    ("data_label", "data_valor", "horario_label", "horario_valor"),
    ("poltrona_label", "poltrona_valor"),
    ("tipo_label", "tipo_valor"),
    ("passageiro_label", "passageiro_valor_1")
]

# ----------------------------------------------------------------------
def draw_mixed(canv, partes, fontes, pts, y_pt):
    """Centraliza linha somando larguras."""
    total = sum(stringWidth(t, f, p) for t, f, p in zip(partes, fontes, pts))
    x_pt = (PAGE_W_PT - total) / 2
    for texto, fonte, pt in zip(partes, fontes, pts):
        canv.setFont(fonte, pt)
        canv.drawString(x_pt, y_pt, texto)
        x_pt += stringWidth(texto, fonte, pt)

# ----------------------------------------------------------------------
def gerar_overlay(dados, coords):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W_PT, PAGE_H_PT))
    usados = set()

    # Linhas centralizadas
    for grupo in GRUPOS:
        partes, fontes, pts = [], [], []
        for chave in grupo:
            meta  = coords[chave]
            texto = meta["texto"]
            if "_valor" in chave:
                campo = chave.replace("_valor", "").replace("_1", "").replace("_2", "_2")
                texto = dados.get(campo, texto)
                fontes.append("Helvetica-Bold")
            else:
                fontes.append(meta.get("font", "Helvetica"))
            partes.append(texto)
            pts.append(meta.get("pt", 8))
            usados.add(chave)
        y_pt = PAGE_H_PT - coords[grupo[0]]["pos"][1]
        draw_mixed(c, partes, fontes, pts, y_pt)

    # Outros campos
    for chave, meta in coords.items():
        if chave in usados:
            continue
        texto = meta["texto"]
        if "_valor" in chave:
            campo = chave.replace("_valor", "").replace("_1", "").replace("_2", "_2")
            texto = dados.get(campo, texto)
        if not texto.strip():
            continue
        fonte   = meta.get("font", "Helvetica")
        tamanho = meta.get("pt", 8)
        align   = meta.get("align", "left")
        x_pt, y_top_pt = meta["pos"]
        y_pt = PAGE_H_PT - y_top_pt
        c.setFont(fonte, tamanho)
        if align == "center":
            c.drawCentredString(PAGE_W_PT/2, y_pt, texto)
        else:
            c.drawString(x_pt, y_pt, texto)

    c.showPage(); c.save(); buf.seek(0)
    return buf

# ----------------------------------------------------------------------
if __name__ == "__main__":
    coords = json.loads(FILE_COORDS.read_text(encoding="utf-8"))
    data   = json.loads(FILE_DATA.read_text(encoding="utf-8"))

    overlay = gerar_overlay(data, coords)

    bg_page = PdfReader(str(FILE_BG)).pages[0]
    bg_page.merge_page(PdfReader(overlay).pages[0])

    writer = PdfWriter(); writer.add_page(bg_page)
    with FILE_OUT.open("wb") as f:
        writer.write(f)

    print("✅ ticket gerado →", FILE_OUT)
