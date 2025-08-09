# gera_ticket_autoscale.py
# Gera ticket_final.pdf sobre o fundo bg_ticket-APAGADO.pdf
# Lê coordenadas em pixels do arquivo JSON contendo _ref_width/_ref_height.
#
# Requisitos: reportlab, PyPDF2
#   pip install reportlab PyPDF2

import json
from pathlib import Path
from typing import Dict, Any

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.ttfonts import TTFont  # (não usado, mas útil se quiser registrar TTF)
from reportlab.lib.pagesizes import letter     # (não usado, só para IDE calar)
from PyPDF2 import PdfReader, PdfWriter

# -----------------------------
# CONFIG
# -----------------------------
FILE_BG = Path("bg_ticket-APAGADO.pdf")         # fundo (PDF nativo)
FILE_COORDS = Path("coords_ticket_100_com_texto.json")  # seu JSON com _ref_width/_ref_height
OUTPUT_PDF = Path("ticket_final.pdf")

# Opcional: desenhar caixas de debug (retângulos) onde cada campo será impresso
DEBUG_BOXES = False

# Nudge/offset global (desativado a pedido)
NUDGE_X = 0.0
NUDGE_Y = 0.0

# Se quiser manter o tamanho de fonte do JSON “fixo” (sem escalar com a página), troque para True
KEEP_FONT_PT = False

# -----------------------------
# Helpers
# -----------------------------
def load_coords(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "_ref_width" not in data or "_ref_height" not in data:
        raise ValueError("O JSON precisa conter _ref_width e _ref_height (pixels de referência).")
    return data

def get_page_size_from_pdf(pdf_path: Path):
    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        raise ValueError("PDF de fundo sem páginas.")
    page = reader.pages[0]
    # PyPDF2 usa user space units (1/72 in). Vamos trabalhar nessas unidades.
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    return width, height

def draw_one_field(c: canvas.Canvas,
                   txt: str,
                   font: str,
                   pt: float,
                   x_px: float,
                   y_px: float,
                   align: str,
                   scale_x: float,
                   scale_y: float,
                   page_h_points: float):
    """Desenha um texto posicionando a partir de coords em pixels (mockup).
       Converte (x_px, y_px) para pontos usando scale_x/scale_y e inverte Y.
    """
    # Escala de fonte: média dos eixos para evitar distorção
    pt_eff = pt if KEEP_FONT_PT else pt * (scale_x + scale_y) / 2.0

    # Converte posição
    x_pt = (x_px * scale_x) + NUDGE_X
    # inverter Y: o JSON tem origem no topo; PDF tem origem embaixo
    y_pt = (page_h_points - (y_px * scale_y)) + NUDGE_Y

    # Define fonte
    # Aceita "Helvetica" e "Helvetica-Bold" (nativo do reportlab)
    try:
        c.setFont(font, pt_eff)
    except:
        c.setFont("Helvetica", pt_eff)

    # Alinhamento
    if align == "center":
        c.drawCentredString(x_pt, y_pt, txt)
    elif align == "right":
        c.drawRightString(x_pt, y_pt, txt)
    else:
        c.drawString(x_pt, y_pt, txt)

    if DEBUG_BOXES:
        # Retângulo de referência (aproximado)
        w = pdfmetrics.stringWidth(txt, c._fontname, pt_eff)
        h = pt_eff * 1.2
        # Ancoragem depende do align:
        if align == "center":
            x0 = x_pt - w / 2
        elif align == "right":
            x0 = x_pt - w
        else:
            x0 = x_pt
        y0 = y_pt - h * 0.25
        c.setLineWidth(0.5)
        c.rect(x0, y0, w, h)

# -----------------------------
# Main
# -----------------------------
def main():
    if not FILE_BG.exists():
        raise FileNotFoundError(f"Fundo não encontrado: {FILE_BG}")

    coords = load_coords(FILE_COORDS)

    ref_w = float(coords["_ref_width"])
    ref_h = float(coords["_ref_height"])

    # Tamanho da página real do PDF de fundo (em pontos)
    page_w_pt, page_h_pt = get_page_size_from_pdf(FILE_BG)

    # Escalas de conversão de pixel(ref) -> pontos
    scale_x = page_w_pt / ref_w
    scale_y = page_h_pt / ref_h

    # Cria um overlay em branco no tamanho da página
    overlay_path = OUTPUT_PDF.with_name("__overlay_tmp.pdf")
    c = canvas.Canvas(str(overlay_path), pagesize=(page_w_pt, page_h_pt))

    # Percorre campos
    for key, props in coords.items():
        if key.startswith("_ref_"):
            continue  # meta

        txt = props.get("texto", "")
        font = props.get("font", "Helvetica")
        pt = float(props.get("pt", 12))
        pos = props.get("pos", [0, 0])
        if not isinstance(pos, (list, tuple)) or len(pos) != 2:
            continue

        x_px, y_px = float(pos[0]), float(pos[1])
        align = props.get("align", "left")

        draw_one_field(
            c=c,
            txt=txt,
            font=font,
            pt=pt,
            x_px=x_px,
            y_px=y_px,
            align=align,
            scale_x=scale_x,
            scale_y=scale_y,
            page_h_points=page_h_pt,
        )

    c.save()

    # Mescla overlay no fundo
    reader_bg = PdfReader(str(FILE_BG))
    reader_ov = PdfReader(str(overlay_path))
    writer = PdfWriter()

    page = reader_bg.pages[0]
    page.merge_page(reader_ov.pages[0])
    writer.add_page(page)

    with open(OUTPUT_PDF, "wb") as f:
        writer.write(f)

    # Limpeza simples do overlay temporário (opcional)
    try:
        overlay_path.unlink()
    except:
        pass

    print(f"✅ Gerado: {OUTPUT_PDF}")
    print(f"   Fundo:  {FILE_BG}")
    print(f"   Coords: {FILE_COORDS}")
    print(f"   Escalas -> X: {scale_x:.6f}  Y: {scale_y:.6f}  (ref: {ref_w}x{ref_h} px)")

if __name__ == "__main__":
    main()