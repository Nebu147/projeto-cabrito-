from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Dict, Any

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from PyPDF2 import PdfReader, PdfWriter

"""
Como usar (PowerShell):
python .\gera_ticket.py --bg .\bg_ticket-APAGADO.pdf --coords .\coords_ticket_100_com_texto.json --out .\ticket_final.pdf --invert-y --baseline-fix 0.30 --proof

Dicas rápidas:
- Use --invert-y porque seu JSON foi medido "a partir do topo".
- Se precisar descer/subir tudo um tico, ajuste --baseline-fix (0.28–0.36).
- Para ajustar só um campo, adicione "dx" e/ou "dy" no próprio item do JSON.
"""

# Campos numéricos da coluna direita (alinhados pelo mesmo X)
RIGHT_KEYS = {
    "tarifa_valor", "taxa_embarque_valor", "pedagio_valor",
    "valor_total_valor", "desconto_valor", "valor_a_pagar_valor",
    "valor_pag_valor", "troco_valor",
}

def read_page_size(pdf_path: Path) -> tuple[float, float]:
    r = PdfReader(str(pdf_path))
    p = r.pages[0]
    box = p.cropbox or p.mediabox
    return float(box.right) - float(box.left), float(box.top) - float(box.bottom)

def baseline_fix(pt: float, factor: float) -> float:
    # ReportLab desenha na linha de base; Acrobat/GIMP dão o topo da caixa
    return factor * pt  # 0.28–0.36 costuma funcionar (padrão 0.30)

def compute_col_r(coords: Dict[str, Any], sx: float, page_w: float) -> float:
    xs = []
    for k in RIGHT_KEYS:
        if k in coords:
            pos = coords[k].get("pos", [None, None])[0]
            if isinstance(pos, (int, float)):
                xs.append(float(pos) * sx)
    return max(xs) if xs else 0.89 * page_w

def draw_text(c: canvas.Canvas, text: str, x: float, y: float, font: str, pt: float, align: str):
    try:
        c.setFont(font, pt)
    except Exception:
        c.setFont("Helvetica", pt)
    a = (align or "left").lower()
    if a == "right":
        c.drawRightString(x, y, text)
    elif a == "center":
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)

def main():
    p = ArgumentParser(description="Gera ticket final sobre um PDF de fundo (invert-y, baseline-fix, prova).")
    p.add_argument("--bg", required=True, help="PDF de fundo (template)")
    p.add_argument("--coords", required=True, help="JSON com coordenadas e estilos")
    p.add_argument("--out", default="ticket_final.pdf", help="PDF de saída")
    p.add_argument("--invert-y", action="store_true", help="Use se coords vieram do topo (PNG/Acrobat topo)")
    p.add_argument("--proof", action="store_true", help="Desenha marcadores/caixas de debug")
    p.add_argument("--baseline-fix", type=float, default=0.30, help="Fator da correção de baseline (0.28–0.36)")
    args = p.parse_args()

    bg = Path(args.bg)
    coords_path = Path(args.coords)
    out_path = Path(args.out)

    with coords_path.open("r", encoding="utf-8") as f:
        coords: Dict[str, Any] = json.load(f)

    page_w, page_h = read_page_size(bg)
    ref_w = float(coords.get("_ref_width", 0))
    ref_h = float(coords.get("_ref_height", 0))
    if not ref_w or not ref_h:
        raise ValueError("JSON precisa conter _ref_width e _ref_height")

    sx, sy = page_w / ref_w, page_h / ref_h
    col_r = compute_col_r(coords, sx, page_w)

    overlay_tmp = out_path.with_name("__overlay_tmp.pdf")
    c = canvas.Canvas(str(overlay_tmp), pagesize=(page_w, page_h))

    for name, meta in coords.items():
        if name.startswith("_"):
            continue

        text = str(meta.get("texto", ""))
        font = meta.get("font", "Helvetica")
        pt = float(meta.get("pt", 22))
        align = meta.get("align", "left")
        x_px, y_px = meta.get("pos", [0, 0])

        # Converte de px (mockup) para pt (PDF)
        X = float(x_px) * sx
        Y = float(y_px) * sy

        # Inversão do Y + baseline com sinal correto
        if args.invert_y:
            # coords vieram do TOPO → inverte y e DESCE o baseline
            Y = page_h - Y
            Y -= baseline_fix(pt, args.baseline_fix)
        else:
            # coords já no sistema do PDF (pé) → SOBE o baseline
            Y += baseline_fix(pt, args.baseline_fix)

        # Microajustes opcionais por campo (em px do mockup)
        # positivos DESCEM quando --invert-y (e sobem quando não inverte)
        dx_px = float(meta.get("dx", 0))
        dy_px = float(meta.get("dy", 0))
        X += dx_px * sx
        Y += (-dy_px * sy) if args.invert_y else (dy_px * sy)

        # Desenho do texto com alinhamento
        if name in RIGHT_KEYS:
            draw_text(c, text, col_r, Y, font, pt, "right")
        else:
            draw_text(c, text, X, Y, font, pt, align)

        # Modo prova: marcador e caixa do texto
        if args.proof:
            c.setLineWidth(0.3)
            # marcador da âncora
            anchor_x = col_r if name in RIGHT_KEYS else X
            c.rect(anchor_x - 1.5, Y - 1.5, 3, 3, stroke=1, fill=0)
            # caixa do texto (estimada pela largura da fonte)
            w = pdfmetrics.stringWidth(
                text,
                font if font in pdfmetrics.getRegisteredFontNames() else "Helvetica",
                pt,
            )
            pad = 2
            if name in RIGHT_KEYS:
                x_box = col_r - w
            else:
                if align == "center":
                    x_box = X - (w / 2)
                elif align == "right":
                    x_box = X - w
                else:
                    x_box = X
            c.setDash(2, 2)
            c.rect(x_box - pad, Y - pad, w + 2 * pad, pt + 2 * pad, stroke=1, fill=0)
            c.setDash()

    c.save()

    # Mescla overlay com o fundo
    r_bg = PdfReader(str(bg))
    r_ov = PdfReader(str(overlay_tmp))
    page = r_bg.pages[0]
    page.merge_page(r_ov.pages[0])
    w = PdfWriter()
    w.add_page(page)
    with out_path.open("wb") as f:
        w.write(f)

    try:
        overlay_tmp.unlink()
    except Exception:
        pass

    print(f"✅ Gerado: {out_path}")
    print(f"   Fundo:  {bg.name}")
    print(f"   Coords: {coords_path.name}")
    print(f"   Escalas -> X: {sx:.6f}  Y: {sy:.6f}  (ref: {ref_w}x{ref_h} px)")

if __name__ == "__main__":
    main()
