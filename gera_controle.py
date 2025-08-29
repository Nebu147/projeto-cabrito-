# src/gera_controle.py
from __future__ import annotations

"""
Gera o CONTROLE (overlay de texto em cima do PDF de fundo).

- Lê:
    --bg      : PDF de fundo (assets/bg_controle.pdf)
    --coords  : JSON com coordenadas e defaults (data/coords_controle.json)
    --vars    : JSON com os valores (data/controle.json)

- Salva:
    --out     : PDF final (out/controle_final.pdf). Se omitido, usa out/controle_final.pdf

- Extras:
    --invert-y        : Usa Y a partir do topo (como a arte).
    --proof           : Desenha marquinhas nas âncoras.
    --png-mono        : Também gera PNG 1-bit (mono) do PDF final.
    --png-engine      : poppler (pdf2image) | pymupdf
    --dpi             : DPI de rasterização (203 por padrão).
    --mode            : 'threshold' (binário com limiar) ou 'dither' (Floyd-Steinberg).
    --threshold       : 0–255 (200 deixa mais preto).
    --printer         : Envia para impressora (lp -d <nome> <arquivo>).
    --width-mm/--height-mm : Ajuda para impressoras térmicas (apenas informativo aqui).
    --keep-intermediate     : Mantém o overlay temporário.
    --verbose               : Logs extras.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4  # fallback

try:
    from PyPDF2 import PdfReader, PdfWriter
except Exception as e:
    print("[ERRO] PyPDF2 é obrigatório:", e, file=sys.stderr)
    sys.exit(1)


# ----------------- util -----------------

def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERRO] Falha lendo JSON: {path}: {e}", file=sys.stderr)
        sys.exit(1)


def ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def read_page_size_mm(pdf_path: Path) -> Tuple[float, float]:
    """Retorna (largura_mm, altura_mm) do PDF."""
    with open(pdf_path, "rb") as fh:
        r = PdfReader(fh)
        p0 = r.pages[0]
        box = p0.mediabox
        w_pt = float(box.width)
        h_pt = float(box.height)
        return (w_pt / mm, h_pt / mm)


def str_width_pt(text: str, font_name: str, pt_size: float) -> float:
    try:
        return pdfmetrics.stringWidth(text, font_name, pt_size)
    except Exception:
        # fontes built-in Helvetica/Helvetica-Bold existem;
        # se algo der errado, evita quebrar
        return pdfmetrics.stringWidth(text, "Helvetica", pt_size)


def align_offset_pt(text: str, font: str, pt: float, align: str) -> float:
    w = str_width_pt(text, font, pt)
    if align == "center":
        return -w / 2.0
    if align == "right":
        return -w
    return 0.0  # left


def get_scale(coords: Dict[str, Any],
              page_w_mm: float,
              page_h_mm: float) -> Tuple[float, float]:
    ref_w = float(coords.get("_ref_width", page_w_mm))
    ref_h = float(coords.get("_ref_height", page_h_mm))
    sx = page_w_mm / ref_w if ref_w else 1.0
    sy = page_h_mm / ref_h if ref_h else 1.0
    return sx, sy


# ----------------- desenho -----------------

def draw_value(c: canvas.Canvas,
               name: str,
               meta: Dict[str, Any],
               dados: Dict[str, Any],
               invert_y: bool,
               page_w_mm: float,
               page_h_mm: float,
               scale_x: float,
               scale_y: float,
               proof: bool = False) -> None:
    """
    **MUDANÇA COMBINADA**:
    - Se a CHAVE existir em `dados` (controle.json), usamos SEMPRE esse valor
      (mesmo que seja "" para suprimir).
    - Só usamos meta["texto"] do coords quando a chave **não existe**.
    """
    # 1) texto
    texto_default = str(meta.get("texto", ""))
    if name in dados:
        text = str(dados[name])
    else:
        text = texto_default

    # 2) pos
    pos = meta.get("pos", [0, 0])
    if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
        return
    x_mm = float(pos[0]) * scale_x
    y_mm = float(pos[1]) * scale_y
    if invert_y:
        y_mm = page_h_mm - y_mm

    # 3) estilo
    font = str(meta.get("font", "Helvetica"))
    pt = float(meta.get("pt", 8))
    align = str(meta.get("align", "left")).lower()

    # 4) desenha
    x_pt = x_mm * mm
    y_pt = y_mm * mm
    c.setFont(font, pt)
    x_pt += align_offset_pt(text, font, pt, align)
    c.drawString(x_pt, y_pt, text)

    # 5) proof
    if proof:
        c.setLineWidth(0.2)
        c.rect((x_mm - 0.8) * mm, (y_mm - 0.8) * mm, 1.6 * mm, 1.6 * mm)


def gerar_overlay(dados: Dict[str, Any],
                  coords: Dict[str, Any],
                  invert_y: bool,
                  page_w_mm: float,
                  page_h_mm: float,
                  proof: bool = False) -> Path:
    """Gera um PDF temporário com os textos nas posições informadas."""
    sx, sy = get_scale(coords, page_w_mm, page_h_mm)

    fd, tmp_path = tempfile.mkstemp(suffix="_overlay_controle.pdf")
    os.close(fd)
    ptmp = Path(tmp_path)

    c = canvas.Canvas(str(ptmp), pagesize=(page_w_mm * mm, page_h_mm * mm))
    # percorre apenas chaves "desenháveis"
    for name, meta in coords.items():
        if name.startswith("_"):
            continue
        if not isinstance(meta, dict):
            continue
        if "pos" not in meta:
            continue
        draw_value(
            c, name, meta, dados, invert_y,
            page_w_mm, page_h_mm, sx, sy, proof
        )
    c.showPage()
    c.save()
    return ptmp


def mesclar(bg_pdf: Path, overlay_pdf: Path, out_pdf: Path) -> None:
    ensure_parent_dir(out_pdf)
    with open(bg_pdf, "rb") as fbg, open(overlay_pdf, "rb") as fov:
        r_bg = PdfReader(fbg)
        r_ov = PdfReader(fov)
        p_bg = r_bg.pages[0]
        p_ov = r_ov.pages[0]
        # PyPDF2 >= 3.0
        p_bg.merge_page(p_ov)
        w = PdfWriter()
        w.add_page(p_bg)
        with open(out_pdf, "wb") as fout:
            w.write(fout)


# ----------------- PNG 1-bit opcional -----------------

def pdf_to_png_1bit_poppler(pdf_path: Path, out_dir: Path, dpi: int,
                            mode: str, threshold: int, verbose: bool) -> Optional[Path]:
    try:
        from pdf2image import convert_from_path
        from PIL import Image
    except Exception as e:
        print("[aviso] Para PNG 1-bit (poppler) instale: pdf2image + pillow.", file=sys.stderr)
        print("        Erro:", e, file=sys.stderr)
        return None

    imgs = convert_from_path(str(pdf_path), dpi=dpi)
    if not imgs:
        print("[aviso] convert_from_path não retornou páginas.", file=sys.stderr)
        return None

    img = imgs[0].convert("L")  # grayscale
    if mode == "threshold":
        bw = img.point(lambda p: 255 if p > threshold else 0, "1")
    else:  # dither
        bw = img.convert("1")  # Floyd-Steinberg

    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / (pdf_path.stem + "_bw.png")
    bw.save(out_png)
    if verbose:
        print(f"[ok] PNG 1-bit salvo: {out_png}")
    return out_png


def pdf_to_png_1bit_pymupdf(pdf_path: Path, out_dir: Path, dpi: int,
                            mode: str, threshold: int, verbose: bool) -> Optional[Path]:
    try:
        import fitz  # PyMuPDF
        from PIL import Image
    except Exception as e:
        print("[aviso] Para engine pymupdf instale: pymupdf + pillow. Erro:", e, file=sys.stderr)
        return None

    doc = fitz.open(str(pdf_path))
    page = doc.load_page(0)
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img = Image.frombytes("L", [pix.width, pix.height], pix.samples)

    if mode == "threshold":
        bw = img.point(lambda p: 255 if p > threshold else 0, "1")
    else:
        bw = img.convert("1")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / (pdf_path.stem + "_bw.png")
    bw.save(out_png)
    if verbose:
        print(f"[ok] PNG 1-bit salvo: {out_png}")
    return out_png


# ----------------- main -----------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Gera CONTROLE (PDF) e opcionalmente PNG 1-bit."
    )
    ap.add_argument("--bg", required=True, help="PDF de fundo (assets/bg_controle.pdf)")
    ap.add_argument("--coords", required=True, help="JSON de coordenadas")
    ap.add_argument("--vars", required=True, help="JSON com os valores")
    ap.add_argument("--out", default="out/controle_final.pdf", help="PDF final")

    ap.add_argument("--invert-y", action="store_true", help="Interpreta Y a partir do topo.")
    ap.add_argument("--proof", action="store_true", help="Desenha marcas nas âncoras.")

    ap.add_argument("--png-mono", action="store_true", help="Também gera PNG 1-bit.")
    ap.add_argument("--png-engine", choices=["poppler", "pymupdf"], default="poppler")
    ap.add_argument("--dpi", type=int, default=203)
    ap.add_argument("--mode", choices=["threshold", "dither"], default="threshold")
    ap.add_argument("--threshold", type=int, default=200)

    ap.add_argument("--printer", help="Nome da impressora CUPS (lp -d).")
    ap.add_argument("--width-mm", type=float, help="Largura mídia (informativo).")
    ap.add_argument("--height-mm", type=float, help="Altura mídia (informativo).")

    ap.add_argument("--keep-intermediate", action="store_true")
    ap.add_argument("--verbose", action="store_true")

    args = ap.parse_args()

    bg_path = Path(args.bg)
    coords_path = Path(args.coords)
    vars_path = Path(args.vars)
    out_pdf = Path(args.out)

    if args.verbose:
        print(f"BG: {bg_path}")
        print(f"COORDS: {coords_path}")
        print(f"VARS: {vars_path}")
        print(f"OUT: {out_pdf}")

    dados = read_json(vars_path)
    coords = read_json(coords_path)

    # tamanho da página do BG
    try:
        page_w_mm, page_h_mm = read_page_size_mm(bg_path)
    except Exception as e:
        print("[aviso] Não consegui ler o tamanho do BG, usando A4:", e, file=sys.stderr)
        page_w_mm = A4[0] / mm
        page_h_mm = A4[1] / mm

    # overlay
    overlay_pdf = gerar_overlay(
        dados=dados,
        coords=coords,
        invert_y=args.invert_y,
        page_w_mm=page_w_mm,
        page_h_mm=page_h_mm,
        proof=args.proof
    )

    # merge
    mesclar(bg_path, overlay_pdf, out_pdf)
    print(f"Gerado PDF: {out_pdf}")

    # opcional: PNG 1-bit
    if args.png_mono:
        out_dir = out_pdf.parent
        if args.png_engine == "poppler":
            pdf_to_png_1bit_poppler(out_pdf, out_dir, args.dpi, args.mode, args.threshold, args.verbose)
        else:
            pdf_to_png_1bit_pymupdf(out_pdf, out_dir, args.dpi, args.mode, args.threshold, args.verbose)

    # opcional: imprimir (CUPS)
    if args.printer:
        try:
            cmd = ["lp", "-d", args.printer, str(out_pdf)]
            subprocess.run(cmd, check=True)
            print(f"[ok] Enviado para impressora: {args.printer}")
        except Exception as e:
            print("[aviso] Falha ao imprimir:", e, file=sys.stderr)

    if not args.keep_intermediate:
        try:
            overlay_pdf.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[ERRO]:", exc, file=sys.stderr)
        sys.exit(1)
