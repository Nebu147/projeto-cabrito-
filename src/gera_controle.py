#!/usr/bin/env python3
"""
gera_controle.py — Gera o CONTROLE sobre um PDF de fundo e (opcional) exporta PNG 1-bit 203 dpi.

Uso típico (Linux):
  python3 src/gera_controle.py \
    --bg assets/bg_controle.pdf \
    --coords data/coords_controle.json \
    --vars data/controle.json \
    --out out/controle_final.pdf \
    --invert-y \
    --png-mono --png-engine poppler --threshold 0.45 \
    --printer EPSON_TM-T20 --width-mm 80 --height-mm 130

Uso típico (Windows):
  py src\gera_controle.py ^
    --bg assets\bg_controle.pdf ^
    --coords data\coords_controle.json ^
    --vars data\controle.json ^
    --out out\controle_final.pdf ^
    --invert-y

Dependências Python:
  - reportlab, PyPDF2
  - (opcional, quando usar --png-engine pymupdf): pymupdf, pillow

Dependências de sistema (quando usar --png-engine poppler):
  - poppler-utils (pdftoppm)
  - imagemagick (convert ou magick)

"""

from __future__ import annotations
import json
import sys
import shutil
import subprocess as sp
from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from typing import Dict, Any

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.units import mm
from PyPDF2 import PdfReader, PdfWriter


# =========================
# Utilidades gerais
# =========================

def ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

def which(name: str) -> str | None:
    return shutil.which(name)

def run_cmd(cmd: list[str], verbose: bool = False) -> None:
    if verbose:
        print("[CMD]", " ".join(cmd))
    p = sp.run(cmd, stdout=sp.PIPE, stderr=sp.STDOUT, text=True)
    if verbose and p.stdout:
        print(p.stdout)
    if p.returncode != 0:
        raise RuntimeError(f"Falha executando: {' '.join(cmd)}\nSaida:\n{p.stdout}")

def draw_text_pt(c: canvas.Canvas, text: str, x_pt: float, y_pt: float,
                 font: str, pt: float, align: str) -> None:
    """Desenha texto em pontos, respeitando align: left|center|right."""
    try:
        c.setFont(font, pt)
    except Exception:
        c.setFont("Helvetica", pt)

    a = (align or "left").lower()
    if a == "center":
        c.drawCentredString(x_pt, y_pt, text)
    elif a == "right":
        c.drawRightString(x_pt, y_pt, text)
    else:
        c.drawString(x_pt, y_pt, text)

def proof_box(c: canvas.Canvas, x_pt: float, y_pt: float, w_pt: float, h_pt: float) -> None:
    c.setDash(2, 2)
    c.setLineWidth(0.3)
    c.rect(x_pt - 2, y_pt - 2, w_pt + 4, h_pt + 4, stroke=1, fill=0)
    c.setDash()


# =========================
# Conversores PDF -> PNG 1-bit
# =========================

def pdf_to_png_1bit_poppler(pdf_path: Path, out_dir: Path, *,
                            dpi: int = 203, mode: str = "threshold",
                            threshold: float = 0.50, keep_intermediate: bool = False,
                            verbose: bool = False) -> Path:
    """
    Usa 'pdftoppm' + ImageMagick para gerar PNG 203dpi e depois PNG 1-bit.
    Retorna caminho do PNG final.
    """
    pdftoppm = which("pdftoppm")
    convert = which("convert") or which("magick")
    if not pdftoppm:
        raise RuntimeError("Dependencia faltando: 'pdftoppm' (instale poppler-utils).")
    if not convert:
        raise RuntimeError("Dependencia faltando: 'convert' (instale imagemagick).")

    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{pdf_path.stem}_{dpi}dpi"
    png203 = base.with_suffix(".png")
    png_bw = out_dir / f"{pdf_path.stem}_bw.png"

    # 1) PDF -> PNG 203 dpi (primeira pagina)
    cmd_pdf = [pdftoppm, "-png", "-r", str(dpi), "-singlefile", "-f", "1", "-l", "1",
               str(pdf_path), str(base)]
    run_cmd(cmd_pdf, verbose)
    if not png203.exists():
        alt = out_dir / f"{pdf_path.stem}_{dpi}dpi-1.png"
        if alt.exists():
            alt.rename(png203)
        else:
            raise RuntimeError("Falha ao gerar PNG 203dpi a partir do PDF.")

    # 2) PNG -> 1-bit
    use_magick = (Path(convert).name.lower() == "magick")
    cmd_bw = ([convert, "convert", str(png203)] if use_magick else [convert, str(png203)])
    if mode == "threshold":
        thr = max(0, min(100, int(round(threshold * 100))))
        cmd_bw += ["-threshold", f"{thr}%", "-type", "bilevel", str(png_bw)]
    else:
        cmd_bw += ["-monochrome", str(png_bw)]
    run_cmd(cmd_bw, verbose)

    if not keep_intermediate and png203.exists():
        try:
            png203.unlink()
        except Exception:
            pass

    return png_bw


