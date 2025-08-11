from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Dict, Any

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from PyPDF2 import PdfReader, PdfWriter

def read_page_size(pdf_path: Path) -> tuple[float, float]:
    r = PdfReader(str(pdf_path))
    p = r.pages[0]
    box = p.cropbox or p.mediabox
    return float(box.right) - float(box.left), float(box.top) - float(box.bottom)

def baseline_fix(pt: float, factor: float = 0.30) -> float:
    return factor * pt

def main():
    p = ArgumentParser(description="Overlay de caixas para validar coordenadas")
    p.add_argument("--bg", required=True)
    p.add_argument("--coords", required=True)
    p.add_argument("--out", default="check.pdf")
    p.add_argument("--invert-y", action="store_true")
    args = p.parse_args()

    bg = Path(args.bg); coords_path = Path(args.coords); out_path = Path(args.out)
    page_w, page_h = read_page_size(bg)

    coords: Dict[str, Any] = json.loads(coords_path.read_text(encoding="utf-8"))
    ref_w = float(coords.get("_ref_width", 0))
    ref_h = float(coords.get("_ref_height", 0))
    if not ref_w or not ref_h:
        raise ValueError("JSON precisa de _ref_width/_ref_height")
    sx, sy = page_w/ref_w, page_h/ref_h

    tmp = out_path.with_name("__overlay_valida_tmp.pdf")
    c = canvas.Canvas(str(tmp), pagesize=(page_w, page_h))
    c.setLineWidth(0.5); c.setStrokeColor(colors.red)

    for k, meta in coords.items():
        if k.startswith("_"):
            continue
        pt = float(meta.get("pt", 22))
        x_px, y_px = meta.get("pos", [0, 0])
        x_pt = float(x_px)*sx
        y_pt = float(y_px)*sy
        if args.invert_y:
            y_pt = page_h - y_pt
        y_pt += baseline_fix(pt)
        # caixinha estimada
        c.rect(x_pt, y_pt, pt*4, pt*1.2, stroke=1, fill=0)

    c.save()
    r_bg = PdfReader(str(bg))
    r_ov = PdfReader(str(tmp))
    page = r_bg.pages[0]
    page.merge_page(r_ov.pages[0])
    w = PdfWriter()
    w.add_page(page)
    with out_path.open("wb") as f:
        w.write(f)

    try:
        tmp.unlink()
    except Exception:
        pass

    print(f"✅ Debug gerado em: {out_path}")

if __name__ == "__main__":
    main()
