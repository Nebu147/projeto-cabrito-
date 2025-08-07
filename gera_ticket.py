#!/usr/bin/env python3
import io
import json
import argparse
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from PyPDF2 import PdfReader, PdfWriter

def generate_ticket(bg_pdf_path, coords_path, output_pdf_path):
    # 1) Leia o PDF de fundo e obtenha dimensões
    reader = PdfReader(bg_pdf_path)
    page = reader.pages[0]
    media = page.mediabox
    page_width = float(media.width)
    page_height = float(media.height)

    # 2) Crie um canvas em memória do mesmo tamanho
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # 3) Carregue as coordenadas
    with open(coords_path, 'r', encoding='utf-8') as f:
        coords = json.load(f)

    # 4) Desenhe cada campo como TextField ajustado
    padding_x, padding_y = 6, 4
    form = c.acroForm
    for name, meta in coords.items():
        texto = meta['texto']
        font = meta.get('font', 'Helvetica')
        pt   = meta.get('pt',    12)
        align= meta.get('align','left')
        x_px, y_px = meta.get('pos',[0,0])

        # Calcule tamanho da caixa
        text_w = stringWidth(texto, font, pt)
        w = text_w + padding_x
        h = pt + padding_y

        # Ajuste X conforme alinhamento
        if align == 'right':
            x_pt = x_px - w
        elif align == 'center':
            x_pt = x_px - (w / 2)
        else:  # left
            x_pt = x_px

        # Inverta Y e considere a altura da caixa
        y_pt = page_height - y_px - h

        # Crie o campo de formulário (texfield)
        form.textfield(
            name=name,
            tooltip=name,
            x=x_pt, y=y_pt,
            width=w, height=h,
            borderStyle='underlined',
            forceBorder=True,
            fontName=font,
            fontSize=pt,
            fieldFlags=meta.get('fieldFlags',0)
        )

    # 5) Finalize o canvas e crie o overlay
    c.save()
    packet.seek(0)
    overlay_pdf = PdfReader(packet)
    overlay_page = overlay_pdf.pages[0]

    # 6) Mescle overlay + página de fundo
    page.merge_page(overlay_page)
    writer = PdfWriter()
    writer.add_page(page)

    # 7) Salve no arquivo de saída
    with open(output_pdf_path, 'wb') as out_f:
        writer.write(out_f)

    print(f"✅ Bilhete gerado: {output_pdf_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gera bilhete com campos editáveis sobre PDF de fundo")
    parser.add_argument("--bg",     default="bg_ticket_full.pdf", help="PDF de fundo (gabarito)")
    parser.add_argument("--coords", default="coords_ticket.json", help="JSON de coordenadas")
    parser.add_argument("--out",    default="ticket_final.pdf", help="Caminho de saída do PDF gerado")
    args = parser.parse_args()
    generate_ticket(args.bg, args.coords, args.out)