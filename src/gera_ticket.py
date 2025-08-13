from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Dict, Tuple

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from PyPDF2 import PdfReader, PdfWriter

# --------------------------- util ---------------------------

RIGHT_KEYS = {
    "tarifa_valor", "taxa_embarque_valor", "pedagio_valor",
    "valor_total_valor", "desconto_valor", "valor_a_pagar_valor",
    "valor_pag_valor", "troco_valor",
}

# Mapa: chave do COORDS -> chave(s) no ticket.json
KEY_MAP: Dict[str, Tuple[str, ...]] = {
    "bpe_numero_valor": ("bpe_numero",),
    "bpe_serie_valor":  ("bpe_serie",),
    "venda_valor":      ("venda", "venda:"),  # aceita os dois jeitos
    "origem_valor":     ("origem",),
    "destino_valor":    ("destino",),
    "data_valor":       ("data",),
    "horario_valor":    ("horario", "hora"),
    "poltrona_valor":   ("poltrona",),
    "plataforma_valor": ("plataforma",),
    "prefixo_valor":    ("prefixo",),

    # Linha: se vier linha1/linha2 usa; se vier só "linha", a 1a usa 'linha' e a 2a fica vazia
    "linha_valor_1":    ("linha1", "linha"),
    "linha_valor_2":    ("linha2",),

    "tipo_valor":       ("tipo",),

    "tarifa_valor":          ("tarifa",),
    "taxa_embarque_valor":   ("taxa_embarque",),
    "pedagio_valor":         ("pedagio",),
    "valor_total_valor":     ("valor_total",),
    "desconto_valor":        ("desconto",),
    "valor_a_pagar_valor":   ("valor_pagar",),
    "forma_pag_valor":       ("forma_pag",),
    "valor_pag_valor":       ("valor_pag",),
    "troco_valor":           ("troco",),

    "passageiro_valor_1": ("passageiro_cpf_nome",),
    "passageiro_valor_2": ("passageiro_sobrenome",),

    # pequenos (se usar)
    "bpe_numero_pequeno": ("bpe_numero",),
    "bpe_serie_pequeno":  ("bpe_serie",),
    "geracao_horario":    ("horario", "hora"),
}


def read_page_size(pdf_path: Path) -> Tuple[float, float]:
    r = PdfReader(str(pdf_path))
    p = r.pages[0]
    box = p.cropbox or p.mediabox
    return float(box.right) - float(box.left), float(box.top) - float(box.bottom)


def baseline_fix(pt: float, factor: float) -> float:
    # ReportLab desenha pela linha de base; Acrobat/GIMP dão o topo da caixa
    return factor * pt  # tipicamente 0.28–0.32 (ou 1.00 no seu caso)


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


def compute_col_r(coords: Dict[str, Any], sx: float, page_w: float) -> float:
    xs = []
    for k in RIGHT_KEYS:
        if k in coords:
            pos = coords[k].get("pos", [None, None])[0]
            if isinstance(pos, (int, float)):
                xs.append(float(pos) * sx)
    return max(xs) if xs else 0.89 * page_w


def get_first(vars_data: Dict[str, Any], keys: Tuple[str, ...]) -> str | None:
    for k in keys:
        if k in vars_data and str(vars_data[k]).strip():
            return str(vars_data[k])
    return None


# --------------------------- main ---------------------------

def main():
    p = ArgumentParser(description="Gera ticket final sobre um PDF de fundo (com invert-y, baseline-fix e prova).")
    p.add_argument("--bg", required=True, help="PDF de fundo (template).")
    p.add_argument("--coords", required=True, help="JSON com coordenadas e estilos.")
    p.add_argument("--vars", help="JSON com os valores do ticket (campos editáveis).")
    p.add_argument("--out", default="ticket_final.pdf", help="PDF de saída.")
    p.add_argument("--invert-y", action="store_true", help="Use se coords vieram do topo (PNG/Acrobat topo).")
    p.add_argument("--proof", action="store_true", help="Desenha marcadores/caixas de debug.")
    p.add_argument("--baseline-fix", type=float, default=0.30, help="Fator da correção de baseline (0.28–0.32).")
    args = p.parse_args()

    bg = Path(args.bg)
    coords_path = Path(args.coords)
    out_path = Path(args.out)

    with coords_path.open("r", encoding="utf-8") as f:
        coords: Dict[str, Any] = json.load(f)

    vars_data: Dict[str, Any] = {}
    if args.vars:
        vp = Path(args.vars)
        if vp.exists():
            with vp.open("r", encoding="utf-8") as f:
                vars_data = json.load(f)

    page_w, page_h = read_page_size(bg)
    ref_w = float(coords.get("_ref_width", 0))
    ref_h = float(coords.get("_ref_height", 0))
    if not ref_w or not ref_h:
        # se não tiver _ref_*, assume que pos[] já está em pontos (sem escala)
        ref_w, ref_h = page_w, page_h

    sx, sy = page_w / ref_w, page_h / ref_h
    col_r = compute_col_r(coords, sx, page_w)

    overlay_tmp = out_path.with_name("__overlay_tmp.pdf")
    c = canvas.Canvas(str(overlay_tmp), pagesize=(page_w, page_h))

    for name, meta in coords.items():
        if name.startswith("_"):
            continue

        # texto base do coords
        text = str(meta.get("texto", ""))

        # aplica valor do ticket.json se houver
        if name in KEY_MAP:
            v = get_first(vars_data, KEY_MAP[name])
            if v is not None:
                text = v
            # caso especial: se for linha_valor_2 e não houver linha2, fica vazio (não desenha "NORTE" herdado do coords)
            if name == "linha_valor_2" and v is None:
                text = ""

        font = meta.get("font", "Helvetica")
        pt = float(meta.get("pt", 22))
        align = meta.get("align", "left")
        x_px, y_px = meta.get("pos", [0, 0])

        # posição em pontos
        X = float(x_px) * sx
        Y = float(y_px) * sy

        # se veio do topo, inverte
        if args.invert_y:
            Y = page_h - Y

        # baseline: com invert-y, precisamos DESCER a caneta => subtrair
        Y -= baseline_fix(pt, args.baseline_fix)

        # desenhar
        if not text.strip():
            continue

        if name in RIGHT_KEYS:
            draw_text(c, text, col_r, Y, font, pt, "right")
        else:
            draw_text(c, text, X, Y, font, pt, align)

        # prova
        if args.proof:
            c.setLineWidth(0.3)
            # âncora
            anchor_x = col_r if name in RIGHT_KEYS else X
            c.rect(anchor_x - 1.5, Y - 1.5, 3, 3, stroke=1, fill=0)
            # caixa estimada
            f_ok = font if font in pdfmetrics.getRegisteredFontNames() else "Helvetica"
            w = stringWidth(text, f_ok, pt)
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

    # mescla overlay com o fundo
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

    print("Gerado:", out_path)
    print("Fundo:", bg.name)
    print("Coords:", coords_path.name)
    print(f"Escalas -> X: {sx:.6f}  Y: {sy:.6f}  (ref: {ref_w}x{ref_h} px)")


if __name__ == "__main__":
    main()