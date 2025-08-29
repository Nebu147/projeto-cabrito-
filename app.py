# interface/app.py — GUI para Ticket/Controle com presets e geração via subprocess
from __future__ import annotations
import json, os, sys, subprocess
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTextEdit, QLabel, QCheckBox, QPushButton, QDoubleSpinBox,
    QFormLayout, QLineEdit, QMessageBox, QFileDialog, QComboBox
)

# --------- Paths do projeto (assumindo app.py dentro de interface/) ----------
ROOT   = Path(__file__).resolve().parents[1]     # .../bilhetes
ASSETS = ROOT / "assets"
DATA   = ROOT / "data"
OUT    = ROOT / "out"
SRC    = ROOT / "src"

BG_TICKET   = ASSETS / "bg_ticket-APAGADO.pdf"
BG_CONTROLE = ASSETS / "bg_controle.pdf"

COORDS_TICKET   = DATA / "coords_ticket_100_com_texto.json"
COORDS_CONTROLE = DATA / "coords_controle.json"

VARS_TICKET   = DATA / "ticket.json"
VARS_CONTROLE = DATA / "controle.json"

GERA_TICKET   = SRC / "gera_ticket.py"
GERA_CONTROLE = SRC / "gera_controle.py"

# ---------- util ----------
def load_json(p: Path) -> Dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def save_json(p: Path, data: Dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def open_file(p: Path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # type: ignore
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)], check=False)
        else:
            subprocess.run(["xdg-open", str(p)], check=False)
    except Exception:
        pass

def ensure_dirs():
    for d in (ASSETS, DATA, OUT, SRC):
        d.mkdir(parents=True, exist_ok=True)

# ---------- Form dinâmico baseado num JSON ----------
class JsonForm(QWidget):
    """
    Gera campos (QLineEdit) a partir das chaves de um JSON.
    Suporta presets por tipo (Ticket/Controle).
    """
    def __init__(self, json_path: Path, title: str):
        super().__init__()
        self.json_path = json_path
        self.title = title  # "Ticket" | "Controle"
        self.fields: Dict[str, QLineEdit] = {}
        self.presets_dir = DATA / "presets" / title.lower()
        self.presets_dir.mkdir(parents=True, exist_ok=True)

        self.setLayout(QVBoxLayout())

        # linha de presets
        top = QHBoxLayout()
        top.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self._refresh_presets()
        btn_preset_load = QPushButton("Aplicar")
        btn_preset_save = QPushButton("Salvar como...")
        top.addWidget(self.preset_combo, 1)
        top.addWidget(btn_preset_load)
        top.addWidget(btn_preset_save)
        self.layout().addLayout(top)

        # formulário
        self.form = QFormLayout()
        self.layout().addLayout(self.form, 1)

        # botões arquivo
        row = QHBoxLayout()
        self.btn_reload = QPushButton("Recarregar JSON")
        self.btn_save   = QPushButton("Salvar JSON")
        row.addWidget(self.btn_reload)
        row.addWidget(self.btn_save)
        self.layout().addLayout(row)

        # área de log (vai ser injetada pela Main)
        self.log: Optional[QTextEdit] = None

        # eventos
        self.btn_reload.clicked.connect(self.reload)
        self.btn_save.clicked.connect(self.save)
        btn_preset_load.clicked.connect(self.apply_preset)
        btn_preset_save.clicked.connect(self.save_preset_as)

        # inicializa
        self.reload()

    # ------- presets -------
    def _refresh_presets(self):
        self.preset_combo.clear()
        items = ["(nenhum)"] + [p.stem for p in sorted(self.presets_dir.glob("*.json"))]
        self.preset_combo.addItems(items)

    def apply_preset(self):
        name = self.preset_combo.currentText()
        if name == "(nenhum)":
            return
        path = self.presets_dir / f"{name}.json"
        if not path.exists():
            QMessageBox.warning(self, "Preset", "Arquivo de preset não encontrado.")
            return
        data = load_json(path)
        # aplica sobre os campos existentes
        for k, edit in self.fields.items():
            if k in data:
                edit.setText(str(data[k]))
        if self.log:
            self.log.append(f"[Preset] Aplicado: {path.name}")

    def save_preset_as(self):
        path_str, ok = QFileDialog.getSaveFileName(
            self, "Salvar preset", str(self.presets_dir / "meu_preset.json"),
            "JSON (*.json)"
        )
        if not ok or not path_str:
            return
        path = Path(path_str)
        data = self.collect()
        save_json(path, data)
        self._refresh_presets()
        if self.log:
            self.log.append(f"[Preset] Salvo: {path.name}")

    # ------- json -------
    def reload(self):
        data = load_json(self.json_path)
        # limpa form
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields.clear()
        # cria campos
        for k in data.keys():
            edit = QLineEdit(str(data.get(k, "")))
            edit.setClearButtonEnabled(True)
            self.form.addRow(QLabel(k), edit)
            self.fields[k] = edit
        if self.log:
            self.log.append(f"[JSON] Carregado: {self.json_path}")

    def collect(self) -> Dict:
        return {k: w.text() for k, w in self.fields.items()}

    def save(self):
        data = self.collect()
        save_json(self.json_path, data)
        QMessageBox.information(self, "OK", f"Salvo em {self.json_path}")
        if self.log:
            self.log.append(f"[JSON] Salvo: {self.json_path}")

