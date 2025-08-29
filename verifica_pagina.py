from PyPDF2 import PdfReader

pg = PdfReader("bg_ticket_full.pdf").pages[0]
print("Página:", pg.mediabox.width, pg.mediabox.height)