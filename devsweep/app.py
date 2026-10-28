"""Tk desktop interface; workers never access Tk objects."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import Candidate, ScanOptions, export_csv, export_json, format_size, recycle_candidates, scan
from .windows import fixed_drives

BG, PANEL, TEXT, MUTED, ACCENT = "#10151f", "#192130", "#eaf1fa", "#9baabd", "#7de2b9"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DevSweep · Dependências sob controle")
        self.geometry("1160x760")
        self.minsize(920, 650)
        self.configure(bg=BG)
        self.roots = [Path.home()]
        self.candidates: dict[str, Candidate] = {}
        self.last_scan_result = None
        self.checked: set[str] = set()
        self.messages: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.sort_reverse: dict[str, bool] = {}
        self.root_text = tk.StringVar(value=str(self.roots[0]))
        self.status = tk.StringVar(value="Escolha o alcance da busca. Nenhuma pasta será alterada ao escanear.")
        self.days = tk.StringVar(value="60")
        self.minimum = tk.StringVar(value="10")
        self.node, self.venv, self.caches = (tk.BooleanVar(value=True) for _ in range(3))
        self.found_text, self.selected_text, self.size_text = (tk.StringVar(value="0") for _ in range(3))
        self.size_text.set("0 B")
        self._theme()
        self._layout()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self.poll)

    def _theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TButton", background="#28354a", foreground=TEXT, padding=(14, 9), borderwidth=0, font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#364964"), ("disabled", "#202a39")], foreground=[("disabled", "#68788e")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#10251e", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#a8efd2"), ("disabled", "#334c47")])
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=8)
        style.configure("TSpinbox", fieldbackground=PANEL, foreground=TEXT, arrowcolor=TEXT, padding=6)
        style.configure("TCheckbutton", background=BG, foreground=TEXT, padding=(0, 5), font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=35, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#233047", foreground=MUTED,
                        padding=10, relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#29463f")], foreground=[("selected", "#ffffff")])

    def _layout(self):
        main = ttk.Frame(self, padding=26)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="D E V S W E E P", foreground=ACCENT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(main, text="Encontre o peso dos projetos antigos.", font=("Segoe UI", 24, "bold")).pack(anchor="w", pady=(8, 4))
        ttk.Label(main, text="Node.js e Python · busca local · revisão antes da limpeza", style="Muted.TLabel").pack(anchor="w")
        scope = ttk.Frame(main)
        scope.pack(fill="x", pady=(24, 12))
        self.scope_entry = ttk.Entry(scope, textvariable=self.root_text, state="readonly")
        self.scope_entry.pack(side="left", fill="x", expand=True)
        self.choose_button = ttk.Button(scope, text="Escolher pasta", command=self.choose_root)
        self.choose_button.pack(side="left", padx=8)
        self.drives_button = ttk.Button(scope, text="Discos locais", command=self.choose_drives)
        self.drives_button.pack(side="left")
        filters = ttk.Frame(main)
        filters.pack(fill="x")
        self.filter_controls = []
        for label, variable in (("node_modules", self.node), ("Ambientes Python", self.venv), ("Caches Python", self.caches)):
            control = ttk.Checkbutton(filters, text=label, variable=variable)
            control.pack(side="left", padx=(0, 17))
            self.filter_controls.append(control)
        ttk.Label(filters, text="Sem alteração há").pack(side="left", padx=(8, 4))
        self.days_entry = ttk.Spinbox(filters, from_=0, to=36500, width=5, textvariable=self.days)
        self.days_entry.pack(side="left")
        ttk.Label(filters, text="dias · mínimo").pack(side="left", padx=5)
        self.min_entry = ttk.Spinbox(filters, from_=0, to=1000000, width=6, textvariable=self.minimum)
        self.min_entry.pack(side="left")
        ttk.Label(filters, text="MiB").pack(side="left", padx=5)
        toolbar = ttk.Frame(main)
        toolbar.pack(fill="x", pady=(14, 16))
        self.scan_button = ttk.Button(toolbar, text="Escanear", style="Accent.TButton", command=self.start_scan)
        self.scan_button.pack(side="left")
        self.stop_button = ttk.Button(toolbar, text="Interromper", state="disabled", command=self.cancel.set)
        self.stop_button.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(toolbar, mode="indeterminate", length=150)
        self.progress.pack(side="right", padx=(10, 0))
        summary = ttk.Frame(main)
        summary.pack(fill="x", pady=(0, 16))
        for label, variable in (("PASTAS EXIBIDAS", self.found_text), ("SELECIONADAS", self.selected_text), ("TAMANHO SELECIONADO", self.size_text)):
            card = ttk.Frame(summary, style="Card.TFrame", padding=(16, 12))
            card.pack(side="left", fill="both", expand=True, padx=(0, 10))
            ttk.Label(card, text=label, background=PANEL, foreground=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
            ttk.Label(card, textvariable=variable, background=PANEL, font=("Segoe UI", 21, "bold")).pack(anchor="w", pady=(3, 0))
        table = ttk.Frame(main)
        table.pack(fill="both", expand=True)
        columns = ("mark", "kind", "size", "age", "path", "state")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        specifications = [("mark", "", 40), ("kind", "TIPO", 105), ("size", "TAMANHO", 100),
                          ("age", "DIAS¹", 65), ("path", "PASTA", 390), ("state", "REVISÃO", 170)]
        for key, label, width in specifications:
            self.tree.heading(key, text=label, command=lambda column=key: self.sort(column))
            self.tree.column(key, width=width, minwidth=width if key != "path" else 160, stretch=key in {"path", "state"})
        scroll_y = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree.bind("<Button-1>", self.on_click)
        self.tree.bind("<space>", self.on_space)
        self.tree.bind("<Double-1>", self.show_details)
        self.tree.tag_configure("blocked", foreground="#b7a99a")
        ttk.Label(main, text="¹ Última alteração observada nas dependências e nos arquivos do projeto; não comprova desuso.",
                  style="Muted.TLabel", font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 3))
        ttk.Label(main, text="O espaço só é liberado ao esvaziar a Lixeira. O tamanho exibido é uma estimativa lógica.",
                  style="Muted.TLabel", font=("Segoe UI", 9)).pack(anchor="w")
        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(14, 0))
        self.mark_button = ttk.Button(actions, text="Marcar exibidas", command=self.mark_all)
        self.mark_button.pack(side="left")
        self.clear_button = ttk.Button(actions, text="Desmarcar", command=self.clear_all)
        self.clear_button.pack(side="left", padx=8)
        self.export_button = ttk.Button(actions, text="Exportar relatório", command=self.export)
        self.export_button.pack(side="left")
        self.trash_button = ttk.Button(actions, text="Enviar selecionadas à Lixeira", state="disabled", command=self.start_cleanup)
        self.trash_button.pack(side="right")
        ttk.Label(main, textvariable=self.status, style="Muted.TLabel", wraplength=1060).pack(anchor="w", pady=(14, 0))

    def choose_root(self):
        path = filedialog.askdirectory(title="Escolha uma pasta para escanear")
        if path:
            self.roots = [Path(path)]
            self.root_text.set(path)

    def choose_drives(self):
        try:
            roots = fixed_drives()
            if not roots:
                raise OSError("Nenhum disco local disponível.")
            self.roots = roots
            self.root_text.set(" | ".join(map(str, roots)))
        except OSError as error:
            messagebox.showerror("Discos locais", str(error))

    def set_busy(self, value: bool, scanning: bool = False):
        self.busy = value
        for widget in [self.choose_button, self.drives_button, self.scan_button, self.days_entry,
                       self.min_entry, self.mark_button, self.clear_button, self.export_button, *self.filter_controls]:
            widget.configure(state="disabled" if value else "normal")
        self.stop_button.configure(state="normal" if value and scanning else "disabled")
        self.trash_button.configure(state="normal" if self.checked and not value else "disabled")
        self.progress.start(12) if value else self.progress.stop()

    def start_scan(self):
        try:
            days, minimum = int(self.days.get()), float(self.minimum.get().replace(",", "."))
            if days < 0 or minimum < 0 or not __import__("math").isfinite(minimum):
                raise ValueError
        except ValueError:
            messagebox.showerror("Filtros", "Informe dias e tamanho mínimo válidos, a partir de zero.")
            return
        options = ScanOptions(self.node.get(), self.venv.get(), self.caches.get())
        if not any((options.node, options.venv, options.caches)):
            messagebox.showinfo("Tipos de pasta", "Selecione pelo menos um tipo de pasta.")
            return
        roots = list(self.roots)
        self.cancel.clear()
        self.checked.clear()
        self.candidates.clear()
        self.last_scan_result = None
        self.tree.delete(*self.tree.get_children())
        self.update_totals()
        self.set_busy(True, scanning=True)
        self.status.set("Buscando pastas; o disco pode levar alguns minutos para ser percorrido…")

        def worker():
            try:
                result = scan(roots, options, self.cancel,
                              lambda current, path: self.messages.put(("progress", (current.visited, str(path)))))
                visible = [item for item in result.candidates if item.age_days() >= days and item.snapshot.size >= minimum * 1024**2]
                self.messages.put(("scanned", (result, visible)))
            except Exception as error:
                self.messages.put(("error", str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def add_rows(self, candidates: list[Candidate]):
        for item in candidates:
            iid = str(len(self.candidates))
            self.candidates[iid] = item
            self.tree.insert("", "end", iid=iid, values=("☐", item.kind, format_size(item.snapshot.size),
                             item.age_days(), str(item.path), item.blocked or "Aguardando seleção"),
                             tags=("blocked",) if item.blocked else ())
        self.update_totals()

    def toggle(self, iid: str):
        if self.busy or not iid:
            return
        item = self.candidates[iid]
        if item.blocked:
            self.status.set(item.blocked)
            return
        self.checked.symmetric_difference_update({iid})
        self.tree.set(iid, "mark", "☑" if iid in self.checked else "☐")
        self.update_totals()

    def on_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            self.toggle(self.tree.identify_row(event.y))

    def on_space(self, _event):
        selected = self.tree.selection()
        if selected:
            self.toggle(selected[0])
        return "break"

    def mark_all(self):
        for iid in self.tree.get_children():
            if not self.candidates[iid].blocked:
                self.checked.add(iid)
                self.tree.set(iid, "mark", "☑")
        self.update_totals()

    def clear_all(self):
        self.checked.clear()
        for iid in self.tree.get_children():
            self.tree.set(iid, "mark", "☐")
        self.update_totals()

    def update_totals(self):
        self.found_text.set(str(len(self.candidates)))
        self.selected_text.set(str(len(self.checked)))
        self.size_text.set(format_size(sum(self.candidates[iid].snapshot.size for iid in self.checked)))
        self.trash_button.configure(state="normal" if self.checked and not self.busy else "disabled")

    def sort(self, column: str):
        reverse = not self.sort_reverse.get(column, False)
        self.sort_reverse[column] = reverse
        def value(iid):
            item = self.candidates[iid]
            return {"size": item.snapshot.size, "age": item.age_days(), "mark": iid in self.checked,
                    "kind": item.kind, "path": str(item.path).lower(), "state": item.blocked}[column]
        for index, iid in enumerate(sorted(self.tree.get_children(), key=value, reverse=reverse)):
            self.tree.move(iid, "", index)

    def show_details(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        item = self.candidates[selected[0]]
        modified = datetime.fromtimestamp(item.newest_ns / 1e9).strftime("%d/%m/%Y %H:%M")
        messagebox.showinfo("Detalhes da pasta", f"{item.path}\n\nTipo: {item.kind}\nProjeto: {item.project}\n"
                            f"Tamanho lógico: {format_size(item.snapshot.size)}\nArquivos: {item.snapshot.files}\n"
                            f"Última alteração observada: {modified}\n\n{item.blocked or 'Disponível para revisão.'}")

    def export(self):
        if not self.candidates:
            messagebox.showinfo("Relatório", "Faça uma busca primeiro.")
            return
        destination = filedialog.asksaveasfilename(title="Exportar inventário", defaultextension=".csv",
                                                 initialfile="devsweep-inventario",
                                                 filetypes=[("CSV", "*.csv"), ("JSON", "*.json")])
        if destination:
            try:
                path = Path(destination)
                candidates = list(self.candidates.values())
                if path.suffix.lower() == ".json":
                    export_json(candidates, path, self.last_scan_result)
                else:
                    export_csv(candidates, path)
                self.status.set(f"Inventário exportado: {destination}")
            except OSError as error:
                messagebox.showerror("Exportar", str(error))

    def start_cleanup(self):
        selected = [self.candidates[iid] for iid in self.checked]
        if not selected or self.busy:
            return
        preview = "\n".join(str(item.path) for item in selected[:6])
        if len(selected) > 6:
            preview += f"\n… e mais {len(selected) - 6} pastas."
        if not messagebox.askyesno("Revisar envio à Lixeira",
            f"Enviar {len(selected)} pasta(s), {self.size_text.get()}, à Lixeira?\n\n{preview}\n\n"
            "Feche os programas que usam esses projetos. Ambientes virtuais podem conter arquivos que você salvou neles.\n"
            "Você pode restaurar pela Lixeira; reinstalar dependências exige os arquivos do projeto.", default="no"):
            return
        self.set_busy(True)
        self.status.set("Revalidando pastas selecionadas e enviando à Lixeira…")

        def worker():
            try:
                results = recycle_candidates(selected)
                self.messages.put(("cleaned", results))
            except Exception as error:
                self.messages.put(("error", str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "progress":
                    count, path = payload
                    self.status.set(f"{count:,} pastas percorridas · {path[-115:]}")
                elif kind == "scanned":
                    result, visible = payload
                    self.last_scan_result = result
                    self.add_rows(visible)
                    self.set_busy(False)
                    label = "Busca interrompida; resultado parcial" if result.cancelled else "Busca concluída"
                    self.status.set(f"{label} · {len(visible)} exibidas de {len(result.candidates)} encontradas · "
                                    f"{result.errors} falhas de acesso · {result.skipped} pastas ignoradas.")
                elif kind == "cleaned":
                    successes = 0
                    for item, message in payload:
                        for iid, candidate in list(self.candidates.items()):
                            if candidate.path == item.path:
                                self.checked.discard(iid)
                                if message == "Enviado à Lixeira":
                                    self.tree.delete(iid)
                                    del self.candidates[iid]
                                    successes += 1
                                else:
                                    self.tree.set(iid, "mark", "☐")
                                    self.tree.set(iid, "state", message)
                    self.set_busy(False)
                    self.update_totals()
                    self.status.set(f"{successes} pasta(s) enviada(s) à Lixeira · {len(payload) - successes} não removidas. "
                                    "Restauração disponível na Lixeira do Windows.")
                    failures = [f"{item.path}\n{message}" for item, message in payload if message != "Enviado à Lixeira"]
                    if failures:
                        messagebox.showwarning("Pastas não removidas", "\n\n".join(failures[:8]))
                elif kind == "error":
                    self.set_busy(False)
                    self.status.set("Operação encerrada com erro. Nenhuma nova ação será iniciada.")
                    messagebox.showerror("DevSweep", payload)
        except queue.Empty:
            pass
        self.after(80, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("Operação em andamento", "Interrompa a busca ou aguarde a limpeza terminar antes de fechar.")
            return
        self.destroy()


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    App().mainloop()
