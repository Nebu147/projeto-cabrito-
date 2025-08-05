from PyPDF2 import PdfReader

def pt_to_mm(pt):
    return pt * 25.4 / 72  # 1 ponto = 1/72 polegada

def verificar_tamanho(pdf_path):
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    width_pt = float(page.mediabox.width)
    height_pt = float(page.mediabox.height)

    width_mm = pt_to_mm(width_pt)
    height_mm = pt_to_mm(height_pt)

    print(f"Tamanho do PDF: {width_mm:.2f} mm x {height_mm:.2f} mm")

# Substitua aqui pelo nome EXATO do seu PDF
verificar_tamanho("controle_80x130.pdf")
