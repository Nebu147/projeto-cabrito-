# extrai_coords_forms.py
import json
import re
from pathlib import Path
from PyPDF2 import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, red, blue, green
from reportlab.lib.utils import ImageReader

# ========== CONFIG ==========
MOCKUP_PDF = Path("ticket_mockup_numbered.pdf")   # seu PDF com formulários
JSON_BASE  = Path("coords_ticket_100_com_texto.json")  # opcional: herdar fontes/pt/texto
OUT_JSON   = Path("coords_ticket_from_forms.json")
DEBUG_PDF  = Path("debug_boxes.pdf")

# Mapeamento: numero_do_campo -> chave_do_coords
# (ajuste livremente; coloquei um exemplo com os mais usados)
MAPEAMENTO = {
    "1": "bpe_numero",                "2": "bpe_numero_valor",
    "3": "bpe_serie_label",           "4": "bpe_serie_valor",
    "5": "venda_label",               "6": "venda_valor",

    "7": "origem_label",              "8": "origem_valor",
    "9": "destino_label",             "10": "destino_valor",

    "11": "data_label",               "12": "data_valor",
    "13": "horario_valor",

    "14": "poltrona_label",           "15": "poltrona_valor",
    "16": "plataforma_label",         "17": "plataforma_valor",

    "18": "prefixo_label",            "19": "prefixo_valor",
    "20": "linha_label",              "21": "linha_valor_1",
    "22": "linha_valor_2",

    "23": "tipo_label",               "24": "tipo_valor",

    "25": "tarifa_label",             "26": "tarifa_valor",
    "27": "taxa_embarque_label",      "28": "taxa_embarque_valor",
    "29": "pedagio_label",            "30": "pedagio_valor",
    "31": "valor_total_label",        "32": "valor_total_valor",
    "33": "desconto_label",           "34": "desconto_valor",
    "35": "valor_a_pagar_label",      "36": "valor_a_pagar_valor",

    "37": "forma_pag_label",          "38": "valor_pag_label",
    "39": "forma_pag_valor",          "40": "valor_pag_valor",
    "41": "troco_label",              "42": "troco_valor",

    "45": "passageiro_valor_2",       # ELIAS DE
    "46": "passageiro_valor_3",       # SOUZA RIBEIRO
    "47": "bpe_numero_pequeno",       "48": "bpe_serie_pequeno",
    "49": "geracao_horario",          "50": "autorizacao_label",
    "51": "autorizacao_valor",

    # Se você usa um label "PASSAGEIRO", pode mapear também:
    # "44": "passageiro_label",
}

# ========== FUNÇÕES ==========

def _numero_do_nome(nome: str) -> str:
    """Extrai dígitos de '7' ou 'campo 7' -> '7'."""
    m = re.search(r"(\d+)$", str(nome))
    return m.group(1) if m else str(nome)

def extrai_rects(pdf_path: Path):
    reader = PdfReader(str(pdf_path))
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)

    fields = []
    try:
        acroform = reader.trailer["/Root"]["/AcroForm"]
        raw_fields = acroform.get("/Fields", [])
    except Exception:
        raw_fields = []

    for f in raw_fields:
        o = f.get_object()
        nome = o.get("/T")
        rect = o.get("/Rect")
        if not rect or not nome:
            continue
        x1, y1, x2, y2 = map(float, rect)
        w = x2 - x1
        h = y2 - y1
        # Converter para "origem no topo" (y cresce para baixo)
        # Vamos usar o topo-esquerdo da caixa como pos (igual seus coords atuais)
        pos_x = x1
        pos_y_top = height - y2
        fields.append({
            "nome_original": nome,
            "numero": _numero_do_nome(nome),
            "rect_pdf": (x1, y1, x2, y2),
            "pos_top_left": (pos_x, pos_y_top),
            "w": w, "h": h
        })

    return width, height, fields

def carrega_base(json_base: Path):
    if json_base.exists():
        with open(json_base, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def gera_debug_pdf(width, height, fields, out_pdf: Path):
    # desenha caixas sobre o mockup para conferência
    c = canvas.Canvas(str(out_pdf), pagesize=(width, height))
    c.setFillColor(Color(0,0,0,0))
    for item in fields:
        x, y = item["pos_top_left"]
        w, h = item["w"], item["h"]
        c.setStrokeColor(red)
        c.rect(x, y, w, h, stroke=1, fill=0)
        c.setFillColor(blue)
        c.drawString(x+2, y+h+4, item["numero"])
        c.setFillColor(Color(0,0,0,0))
    c.save()

# ========== EXECUÇÃO ==========

if __name__ == "__main__":
    if not MOCKUP_PDF.exists():
        raise SystemExit(f"❌ Mockup não encontrado: {MOCKUP_PDF}")

    w, h, fields = extrai_rects(MOCKUP_PDF)
    print(f"Mockup: {MOCKUP_PDF}  ({w:.1f} x {h:.1f} pts)  Campos: {len(fields)}")

    base = carrega_base(JSON_BASE)

    # Começa o coords novo
    coords_out = {"_ref_width": w, "_ref_height": h}

    # Se existe base, herda tudo; depois só atualiza pos das chaves mapeadas
    if base:
        coords_out.update({k: v for k, v in base.items() if not k.startswith("_ref_")})

    # Aplica posições com base no mapeamento
    usados = 0
    for item in fields:
        num = item["numero"]
        if num in MAPEAMENTO:
            chave = MAPEAMENTO[num]
            x, y = item["pos_top_left"]
            # Se já existe a chave (da base), só troca pos; senão cria simples:
            if chave in coords_out:
                coords_out[chave]["pos"] = [round(x,2), round(y,2)]
            else:
                coords_out[chave] = {
                    "texto": "",
                    "font": "Helvetica",
                    "pt": 22,
                    "pos": [round(x,2), round(y,2)],
                    "align": "left"
                }
            usados += 1

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(coords_out, f, ensure_ascii=False, indent=2)

    # PDF de conferência (caixas)
    gera_debug_pdf(w, h, fields, DEBUG_PDF)

    print(f"✅ Gerado: {OUT_JSON}")
    print(f"🔍 Conferência: {DEBUG_PDF}")
    faltando = len([i for i in MAPEAMENTO if i not in [f['numero'] for f in fields]])
    if faltando:
        print("⚠️ Atenção: há números no MAPEAMENTO que não existem no PDF.")