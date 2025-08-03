#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import argparse
from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from PyPDF2 import PdfReader, PdfWriter

# -------------------------------------------------------------------------
# LOGGING
# -------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# -------------------------------------------------------------------------
# FONTES
# -------------------------------------------------------------------------
# Helvetica já está embutida no PDF, mas se quiser registrar outra:
# pdfmetrics.registerFont(TTFont("OpenSans", "fonts/OpenSans-Regular.ttf"))
FONTS = {
    "normal": "Helvetica",
    "bold": "Helvetica-Bold",
}

# -------------------------------------------------------------------------
# UTILITÁRIOS
# -------------------------------------------------------------------------
def mm2pt(value_mm: float) -> float:
    """Converte milímetros para pontos."""
    return value_mm * mm

def load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Não consegui ler JSON em {path}: {e}")
        raise SystemExit(1)

# -------------------------------------------------------------------------
# OVERLAY E MERGE
# -------------------------------------------------------------------------
def make_overlay(data: dict, coords: dict, page_w: float, page_h: float, font_sz: int) -> BytesIO:
    """
    Cria um PDF em memória com:
      1) retângulos brancos (se coords[field]["mask"] for True)
      2) texto nos coords[field] (em mm a partir do canto inferior esquerdo)
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(mm2pt(page_w), mm2pt(page_h)))
    c.setFillColorRGB(1, 1, 1)  # branco

    # primeiro, máscara (se existir campo "mask" no coords)
    for key, val in coords.items():
        if val.get("mask"):  # coords[key] = {"pos":[x,y], "mask": [w,h]}
            x_mm, y_mm = val["pos"]
            w_mm, h_mm = val["mask"]
            c.rect(mm2pt(x_mm), mm2pt(y_mm), mm2pt(w_mm), mm2pt(h_mm), fill=1, stroke=0)

    # segundo, texto
    for key, val in coords.items():
        if key not in data:
            continue
        text = str(data[key])
        x_mm, y_mm = val["pos"]
        c.setFont(FONTS.get("bold"), font_sz)
        c.drawString(mm2pt(x_mm), mm2pt(y_mm), text)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

def merge_pdfs(template_pdf: str, overlay_buf: BytesIO, out_pdf: str):
    """Mescla overlay_buf (1 página) sobre template_pdf."""
    reader_bg = PdfReader(template_pdf)
    reader_ov = PdfReader(overlay_buf)
    writer = PdfWriter()

    page_bg = reader_bg.pages[0]
    page_ov = reader_ov.pages[0]

    page_bg.merge_page(page_ov)
    writer.add_page(page_bg)

    with open(out_pdf, "wb") as f:
        writer.write(f)

# -------------------------------------------------------------------------
# FLUXO PRINCIPAL
# -------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Gera PDF de bilhete/controle.")
    p.add_argument("--template", required=True, help="PDF de fundo (template)")
    p.add_argument("--data", required=True, help="JSON com valores dos campos")
    p.add_argument("--coords", required=True, help="JSON com coords e máscara")
    p.add_argument("--out", required=True, help="Arquivo PDF de saída")
    p.add_argument("--page-w", type=float, required=True, help="largura mm")
    p.add_argument("--page-h", type=float, required=True, help="altura mm")
    p.add_argument("--font-size", type=int, default=9, help="tamanho da fonte (pt)")
    args = p.parse_args()

    logging.info(f"Lendo dados: {args.data}")
    data = load_json(args.data)

    logging.info(f"Lendo coords: {args.coords}")
    coords = load_json(args.coords)

    logging.info("Construindo overlay...")
    overlay = make_overlay(data, coords, args.page_w, args.page_h, args.font_size)

    logging.info(f"Misturando sobre {args.template} → {args.out}")
    merge_pdfs(args.template, overlay, args.out)

    logging.info("Concluído.")

if __name__ == "__main__":
    main()