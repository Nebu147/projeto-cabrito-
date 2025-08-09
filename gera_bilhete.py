gera_ticket_final.py
Fundo: bg_ticket-APAGADO.pdf  |  Coords: coords_ticket_100_com_texto.json
Requisitos: pip install reportlab PyPDF2
import json
from pathlib import Path
from argparse import ArgumentParser
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from PyPDF2 import PdfReader, PdfWriter
Campos que devem alinhar à direita em uma coluna comum
RIGHT_KEYS = {
"tarifa_valor", "taxa_embarque_valor", "pedagio_valor",
"valor_total_valor", "desconto_valor", "valor_a_pagar_valor",
"valor_pag_valor", "troco_valor"
}
def read_page_size(pdf_path: Path):
pg = PdfReader(str(pdf_path)).pages[0]
# Usa cropBox se existir (mais “real” que mediaBox)
box = pg.cropbox if pg.cropbox else pg.mediabox
w = float(box.right) - float(box.left)
h = float(box.top) - float(box.bottom)
return w, h
def baseline_fix(pt: float) -> float:
"""Compensa “afundamento” do texto em relação ao topo da caixa.
0.28~0.32 funciona bem para Helvetica; usei 0.30 por padrão."""
return 0.30 * pt
def compute_col_r(coords: dict, sx: float, page_w: float) -> float:
"""Calcula X da coluna direita. Usa o maior X visto nos valores da direita
(após escala) ou 0.89*page_w como fallback."""
xs = []
for k in RIGHT_KEYS:
if k in coords:
pos = coords[k].get("pos", [None, None])[0]
if isinstance(pos, (int, float)):
xs.append(float(pos) * sx)
if xs:
return max(xs)
return 0.89 * page_w
def draw_text(c: canvas.Canvas, text: str, x: float, y: float, font: str, pt: float, align: str = "left"):
try:
c.setFont(font, pt)
except Exception:
c.setFont("Helvetica", pt)
if align == "center":
c.drawCentredString(x, y, text)
elif align == "right":
c.drawRightString(x, y, text)
else:
c.drawString(x, y, text)
def main():
ap = ArgumentParser()
ap.add_argument("--bg", default="bg_ticket-APAGADO.pdf")
ap.add_argument("--coords", default="coords_ticket_100_com_texto.json")
ap.add_argument("--out", default="ticket_final.pdf")
ap.add_argument("--invert-y", action="store_true",
help="Use se suas coords foram medidas do TOPO (ex.: GIMP). Para Acrobat, deixe DESLIGADO.")
ap.add_argument("--proof", action="store_true",
help="Desenha caixas de prova em volta dos textos.")
args = ap.parse_args()
bg = Path(args.bg)
coords_path = Path(args.coords)
out = Path(args.out)

if not bg.exists():
    raise FileNotFoundError(f"Fundo não encontrado: {bg}")
if not coords_path.exists():
    raise FileNotFoundError(f"Coords não encontrado: {coords_path}")

page_w, page_h = read_page_size(bg)

coords = json.loads(coords_path.read_text(encoding="utf-8"))
ref_w = float(coords.get("_ref_width", 0))
ref_h = float(coords.get("_ref_height", 0))
if not ref_w or not ref_h:
    raise ValueError("O JSON precisa conter _ref_width e _ref_height (dimensões do mockup).")

sx = page_w / ref_w
sy = page_h / ref_h

# Coluna direita comum
col_r = compute_col_r(coords, sx, page_w)

# Overlay
overlay_tmp = Path("_overlay_ticket.pdf")
c = canvas.Canvas(str(overlay_tmp), pagesize=(page_w, page_h))

for name, meta in coords.items():
    if name.startswith("_"):  # ignora metadados
        continue
    text = meta.get("texto", "")
    font = meta.get("font", "Helvetica")
    pt = float(meta.get("pt", 22))
    x0, y0 = meta.get("pos", [0, 0])
    align = meta.get("align", "left").lower()

    # Escala
    X = float(x0) * sx
    Y = float(y0) * sy

    # Origem Y: Acrobat = rodapé (não inverter). GIMP = topo (inverter).
    if args.invert_y:
        Y = page_h - Y

    # Compensação de baseline (para alinhar com topo visual da caixa)
    Y += baseline_fix(pt) * (sy if not args.invert_y else 1.0)

    # Coluna direita: força mesmo X e alinhamento
    if name in RIGHT_KEYS:
        draw_text(c, text, col_r, Y, font, pt, align="right")
    else:
        draw_text(c, text, X, Y, font, pt, align=align)

    # Prova visual
    if args.proof:
        try:
            txt_w = pdfmetrics.stringWidth(text, c._fontname, pt)
        except Exception:
            txt_w = pdfmetrics.stringWidth(text, "Helvetica", pt)
        pad = 2
        if name in RIGHT_KEYS:
            x_box = col_r - txt_w
        else:
            if align == "left":
                x_box = X
            elif align == "center":
                x_box = X - txt_w / 2.0
            else:  # right
                x_box = X - txt_w
        c.setDash(2, 2)
        c.rect(x_box - pad, Y - pad, txt_w + 2 * pad, pt + 2 * pad, stroke=1, fill=0)
        c.setDash()

c.save()

# Mescla
reader_bg = PdfReader(str(bg))
reader_ov = PdfReader(str(overlay_tmp))
page = reader_bg.pages[0]
page.merge_page(reader_ov.pages[0])
writer = PdfWriter()
writer.add_page(page)
with open(out, "wb") as f:
    writer.write(f)

print(f"✅ Gerado: {out} | (bg {page_w:.1f}×{page_h:.1f} pt | ref {ref_w:.1f}×{ref_h:.1f} pt | sx={sx:.4f} sy={sy:.4f})")

if name == "main":
main()
