# gera_controle.py  —  modo estrito (respeita 100% o coords_controle.json)

from __future__ import annotations
import json
from argparse import ArgumentParser
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from PyPDF2 import PdfReader, PdfWriter

# Tamanho fixo do CONTROLE
PAGE_W_MM = 80
PAGE_H_MM = 130
PAGE_W_PT = PAGE_W_MM * mm
PAGE_H_PT = PAGE_H_MM * mm

# Mapeamento de chaves *_valor -> campo no controle.json
KEY_MAP = {
    "origem_valor":        ["origem"],
    "destino_valor":       ["destino"],
    "data_valor":          ["data"],
    "horario_valor":       ["hora", "horario"],   # aceita "hora" ou "horario"
    "poltrona_valor":      ["poltrona"],
    "plataforma_valor":    ["plataforma"],
    "prefixo_valor":       ["prefixo"],
    "linha_valor_1":       ["linha1", "linha_1"],
    "linha_valor_2":       ["linha2", "linha_2"],
    "tipo_valor":          ["tipo"],
    "passageiro_valor_1":  ["passageiro", "passageiro_nome"],
    "passageiro_valor_2":  ["passageiro_2", "sobrenome"],
}

def var_for_key(name: str, dados: dict, default: str) -> str:
    """Retorna o valor do controle.json correspondente a uma chave *_valor;
       se não houver, devolve o texto default do coords."""
    for cand in KEY_MAP.get(name, []):
        if cand in dados and str(dados[cand]).strip():
            return str(dados[cand])
    return default

def draw_one(c: canvas.Canvas, meta: dict, invert_y: bool):
    """Desenha um item do coords (texto literal, sem substituição)."""
    texto = str(meta.get("texto", ""))
    font  = meta.get("font", "Helvetica")
    pt    = float(meta.get("pt", 8))
    align = meta.get("align", "left").lower()
    x_mm, y_mm = meta.get("pos", [0.0, 0.0])

    x = float(x_mm) * mm
    y = float(y_mm) * mm
    if invert_y:
        y = PAGE_H_PT - y

    c.setFont(font, pt)
    if align == "center":
        c.drawCentredString(PAGE_W_PT/2, y, texto)
    elif align == "right":
        c.drawRightString(x, y, texto)
    else:
        c.drawString(x, y, texto)

def draw_value(c: canvas.Canvas, name: str, meta: dict, dados: dict, invert_y: bool):
    """Desenha item *_valor substituindo pelo controle.json; todo o resto respeita o coords."""
    texto_default = str(meta.get("texto", ""))
    texto = var_for_key(name, dados, texto_default)

    meta2 = dict(meta)
    meta2["texto"] = texto
    draw_one(c, meta2, invert_y)

def gerar_overlay(dados: dict, coords: dict, invert_y: bool, proof: bool) -> Path:
    tmp = Path("__overlay_tmp_controle.pdf")
    c = canvas.Canvas(str(tmp), pagesize=(PAGE_W_PT, PAGE_H_PT))

    for name, meta in coords.items():
        # Ignore metadados opcionais
        if name.startswith("_"):
            continue

        # Substitui somente *_valor; demais são desenhados literalmente
        if name.endswith("_valor") or name.endswith("_valor_1") or name.endswith("_valor_2"):
            draw_value(c, name, meta, dados, invert_y)
        else:
            draw_one(c, meta, invert_y)

        if proof:
            # caixinha simples para debug
            try:
                x_mm, y_mm = meta.get("pos", [0.0, 0.0])
                pt = float(meta.get("pt", 8))
                x = float(x_mm) * mm
                y = float(y_mm) * mm
                if invert_y:
                    y = PAGE_H_PT - y
                c.setLineWidth(0.3)
                c.rect(x-1.5, y-1.5, 3, 3)  # âncora
                c.setDash(2, 2)
                c.rect(x-2, y-2, 60, pt+4)  # caixa ilustrativa
                c.setDash()
            except Exception:
                pass

    c.showPage()
    c.save()
    return tmp

def mesclar(bg_pdf: Path, overlay_pdf: Path, out_pdf: Path):
    r_bg = PdfReader(str(bg_pdf))
    r_ov = PdfReader(str(overlay_pdf))
    page = r_bg.pages[0]
    page.merge_page(r_ov.pages[0])
    w = PdfWriter()
    w.add_page(page)
    with out_pdf.open("wb") as f:
        w.write(f)

def main():
    p = ArgumentParser(description="Gera CONTROLE (80x130mm) respeitando 100% o coords_controle.json.")
    p.add_argument("--bg", required=True, help="PDF de fundo (bg_controle.pdf)")
    p.add_argument("--coords", required=True, help="JSON de coordenadas (coords_controle.json)")
    p.add_argument("--vars", required=True, help="JSON de variáveis (controle.json)")
    p.add_argument("--out", default="controle_final.pdf", help="PDF de saída")
    p.add_argument("--invert-y", action="store_true", help="Se coords usa Y a partir do topo (recomendado)")
    p.add_argument("--proof", action="store_true", help="Desenha âncoras/caixas de debug")
    args = p.parse_args()

    bg = Path(args.bg)
    coords_path = Path(args.coords)
    vars_path = Path(args.vars)
    out_path = Path(args.out)

    coords = json.loads(coords_path.read_text(encoding="utf-8"))
    dados  = json.loads(vars_path.read_text(encoding="utf-8"))

    tmp = gerar_overlay(dados, coords, args.invert_y, args.proof)
    try:
        mesclar(bg, tmp, out_path)
    finally:
        try: tmp.unlink()
        except Exception: pass

    print("Gerado:", out_path)

if __name__ == "__main__":
    main()