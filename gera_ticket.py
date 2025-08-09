# -*- coding: utf-8 -*-
"""
Gera o ticket final com:
- Autoescala do mockup para o fundo
- Fallback de fonte quando o campo do mockup está com "Automático"
- Nudge opcional (dx/dy) para microajustes

Requisitos:
pip install reportlab PyPDF2

Arquivos esperados na mesma pasta:
- bg_ticket-APAGADO.pdf
- coords_ticket_100_com_texto.json
- ticket_mockup_numbered.pdf   (o seu PDF com os campos de formulário)

Saída: ticket_final.pdf
"""

import re
import json
from pathlib import Path
from typing import Dict, Tuple, Optional

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics

# -------- CONFIG --------
FILE_BG = Path("bg_ticket-APAGADO.pdf")            # fundo
FILE_COORDS = Path("coords_ticket_100_com_texto.json")
FILE_MOCKUP = Path("ticket_mockup_numbered.pdf")   # PDF com os campos numerados
OUTPUT = Path("ticket_final.pdf")

# Quando o tamanho da fonte do mockup está AUTOMÁTICO,
# estimar pt a partir da altura da caixa * este fator:
AUTO_FONT_SCALE = 0.82  # ajuste fino visual
USE_MOCKUP_PT_WHEN_AVAILABLE = True  # se o mockup tiver pt fixo, usa ele

# Nudge global (aplicado já no "mundo do fundo", depois da autoescala):
NUDGE_DX = 0.0
NUDGE_DY = 0.0

# -------- Utils --------
def _num(x):
    try:
        # PyPDF2 pode retornar NameObject/FloatObject/etc.
        return float(str(x))
    except Exception:
        return float(x)

def parse_DA_to_pt(da: str) -> Optional[float]:
    """
    /DA pode vir algo como: '/Helv 0 g 0 G 22 Tf' ou '22 Tf'
    Retorna o número antes de 'Tf', se houver.
    """
    if not da:
        return None
    m = re.search(r"([\d\.]+)\s+Tf\b", da)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None

def extract_mockup_fields(mockup_path: Path) -> Tuple[Dict[str, dict], Tuple[float,float]]:
    """
    Lê os campos do PDF do mockup e retorna:
    - dict[name] = {'rect':(x1,y1,x2,y2), 'pt':<float|None>, 'align': 'left|center|right'}
    - tamanho da página (w,h) do mockup
    """
    fields = {}
    reader = PdfReader(str(mockup_path))
    page = reader.pages[0]
    try:
        acro = reader.trailer["/Root"]["/AcroForm"]
        raw_fields = acro.get("/Fields", [])
    except Exception:
        raw_fields = []

    # tamanho do mockup
    w = float(page.mediabox.width)
    h = float(page.mediabox.height)

    for f in raw_fields:
        fld = f.get_object()
        name = fld.get("/T")
        rect = fld.get("/Rect")
        da = fld.get("/DA")
        q = fld.get("/Q")  # 0 left, 1 center, 2 right

        if not name or not rect:
            continue

        x1, y1, x2, y2 = map(_num, rect)
        pt = parse_DA_to_pt(da)

        if q == 1:
            align = "center"
        elif q == 2:
            align = "right"
        else:
            align = "left"

        fields[name] = {
            "rect": (x1, y1, x2, y2),
            "pt": pt,  # None quando Automático
            "align": align
        }

    return fields, (w, h)