# ---------- Janela principal ----------
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.setWindowTitle("Editor de Bilhetes (Ticket / Controle)")
        self.resize(1000, 740)

        tabs = QTabWidget()

        # --- Aba Ticket ---
        self.ticket = JsonForm(VARS_TICKET, title="Ticket")
        box_t = QHBoxLayout()
        self.basefix = QDoubleSpinBox()
        self.basefix.setRange(0.00, 2.00)
        self.basefix.setSingleStep(0.05)
        self.basefix.setValue(1.00)  # você disse que 1.00 alinhou perfeito
        self.invertY_ticket = QCheckBox("invert-y")
        self.invertY_ticket.setChecked(True)
        self.proof = QCheckBox("proof")
        self.proof.setChecked(False)
        btn_gera_ticket = QPushButton("Gerar TICKET PDF")
        box_t.addWidget(QLabel("baseline-fix:"))
        box_t.addWidget(self.basefix)
        box_t.addWidget(self.invertY_ticket)
        box_t.addWidget(self.proof)
        box_t.addStretch(1)
        box_t.addWidget(btn_gera_ticket)
        self.ticket.layout().addLayout(box_t)
        tabs.addTab(self.ticket, "Ticket")

        # --- Aba Controle ---
        self.controle = JsonForm(VARS_CONTROLE, title="Controle")
        box_c = QHBoxLayout()
        self.invertY_ctrl = QCheckBox("invert-y")
        self.invertY_ctrl.setChecked(True)   # CONTROLE usa invert-y
        btn_gera_ctrl = QPushButton("Gerar CONTROLE PDF")
        box_c.addWidget(self.invertY_ctrl)
        box_c.addStretch(1)
        box_c.addWidget(btn_gera_ctrl)
        self.controle.layout().addLayout(box_c)
        tabs.addTab(self.controle, "Controle")

        # --- Central + LOG embaixo ---
        central = QWidget()
        v = QVBoxLayout(central)
        v.addWidget(tabs, 1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(180)
        # injeta log nos forms
        self.ticket.log = self.log
        self.controle.log = self.log
        v.addWidget(self.log)

        self.setCentralWidget(central)

        # --- Conexões ---
        btn_gera_ticket.clicked.connect(self.run_ticket)
        btn_gera_ctrl.clicked.connect(self.run_controle)

        self.statusBar().showMessage(str(ROOT))
        self._log(f"ROOT = {ROOT}")

    # ------------ helpers ------------
    def _log(self, msg: str):
        self.log.append(msg)
        self.log.ensureCursorVisible()

    def _check_paths_ticket(self) -> bool:
        missing = []
        for p in (GERA_TICKET, BG_TICKET, COORDS_TICKET, VARS_TICKET):
            if not p.exists():
                missing.append(str(p.relative_to(ROOT)))
        if missing:
            QMessageBox.critical(self, "Arquivos ausentes",
                                 "Estes caminhos não foram encontrados:\n" + "\n".join(missing))
            return False
        return True

    def _check_paths_controle(self) -> bool:
        missing = []
        for p in (GERA_CONTROLE, BG_CONTROLE, COORDS_CONTROLE, VARS_CONTROLE):
            if not p.exists():
                missing.append(str(p.relative_to(ROOT)))
        if missing:
            QMessageBox.critical(self, "Arquivos ausentes",
                                 "Estes caminhos não foram encontrados:\n" + "\n".join(missing))
            return False
        return True

    # ------------ ações ------------
    def run_ticket(self):
        if not self._check_paths_ticket():
            return
        # salva JSON antes
        self.ticket.save()

        cmd = [
    sys.executable, str(GERA_TICKET),
    "--bg", str(BG_TICKET),
    "--coords", str(COORDS_TICKET),
    "--vars", str(VARS_TICKET),
    "--out", str(OUT / "ticket_final.pdf"),
    "--invert-y",
    "--baseline-fix", f"{self.basefix.value():.2f}",
]
        
        if self.proof.isChecked():
            cmd.append("--proof")

        OUT.mkdir(parents=True, exist_ok=True)
        self._log("[CMD] " + " ".join(cmd))
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self._log(cp.stdout or "(ok)")
            open_file(OUT / "ticket_final.pdf")
        except subprocess.CalledProcessError as e:
            self._log((e.stdout or "") + "\n" + (e.stderr or ""))
            QMessageBox.critical(self, "Erro ao gerar TICKET", e.stderr or "Falha.")

    def run_controle(self):
        if not self._check_paths_controle():
            return
        # salva JSON antes
        self.controle.save()

        cmd = [
            sys.executable, str(GERA_CONTROLE),
            "--bg", str(BG_CONTROLE),
            "--coords", str(COORDS_CONTROLE),
            "--vars", str(VARS_CONTROLE),
            "--out", str(OUT / "controle_final.pdf"),
            "--invert-y",
        ]
        OUT.mkdir(parents=True, exist_ok=True)
        self._log("[CMD] " + " ".join(cmd))
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self._log(cp.stdout or "(ok)")
            open_file(OUT / "controle_final.pdf")
        except subprocess.CalledProcessError as e:
            self._log((e.stdout or "") + "\n" + (e.stderr or ""))
            QMessageBox.critical(self, "Erro ao gerar CONTROLE", e.stderr or "Falha.")

# ---------- main ----------
def main():
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()