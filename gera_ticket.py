
import json
import argparse
from pathlib import Path
from reportlab.pdfgen import canvas
from PyPDF2 import PdfReader, PdfWriter

def gerar_ticket(bg_path, coords_path, out_path, invert_y=False, debug=False):
    bg_pdf = Path(bg_path)
    coords_file = Path(coords_path)
    out_pdf = Path(out_path)

    # Ler coordenadas
    with open(coords_file, "r", encoding="utf-8") as f:
        coords = json.load(f)

    # Ler dimensões do fundo
    bg_reader = PdfReader(str(bg_pdf))
    bg_page = bg_reader.pages[0]
    bg_width = float(bg_page.mediabox.width)
    bg_height = float(bg_page.mediabox.height)

    # Pegar dimensões de referência do JSON
    ref_width = coords.get("_ref_width", bg_width)
    ref_height = coords.get("_ref_height", bg_height)

    # Calcular escala
    scale_x = bg_width / ref_width
    scale_y = bg_height / ref_height
    print(f"(bg: {bg_width:.2f}x{bg_height:.2f} pt | ref: {ref_width:.2f}x{ref_height:.2f} pt | sx={scale_x:.4f}, sy={scale_y:.4f})")

    # Criar overlay
    overlay_path = "overlay_temp.pdf"
    c = canvas.Canvas(overlay_path, pagesize=(bg_width, bg_height))

    for campo, props in coords.items():
        if campo.startswith("_"):  # Ignorar metadados
            continue

        texto = props["texto"]
        font = props.get("font", "Helvetica")
        pt = props.get("pt", 12)
        x, y = props["pos"]
        align = props.get("align", "left")

        # Aplicar escala
        x_scaled = x * scale_x
        y_scaled = y * scale_y

        # Inverter Y se necessário
        if invert_y:
            y_scaled = bg_height - y_scaled

        c.setFont(font, pt)
        if debug:
            c.setStrokeColorRGB(1, 0, 0)
            c.rect(x_scaled - 1, y_scaled - 1, 100, 12, stroke=1, fill=0)

        if align == "center":
            c.drawCentredString(x_scaled, y_scaled, texto)
        elif align == "right":
            c.drawRightString(x_scaled, y_scaled, texto)
        else:
            c.drawString(x_scaled, y_scaled, texto)

    c.save()

    # Mesclar overlay com fundo
    overlay_reader = PdfReader(overlay_path)
    writer = PdfWriter()
    page = bg_reader.pages[0]
    page.merge_page(overlay_reader.pages[0])
    writer.add_page(page)

    with open(out_pdf, "wb") as f:
        writer.write(f)

    print(f"✅ Ticket gerado: {out_pdf}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bg", required=True, help="PDF de fundo")
    parser.add_argument("--coords", required=True, help="JSON com coordenadas")
    parser.add_argument("--out", required=True, help="Arquivo PDF de saída")
    parser.add_argument("--invert-y", action="store_true", help="Inverter eixo Y")
    parser.add_argument("--debug", action="store_true", help="Desenhar caixas de debug")
    args = parser.parse_args()

    gerar_ticket(args.bg, args.coords, args.out, invert_y=args.invert_y, debug=args.debug)
