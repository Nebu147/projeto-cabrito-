from __future__ import annotations
import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Dict, Any, Tuple

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk


# ---------------------- Utils ----------------------
def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------- App ----------------------
class CoordEditor(tk.Tk):
    """Editor para arrastar caixinhas em cima do gabarito e salvar coordenadas.

    Recursos:
    - Salva por padrão em .\data\coords_editado.json (mostra caminho completo)
    - Setas movem a caixa selecionada (Shift=10px; Ctrl+setas funcionam mesmo sem foco)
    - Scroll do mouse: ROLA a página (vertical). Shift+scroll = rolagem horizontal.
      Ctrl+scroll = ZOOM (opcional).
    - Botões Zoom +/-, rótulos on/off, arrastar com o mouse.
    """

    def __init__(self, bg_img_path: Path, coords_path: Path, out_path: Path):
        super().__init__()
        self.title("Editor de coordenadas do bilhete")

        # Caminhos
        self.bg_img_path = bg_img_path.resolve()
        self.coords_path = coords_path.resolve()
        self.out_path = out_path.resolve()

        # Dados
        self.coords: Dict[str, Any] = load_json(self.coords_path)
        self.ref_w = int(self.coords.get("_ref_width", 0))
        self.ref_h = int(self.coords.get("_ref_height", 0))
        if not self.ref_w or not self.ref_h:
            messagebox.showerror("Erro", "JSON precisa de _ref_width/_ref_height")
            self.destroy()
            return

        # Imagem
        try:
            self.img = Image.open(self.bg_img_path)
        except Exception as e:
            messagebox.showerror("Erro ao abrir imagem", f"{self.bg_img_path}\n\n{e}")
            self.destroy()
            return

        if self.img.size != (self.ref_w, self.ref_h):
            messagebox.showwarning(
                "Atenção",
                f"Tamanho do PNG ({self.img.size[0]}x{self.img.size[1]}) \n"
                f"≠ _ref_width/_ref_height ({self.ref_w}x{self.ref_h}).\n"
                f"Use o mesmo tamanho para evitar deslocamentos."
            )

        # Estado de zoom
        self.zoom = 1.0
        self.min_zoom, self.max_zoom = 0.25, 4.0

        # Canvas (com rolagem)
        self.canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        self.canvas.grid(row=1, column=0, columnspan=6, sticky="nsew")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # Imagem renderizada
        self.tk_img = ImageTk.PhotoImage(self.img)
        self.img_id = self.canvas.create_image(0, 0, image=self.tk_img, anchor="nw")

        # Barra superior / toolbar
        self._build_toolbar()

        # Shapes -> {name: (rect_id, text_id)}
        self.shapes: Dict[str, Tuple[int, int]] = {}
        self.selected_name: str | None = None
        self.show_labels = tk.BooleanVar(value=True)

        # Desenha & binds
        self._draw_all()
        self._setup_bindings()

        # Barra de status
        self.status = tk.StringVar(value="Pronto")
        ttk.Label(self, textvariable=self.status).grid(row=2, column=0, columnspan=6, sticky="we", padx=6, pady=4)
        self._update_status_path()

    # ---------- UI ----------
    def _build_toolbar(self):
        pad = {"padx": 6, "pady": 6}
        ttk.Label(self, text="Campo:").grid(row=0, column=0, **pad, sticky="w")
        self.cmb = ttk.Combobox(self, state="readonly", width=36, values=self._field_names())
        self.cmb.grid(row=0, column=1, **pad, sticky="w")
        self.cmb.bind("<<ComboboxSelected>>", self._select_from_combo)
        # Bloqueia setas dentro do combobox (pra ele não roubar as teclas)
        for k in ("<Up>", "<Down>", "<Left>", "<Right>"):
            self.cmb.bind(k, lambda e: "break")

        ttk.Button(self, text="Rótulos (L)", command=self._toggle_labels).grid(row=0, column=2, **pad)
        ttk.Button(self, text="Zoom -", command=lambda: self._set_zoom(self.zoom * 0.9)).grid(row=0, column=3, **pad)
        ttk.Button(self, text="Zoom +", command=lambda: self._set_zoom(self.zoom * 1.1)).grid(row=0, column=4, **pad)
        ttk.Button(self, text="Salvar (Ctrl+S)", command=self.save).grid(row=0, column=5, **pad)

    def _field_names(self):
        return [k for k in self.coords.keys() if not k.startswith("_")]

    # ---------- DRAW ----------
    def _draw_all(self):
        # Limpa (menos imagem)
        for name, (rid, tid) in list(self.shapes.items()):
            self.canvas.delete(rid); self.canvas.delete(tid)
        self.shapes.clear()

        for name in self._field_names():
            meta = self.coords[name]
            x, y = meta.get("pos", [0, 0])
            pt = float(meta.get("pt", 22))
            w, h = pt * 4, pt * 1.2

            rx, ry = x * self.zoom, y * self.zoom
            rw, rh = w * self.zoom, h * self.zoom

            rect = self.canvas.create_rectangle(rx, ry, rx + rw, ry + rh, outline="#2a7", width=2)
            label = self.canvas.create_text(rx + 2, ry - 10, anchor="sw", text=name, fill="#c00")
            if not self.show_labels.get():
                self.canvas.itemconfigure(label, state="hidden")
            self.shapes[name] = (rect, label)

        self.canvas.config(width=int(self.img.width * self.zoom), height=int(self.img.height * self.zoom))
        self._render_bg()

        # Define a área rolável do canvas (precisa para yview/xview funcionar até o fim)
        self.canvas.configure(scrollregion=(0, 0, int(self.img.width * self.zoom), int(self.img.height * self.zoom)))

    def _render_bg(self):
        zw = max(1, int(self.img.width * self.zoom))
        zh = max(1, int(self.img.height * self.zoom))
        img2 = self.img.resize((zw, zh), Image.NEAREST)
        self.tk_img = ImageTk.PhotoImage(img2)
        self.canvas.itemconfigure(self.img_id, image=self.tk_img)

    # ---------- EVENTS ----------
    def _setup_bindings(self):
        # Mouse
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # Atalhos gerais
        self.bind("<Control-s>", lambda e: self.save())
        self.bind("<l>", lambda e: self._toggle_labels())

        # Setas no CANVAS (precisa de foco no canvas)
        for seq, dx, dy in [
            ("<Left>", -1, 0), ("<Right>", 1, 0), ("<Up>", 0, -1), ("<Down>", 0, 1),
            ("<Shift-Left>", -10, 0), ("<Shift-Right>", 10, 0),
            ("<Shift-Up>", 0, -10), ("<Shift-Down>", 0, 10),
        ]:
            self.canvas.bind(seq, lambda e, dx=dx, dy=dy: self._nudge(dx, dy))

        # Failsafe: Ctrl+setas funcionam mesmo sem foco no canvas
        for seq, dx, dy in [
            ("<Control-Left>", -1, 0), ("<Control-Right>", 1, 0),
            ("<Control-Up>", 0, -1), ("<Control-Down>", 0, 1),
        ]:
            self.bind(seq, lambda e, dx=dx, dy=dy: self._nudge(dx, dy))

        # --- Scroll do mouse: rolagem por padrão ---
        # Windows/macOS: roda vertical; Ctrl+rodinha = zoom; Shift+rodinha = horizontal
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_wheel_h)
        # Linux (X11): botões 4/5 simulam scroll
        self.canvas.bind("<Button-4>",   lambda e: self._on_wheel_linux(e, +1))
        self.canvas.bind("<Button-5>",   lambda e: self._on_wheel_linux(e, -1))

    def _toggle_labels(self):
        self.show_labels.set(not self.show_labels.get())
        for _, (_, tid) in self.shapes.items():
            self.canvas.itemconfigure(tid, state="normal" if self.show_labels.get() else "hidden")

    def _set_zoom(self, z: float):
        self.zoom = max(self.min_zoom, min(self.max_zoom, z))
        self._draw_all()
        if self.selected_name:
            self._highlight(self.selected_name)

    # --- Handlers de scroll/zoom ---
    def _on_wheel(self, ev):
        # Ctrl + rodinha = ZOOM; senão, rolagem vertical
        if ev.state & 0x0004:  # Ctrl
            factor = 1.1 if ev.delta > 0 else 0.9
            self._set_zoom(self.zoom * factor)
        else:
            self.canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")
        self.canvas.focus_set()

    def _on_wheel_h(self, ev):
        # Shift + rodinha = rolagem horizontal
        self.canvas.xview_scroll(int(-1 * (ev.delta / 120)), "units")
        self.canvas.focus_set()

    def _on_wheel_linux(self, ev, direction):
        # direction: +1 = para cima, -1 = para baixo
        if ev.state & 0x0004:  # Ctrl
            factor = 1.1 if direction > 0 else 0.9
            self._set_zoom(self.zoom * factor)
        else:
            self.canvas.yview_scroll(-1 * direction, "units")
        self.canvas.focus_set()

    def _select_from_combo(self, _):
        name = self.cmb.get()
        self._select(name)
        self.canvas.focus_set()  # volta foco pro canvas

    def _select(self, name: str | None):
        self.selected_name = name
        self._highlight(name)
        if name:
            self.status.set(f"Selecionado: {name}  pos={self.coords[name].get('pos')}")
        else:
            self.status.set("Pronto")

    def _highlight(self, name: str | None):
        for n, (rid, _) in self.shapes.items():
            self.canvas.itemconfigure(rid, outline="#2a7", width=2)
        if name and name in self.shapes:
            rid, _ = self.shapes[name]
            self.canvas.itemconfigure(rid, outline="#06f", width=3)

    def _hit_test(self, x, y) -> str | None:
        candidates = []
        for name, (rid, _) in self.shapes.items():
            x1, y1, x2, y2 = self.canvas.coords(rid)
            if x1 <= x <= x2 and y1 <= y <= y2:
                area = (x2 - x1) * (y2 - y1)
                candidates.append((area, name))
        # pega a menor área (mais “em cima”)
        return min(candidates)[1] if candidates else None


    def _on_click(self, ev):
        self.canvas.focus_set()  # garante que as setas vão pro canvas
        name = self._hit_test(ev.x, ev.y)
        self._select(name)
        self.drag_offset = None
        if name:
            rid, _ = self.shapes[name]
            x1, y1, x2, y2 = self.canvas.coords(rid)
            self.drag_offset = (ev.x - x1, ev.y - y1)

    def _on_drag(self, ev):
        if not self.selected_name or not self.drag_offset:
            return
        dx, dy = self.drag_offset
        rid, tid = self.shapes[self.selected_name]
        x1 = ev.x - dx
        y1 = ev.y - dy
        x2 = x1 + (self.canvas.coords(rid)[2] - self.canvas.coords(rid)[0])
        y2 = y1 + (self.canvas.coords(rid)[3] - self.canvas.coords(rid)[1])
        self.canvas.coords(rid, x1, y1, x2, y2)
        self.canvas.coords(tid, x1 + 2, y1 - 10)
        # Atualiza pos (desfaz zoom)
        self.coords[self.selected_name]["pos"] = [round(x1 / self.zoom, 2), round(y1 / self.zoom, 2)]
        self.status.set(f"Arrastando {self.selected_name} → {self.coords[self.selected_name]['pos']}")

    def _on_release(self, _):
        self.drag_offset = None

    def _nudge(self, dx: int, dy: int):
        if not self.selected_name:
            return
        name = self.selected_name
        rid, tid = self.shapes[name]
        self.canvas.move(rid, dx, dy)
        self.canvas.move(tid, dx, dy)
        x1, y1, _, _ = self.canvas.coords(rid)
        self.coords[name]["pos"] = [round(x1 / self.zoom, 2), round(y1 / self.zoom, 2)]
        self.status.set(f"Nudge {name} → {self.coords[name]['pos']}")

    # ---------- SAVE ----------
    def save(self):
        try:
            save_json(self.out_path, self.coords)
            messagebox.showinfo("Salvo", f"Coordenadas salvas em:\n{self.out_path}")
            print(f"[editor] Coordenadas salvas em: {self.out_path}")
            self._update_status_path(saved=True)
        except Exception as e:
            messagebox.showerror("Erro ao salvar", str(e))

    def _update_status_path(self, saved: bool = False):
        msg = f"Saída: {self.out_path}"
        if saved:
            msg += "  (OK)"
        self.status.set(msg)


# ---------------------- Main ----------------------
def main():
    ap = ArgumentParser(description="Editor para arrastar caixinhas e salvar coordenadas em JSON.")
    ap.add_argument("--bg", required=True, help="PNG do gabarito (ex.: 603x2048).")
    ap.add_argument("--coords", required=True, help="JSON com _ref_width/_ref_height e campos.")
    ap.add_argument("--out", help="JSON de saída. Se não passar, salva em .\\data\\coords_editado.json")
    args = ap.parse_args()

    base = Path.cwd()
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    bg = Path(args.bg).expanduser().resolve()
    coords = Path(args.coords).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve() if args.out else (data_dir / "coords_editado.json").resolve()

    print(f"[editor] Saída configurada para: {out_path}")

    app = CoordEditor(bg, coords, out_path)
    app.mainloop()


if __name__ == "__main__":
    main()
