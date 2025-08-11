# src/gera_controle.py  —  CONTROLE 80x130 mm (sem baseline, centralização por grupos)
from __future__ import annotations

import json
import re
from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
print(">> usando src/gera_controle.py (build com KEY_MAP)")

# topo do arquivo (depois dos imports)
KEY_MAP = {
    "origem_valor":        ["origem_valor", "origem"],
    "destino_valor":       ["destino_valor", "destino"],
    "data_valor":          ["data_valor", "data"],
    "horario_valor":       ["horario_valor", "hora", "horario"],
    "poltrona_valor":      ["poltrona_valor", "poltrona"],
    "plataforma_valor":    ["plataforma_valor", "plataforma"],
    "prefixo_valor":       ["prefixo_valor", "prefixo"],
    "linha_valor_1":       ["linha_valor_1", "linha1", "linha"],
    "linha_valor_2":       ["linha_valor_2", "linha2"],
    "tipo_valor":          ["tipo_valor", "tipo"],
    "passageiro_valor_1":  ["passageiro_valor_1", "passageiro", "passageiro_nome"],
    "passageiro_valor_2":  ["passageiro_valor_2", "passageiro_2", "sobrenome"],
}

# -------- util --------
def swidth(text: str, font: str, pt: float) -> float:
    if font not in pdfmetrics.getRegisteredFontNames():
        font = "Helvetica"
    return pdfmetrics.stringWidth(text or "", font, pt)

def get_xy_mm(pos: Any) -> Tuple[float, float]:
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        return float(pos[0]), float(pos[1])
    if isinstance(pos, dict) and "x" in pos and "y" in pos:
        return float(pos["x"]), float(pos["y"])
    raise ValueError(f"pos inválido: {pos!r}")

def base_key(name: str) -> str:
    # remove _valor e _<n> do final
    return re.sub(r"(?:_valor)?(?:_\d+)?$", "", name)

def resolve_text(name: str, meta: dict, dados: Dict[str, Any]) -> str:
    """
    Resolve o texto para um campo do coords:
    - tenta chaves mapeadas em KEY_MAP para esse 'name';
    - se não houver mapeamento, tenta a chave exata;
    - por fim tenta a chave-base (sem _valor/_n);
    - senão, fica com o texto do coords.
    """
    txt = str(meta.get("texto", ""))

    # 1) mapeamento explícito
    for k in KEY_MAP.get(name, []):
        if k in dados and str(dados[k]).strip():
            return str(dados[k])

    # 2) chave exata
    if name in dados and str(dados[name]).strip():
        return str(dados[name])

    # 3) chave-base (apenas para não numerados)
    if not re.search(r"_\d+$", name):
        kbase = re.sub(r"(?:_valor)?(?:_\d+)?$", "", name)
        if kbase in dados and str(dados[kbase]).strip():
            return str(dados[kbase])

    # 4) fallback: texto do coords
    return txt

    return txt

# -------- grupos centralizados (uma linha por grupo) --------
GRUPOS: List[Tuple[str, ...]] = [
    ("origem_label",  "origem_valor"),
    ("destino_label", "destino_valor"),
    ("data_label",    "data_valor", "horario_label", "horario_valor"),
    ("poltrona_label","poltrona_valor","plataforma_label","plataforma_valor"),
    ("prefixo_label", "prefixo_valor", "linha_label", "linha_valor_1"),  # SEM linha_valor_2
    ("tipo_label",    "tipo_valor"),
]

def gerar_overlay_mm(
    dados: Dict[str, Any],
    coords: Dict[str, Any],
    page_w_mm: float,
    page_h_mm: float,
    invert_y: bool,
) -> BytesIO:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w_mm * mm, page_h_mm * mm))
    usados = set()

    # --- linhas centralizadas (grupos) ---
    for grupo in GRUPOS:
        y_top_mm = get_xy_mm(coords[grupo[0]]["pos"])[1]
        y_mm = (page_h_mm - y_top_mm) if invert_y else y_top_mm

        partes: List[str] = []
        fontes: List[str] = []
        pts: List[float] = []

        for name in grupo:
            meta = coords[name]
            font = meta.get("font", "Helvetica")
            pt = float(meta.get("pt", 8))
            txt = resolve_text(name, meta, dados)
            if name.endswith("_valor"):
                font = "Helvetica-Bold"
            partes.append(txt); fontes.append(font); pts.append(pt)
            usados.add(name)

        total_w = sum(swidth(t, f, p) for t, f, p in zip(partes, fontes, pts))
        x_pt = ((page_w_mm * mm) - total_w) / 2.0
        for t, f, p in zip(partes, fontes, pts):
            try: c.setFont(f, p)
            except Exception: c.setFont("Helvetica", p)
            c.drawString(x_pt, y_mm * mm, t)
            x_pt += swidth(t, f, p)

    # --- demais campos (ex.: PASSAGEIRO, linha_valor_2 etc.) ---
    for name, meta in coords.items():
        if name in usados or name.startswith("_"):
            continue
        font  = meta.get("font", "Helvetica")
        pt    = float(meta.get("pt", 8))
        align = (meta.get("align", "left") or "left").lower()
        x_mm, y_top_mm = get_xy_mm(meta.get("pos", [0, 0]))
        y_mm = (page_h_mm - y_top_mm) if invert_y else y_top_mm

        txt = resolve_text(name, meta, dados)
        if not txt.strip():
            continue

        try: c.setFont(font, pt)
        except Exception: c.setFont("Helvetica", pt)

        if align == "center":
            c.drawCentredString((page_w_mm * mm) / 2, y_mm * mm, txt)
        elif align == "right":
            c.drawRightString(x_mm * mm, y_mm * mm, txt)
        else:
            c.drawString(x_mm * mm, y_mm * mm, txt)

    c.showPage(); c.save(); buf.seek(0); return buf

def mesclar_overlay(bg_pdf: Path, overlay: BytesIO, out_pdf: Path):
    r_bg = PdfReader(str(bg_pdf)); r_ov = PdfReader(overlay)
    page = r_bg.pages[0]; page.merge_page(r_ov.pages[0])
    w = PdfWriter(); w.add_page(page)
    with out_pdf.open("wb") as f: w.write(f)

def main():
    ap = ArgumentParser(description="CONTROLE 80x130 mm (sem baseline, centralização por grupos)")
    ap.add_argument("--bg", required=True)
    ap.add_argument("--coords", required=True)
    ap.add_argument("--vars")
    ap.add_argument("--out", default="controle_80x130.pdf")
    ap.add_argument("--page-w-mm", type=float, default=80.0)
    ap.add_argument("--page-h-mm", type=float, default=130.0)
    ap.add_argument("--invert-y", action="store_true")
    args = ap.parse_args()

    bg = Path(args.bg)
    coords = json.loads(Path(args.coords).read_text(encoding="utf-8"))
    dados: Dict[str, Any] = {}
    if args.vars and Path(args.vars).exists():
        dados = json.loads(Path(args.vars).read_text(encoding="utf-8"))

    overlay = gerar_overlay_mm(dados, coords, args.page_w_mm, args.page_h_mm, args.invert_y)
    outp = Path(args.out); mesclar_overlay(bg, overlay, outp)
    print(f"✅ Gerado: {outp}\n   Fundo:  {bg.name}\n   Página: {args.page_w_mm}×{args.page_h_mm} mm")

if __name__ == "__main__":
    main()