def pdf_to_png_1bit_pymupdf(pdf_path: Path, out_dir: Path, *,
                            dpi: int = 203, mode: str = "threshold",
                            threshold: float = 0.50, verbose: bool = False) -> Path:
    """
    Usa PyMuPDF (fitz) + Pillow para rasterizar e gerar PNG 1-bit.
    Retorna caminho do PNG final.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError("pymupdf nao encontrado. pip install pymupdf") from e
    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError("Pillow nao encontrado. pip install pillow") from e

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open(str(pdf_path))
    try:
        page = pdf[0]
        scale = dpi / 72.0
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
    finally:
        pdf.close()

    gray_path = out_dir / f"{pdf_path.stem}_{dpi}dpi_gray.png"
    bw_path = out_dir / f"{pdf_path.stem}_bw.png"
    pix.save(str(gray_path))

    img = Image.open(gray_path).convert("L")  # 8-bit cinza
    if mode == "threshold":
        thr = int(max(0, min(255, round(threshold * 255))))
        img = img.point(lambda p: 255 if p > thr else 0, mode="1")  # 1-bit por limiar
    else:
        img = img.convert("1")  # 1-bit com dithering (Floyd–Steinberg)

    img.save(bw_path)
    try:
        gray_path.unlink()
    except Exception:
        pass

    return bw_path


def cups_print_png(png_path: Path, printer: str, *, width_mm: float, height_mm: float, verbose: bool = False) -> None:
    lp = which("lp")
    if not lp:
        raise RuntimeError("CUPS nao encontrado. Instale 'cups' para imprimir via 'lp'.")
    media = f"Custom.{width_mm}x{height_mm}mm"
    cmd = [lp, "-d", printer,
           "-o", "fit-to-page=false",
           "-o", "scaling=100",
           "-o", f"media={media}",
           str(png_path)]
    run_cmd(cmd, verbose)


# =========================
# Render do CONTROLE
# =========================

# Se o seu controle sempre for 80x130 mm, estes sao defaults.
DEFAULT_W_MM = 80.0
DEFAULT_H_MM = 130.0

# Mapa de chaves do COORDS -> variaveis do JSON de dados
VAR_MAP: Dict[str, str] = {
    "origem_valor": "origem",
    "destino_valor": "destino",
    "data_valor": "data",
    "horario_valor": "hora",
    "poltrona_valor": "poltrona",
    "plataforma_valor": "plataforma",
    "prefixo_valor": "prefixo",
    "linha_valor_1": "linha1",
    "linha_valor_2": "linha2",
    "tipo_valor": "tipo",
    "passageiro_valor_1": "passageiro",
    "passageiro_valor_2": "passageiro_2",
}

def gerar_overlay_controle(coords: Dict[str, Any],
                           dados: Dict[str, Any],
                           page_w_mm: float, page_h_mm: float,
                           invert_y: bool, proof: bool) -> BytesIO:
    """
    Desenha todos os campos do controle respeitando exatamente as coordenadas do JSON.
    - pos: [x_mm, y_mm_top_origen]  (se invert_y=True, y e baseado no topo)
    - align: left|center|right
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w_mm * mm, page_h_mm * mm))

    for name, meta in coords.items():
        # ignore metadados e entradas quebradas
        if name.startswith("_"):
            continue
        if not isinstance(meta, dict):
            continue

        # Texto base (do coords), substituido por dados se houver mapeamento
        texto = str(meta.get("texto", ""))
        if name in VAR_MAP:
            var_key = VAR_MAP[name]
            texto = str(dados.get(var_key, texto))

        # Nao desenha espacos / vazio
        if not texto.strip():
            continue

        font = meta.get("font", "Helvetica")
        pt = float(meta.get("pt", 8))
        align = meta.get("align", "left")

        x_mm, y_mm_top = meta.get("pos", [0.0, 0.0])
        # Converte Y: coords medidos do topo? entao inverter
        if invert_y:
            y_mm = page_h_mm - float(y_mm_top)
        else:
            y_mm = float(y_mm_top)

        x_pt = float(x_mm) * mm
        y_pt = float(y_mm) * mm

        # Desenha
        draw_text_pt(c, texto, x_pt, y_pt, font, pt, align)

        # Prova: caixa pontilhada ao redor do texto (largura estimada)
        if proof:
            try:
                font_used = font if font in pdfmetrics.getRegisteredFontNames() else "Helvetica"
                w_pt = stringWidth(texto, font_used, pt)
            except Exception:
                w_pt = stringWidth(texto, "Helvetica", pt)
            h_pt = pt  # altura aproximada
            # Alinhamentos ajustam a caixa
            a = (align or "left").lower()
            if a == "center":
                x0 = x_pt - w_pt / 2.0
            elif a == "right":
                x0 = x_pt - w_pt
            else:
                x0 = x_pt
            proof_box(c, x0, y_pt, w_pt, h_pt)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def mesclar_overlay_com_bg(overlay: BytesIO, bg_pdf: Path, out_pdf: Path) -> None:
    """Mescla o overlay (PDF em memoria) sobre o PDF de fundo e grava out_pdf."""
    ensure_parent_dir(out_pdf)
    r_bg = PdfReader(str(bg_pdf))
    r_ov = PdfReader(overlay)
    page = r_bg.pages[0]
    page.merge_page(r_ov.pages[0])  # PyPDF2 >= 2.x
    w = PdfWriter()
    w.add_page(page)
    with out_pdf.open("wb") as f:
        w.write(f)


