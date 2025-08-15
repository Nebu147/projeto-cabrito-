# src/conv_png.py
from pdf2image import convert_from_path
from PIL import Image

def pdf_para_png_1bit(pdf_in, png_out, dpi=203, width_px=576, threshold=200):
    pages = convert_from_path(pdf_in, dpi=dpi, fmt="png", grayscale=True)
    img = pages[0]
    w, h = img.size
    if w != width_px:
        new_h = int(h * (width_px / w))
        img = img.resize((width_px, new_h), resample=Image.NEAREST)
    bw = img.convert("L").point(lambda x: 0 if x < threshold else 255, mode="1")
    bw.save(png_out, optimize=True)