def load_coords(coords_path: Path) -> dict:
    with open(coords_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_bg_size(bg_path: Path) -> Tuple[float, float]:
    r = PdfReader(str(bg_path))
    p = r.pages[0]
    return float(p.mediabox.width), float(p.mediabox.height)

def build_overlay(
    bg_size: Tuple[float,float],
    coords: dict,
    ref_size: Tuple[float,float],
    mockup_fields: Dict[str, dict],
    nudge_dx: float = 0.0,
    nudge_dy: float = 0.0,
    auto_font_scale: float = 0.82,
    use_mockup_pt: bool = True,
    overlay_path: Path = Path("overlay_tmp.pdf"),
):
    """
    Desenha os textos escalando do espaço do mockup(ref) para o espaço do fundo(bg).
    Se pt vier ausente/"auto", calcula do mockup: usa /DA; se não existir, estima por altura do Rect.
    """
    bg_w, bg_h = bg_size
    ref_w, ref_h = ref_size

    sx = bg_w / ref_w
    sy = bg_h / ref_h

    c = canvas.Canvas(str(overlay_path), pagesize=(bg_w, bg_h))

    # Tenta usar Helvetica / Helvetica-Bold nativos
    # (reportlab já tem mapeados; se quiser trocar, registrar aqui)
    for key, item in coords.items():
        texto = item.get("texto", "")
        font_name = item.get("font", "Helvetica")
        pt_cfg = item.get("pt", None)   # pode ser numérico ou "auto"
        x_ref, y_ref = item.get("pos", [0, 0])
        align = item.get("align", "left")

        # Converte posição do mockup(ref) -> fundo(bg) e inverte Y
        x_bg = x_ref * sx + nudge_dx
        y_bg_from_bottom = y_ref * sy + nudge_dy
        y_bg = bg_h - y_bg_from_bottom  # origem do reportlab em baixo

        # Tamanho da fonte: 1) coords, 2) mockup /DA, 3) mockup Rect->estimativa
        pt_final = None
        # 1) se coords já trouxe pt numérico, usa
        if isinstance(pt_cfg, (int, float)) and pt_cfg > 0:
            pt_final = float(pt_cfg) * sy  # escala vertical
        # 2) tentar pt do mockup
        if (pt_final is None or pt_cfg == "auto") and key in mockup_fields:
            mf = mockup_fields[key]
            if use_mockup_pt and mf.get("pt"):
                pt_final = float(mf["pt"]) * sy
        # 3) estimar pelo Rect do mockup
        if pt_final is None and key in mockup_fields:
            x1, y1, x2, y2 = mockup_fields[key]["rect"]
            rect_h = abs(y2 - y1)
            # fonte ≈ altura da caixa * fator
            pt_final = (rect_h * auto_font_scale) * sy

        # fallback duro se tudo falhar
        if pt_final is None:
            pt_final = 18.0 * sy

        # ajustar alinhamento
        c.setFont(font_name, pt_final)
        if align == "center":
            c.drawCentredString(x_bg, y_bg, texto)
        elif align == "right":
            c.drawRightString(x_bg, y_bg, texto)
        else:
            c.drawString(x_bg, y_bg, texto)

    c.save()
    return sx, sy

def compose(bg_path: Path, overlay_path: Path, out_path: Path):
    bg_reader = PdfReader(str(bg_path))
    ov_reader = PdfReader(str(overlay_path))
    writer = PdfWriter()

    page = bg_reader.pages[0]
    page.merge_page(ov_reader.pages[0])
    writer.add_page(page)

    with open(out_path, "wb") as f:
        writer.write(f)

def main():
    # ler fundo + coord + mockup
    coords = load_coords(FILE_COORDS)
    mock_fields, (ref_w, ref_h) = extract_mockup_fields(FILE_MOCKUP)
    bg_w, bg_h = get_bg_size(FILE_BG)

    # log
    print("== Ticket generator ==")
    print(f"Fundo : {FILE_BG}  ({bg_w:.1f} x {bg_h:.1f})")
    print(f"Mockup: {FILE_MOCKUP}  ({ref_w:.1f} x {ref_h:.1f})")

    # overlay
    overlay_tmp = Path("overlay_tmp.pdf")
    sx, sy = build_overlay(
        (bg_w, bg_h),
        coords,
        (ref_w, ref_h),
        mock_fields,
        nudge_dx=NUDGE_DX,
        nudge_dy=NUDGE_DY,
        auto_font_scale=AUTO_FONT_SCALE,
        use_mockup_pt=USE_MOCKUP_PT_WHEN_AVAILABLE,
        overlay_path=overlay_tmp,
    )
    print(f"Escala aplicada: sx={sx:.6f} sy={sy:.6f} | nudge dx={NUDGE_DX:.2f} dy={NUDGE_DY:.2f}")

    # merge
    compose(FILE_BG, overlay_tmp, OUTPUT)
    print(f"✅ Bilhete gerado: {OUTPUT}")

if __name__ == "__main__":
    main()