# =========================
# CLI
# =========================

def main() -> None:
    p = ArgumentParser(description="Gera o CONTROLE sobre um PDF de fundo e (opcional) exporta PNG 1-bit.")
    p.add_argument("--bg", required=True, help="PDF de fundo (template do CONTROLE).")
    p.add_argument("--coords", required=True, help="JSON com coordenadas/estilos do CONTROLE.")
    p.add_argument("--vars", required=True, help="JSON com valores (origem, destino, etc.).")
    p.add_argument("--out", default="out/controle_final.pdf", help="PDF de saida.")
    p.add_argument("--invert-y", action="store_true", help="Use se as coordenadas foram medidas a partir do topo.")
    p.add_argument("--proof", action="store_true", help="Modo prova: desenha caixas de debug ao redor dos textos.")

    # Exportacao PNG 1-bit / Impressao
    p.add_argument("--png-mono", action="store_true", help="Apos gerar o PDF, exporta PNG 1-bit 203 dpi.")
    p.add_argument("--png-engine", choices=["poppler", "pymupdf"], default="poppler",
                   help="Motor para rasterizar o PDF em imagem (default: poppler).")
    p.add_argument("--dpi", type=int, default=203, help="DPI para o PNG (default: 203).")
    p.add_argument("--mode", choices=["threshold", "dither"], default="threshold",
                   help="threshold=preto/branco puro; dither=pontilhado (ainda 1-bit).")
    p.add_argument("--threshold", type=float, default=0.50,
                   help="Limiar do threshold (0.0–1.0). Ignorado no modo dither. Default 0.50.")
    p.add_argument("--printer", help="Se informado, envia o PNG 1-bit para esta impressora CUPS.")
    p.add_argument("--width-mm", type=float, default=None, help="Largura da midia (mm) para imprimir (default: do coords ou 80).")
    p.add_argument("--height-mm", type=float, default=None, help="Altura da midia (mm) para imprimir (default: do coords ou 130).")
    p.add_argument("--keep-intermediate", action="store_true", help="Mantem o PNG 203 dpi intermediario (quando poppler).")
    p.add_argument("--verbose", action="store_true", help="Mostra comandos de conversao/impressao.")

    args = p.parse_args()

    bg_pdf = Path(args.bg)
    coords_path = Path(args.coords)
    vars_path = Path(args.vars)
    out_pdf = Path(args.out)

    # Carrega JSONs
    coords: Dict[str, Any] = json.loads(coords_path.read_text(encoding="utf-8"))
    dados: Dict[str, Any] = json.loads(vars_path.read_text(encoding="utf-8"))

    # Tamanho da pagina em mm
    page_w_mm = float(coords.get("_ref_width", DEFAULT_W_MM))
    page_h_mm = float(coords.get("_ref_height", DEFAULT_H_MM))

    # Gera overlay em memoria e mescla
    overlay = gerar_overlay_controle(coords, dados, page_w_mm, page_h_mm, args.invert_y, args.proof)
    mesclar_overlay_com_bg(overlay, bg_pdf, out_pdf)

    print("Gerado PDF:", out_pdf)

    # Exporta PNG 1-bit (opcional)
    if args.png_mono:
        out_dir = out_pdf.parent
        engine = args.png_engine
        png_path: Path

        try:
            if engine == "poppler":
                png_path = pdf_to_png_1bit_poppler(
                    out_pdf, out_dir,
                    dpi=args.dpi, mode=args.mode, threshold=args.threshold,
                    keep_intermediate=args.keep_intermediate, verbose=args.verbose
                )
            else:
                png_path = pdf_to_png_1bit_pymupdf(
                    out_pdf, out_dir,
                    dpi=args.dpi, mode=args.mode, threshold=args.threshold,
                    verbose=args.verbose
                )
            print("Gerado PNG 1-bit:", png_path)
        except Exception as e:
            print("[AVISO] Conversao para 1-bit falhou:", e, file=sys.stderr)
            return

        # Impressao (opcional)
        if args.printer:
            w_mm = args.width_mm if args.width_mm is not None else page_w_mm
            h_mm = args.height_mm if args.height_mm is not None else page_h_mm
            try:
                cups_print_png(png_path, args.printer, width_mm=w_mm, height_mm=h_mm, verbose=args.verbose)
                print("Enviado para impressora:", args.printer)
            except Exception as e:
                print("[AVISO] Impressao via CUPS falhou:", e, file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Erro:", exc, file=sys.stderr)
        sys.exit(1)