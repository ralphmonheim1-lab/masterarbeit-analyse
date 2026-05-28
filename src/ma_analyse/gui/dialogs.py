"""Dialoge fuer Naming- und Format-Einstellungen der Tk-GUI."""

from __future__ import annotations

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:
    tk = None
    ttk = None
    messagebox = None

from ..settings import naming as NAMENSMAPPING_MODULE
from ..settings.formats import (
    FORMAT_CATALOG,
    FORMAT_DOC,
    get_format_names,
    load_output_format_rules,
    write_output_format_rules,
)

OUTPUT_FORMAT_DOC = FORMAT_DOC


class SettingsDialogMixin:
    """Ergaenzt PipelineGUI um Einstellungsdialoge."""

    def _open_output_format_dialog(self):
        if self.format_dialog is not None and self.format_dialog.winfo_exists():
            self.format_dialog.focus_set()
            self.format_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Format")
        dialog.geometry("1180x760")
        dialog.minsize(980, 620)
        dialog.configure(bg=self.color_bg)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", self._close_output_format_dialog)
        self.format_dialog = dialog

        header = tk.Frame(dialog, bg=self.color_bg)
        header.pack(fill=tk.X, padx=18, pady=(18, 10))

        ttk.Label(header, text="Ausgabeformate", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text=f"Quelle: {self.format_doc_path}",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        body = tk.Frame(dialog, bg=self.color_bg)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))

        left = tk.Frame(body, bg=self.color_bg)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14))

        right = tk.Frame(body, bg=self.color_panel, highlightbackground=self.color_border, highlightthickness=1)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(left, text="Ausgabe-Regeln", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 8))

        canvas = tk.Canvas(left, bg=self.color_bg, highlightthickness=0, bd=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(left, orient=tk.VERTICAL, command=canvas.yview, style="Tool.Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scrollbar.set)

        table_frame = tk.Frame(canvas, bg=self.color_panel_light)
        self.format_table_frame = table_frame
        window_id = canvas.create_window((0, 0), window=table_frame, anchor="nw")

        def _sync_table_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        canvas.bind("<Configure>", _sync_table_width)
        table_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        self._build_output_format_table_header(table_frame)
        self._reload_output_format_rows(table_frame)

        self._build_format_catalog_column(right)

        button_bar = tk.Frame(dialog, bg=self.color_bg)
        button_bar.pack(fill=tk.X, padx=18, pady=(0, 18))

        ttk.Button(
            button_bar,
            text="Speichern",
            style="Primary.TButton",
            command=self._save_output_formats,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            button_bar,
            text="Abbrechen",
            style="Secondary.TButton",
            command=self._close_output_format_dialog,
        ).pack(side=tk.RIGHT, padx=(0, 12))

    def _build_output_format_table_header(self, table_frame):
        headers = ["Befehl", "Unterbefehl", "Ausgabe", "Format"]
        widths = [14, 16, 34, 18]
        for column, (label_text, width) in enumerate(zip(headers, widths, strict=True)):
            label = tk.Label(
                table_frame,
                text=label_text,
                bg=self.color_panel,
                fg=self.color_text,
                font=("Segoe UI", 10, "bold"),
                anchor=tk.W,
                padx=8,
                pady=8,
            )
            label.grid(row=0, column=column, sticky="ew", padx=1, pady=1)
            table_frame.grid_columnconfigure(column, weight=1, minsize=width * 10)

    def _reload_output_format_rows(self, table_frame):
        if table_frame is None:
            return
        for child in table_frame.grid_slaves():
            if int(child.grid_info()["row"]) > 0:
                child.destroy()

        self.format_row_vars = {}
        rules = load_output_format_rules(self.format_doc_path)
        format_names = get_format_names()
        for row_index, rule in enumerate(rules, start=1):
            row_bg = self.color_panel_light if row_index % 2 else self.color_panel
            for column, value in enumerate([rule["command"], rule["subcommand"], rule["output"]]):
                label = tk.Label(
                    table_frame,
                    text=value,
                    bg=row_bg,
                    fg=self.color_text,
                    anchor=tk.W,
                    padx=8,
                    pady=8,
                    wraplength=300 if column == 2 else 160,
                    justify=tk.LEFT,
                )
                label.grid(row=row_index, column=column, sticky="ew", padx=1, pady=1)

            var = tk.StringVar(value=rule["format"] if rule["format"] in FORMAT_CATALOG else format_names[0])
            combo = ttk.Combobox(
                table_frame,
                textvariable=var,
                values=format_names,
                state="readonly",
            )
            combo.grid(row=row_index, column=3, sticky="ew", padx=1, pady=1, ipady=4)
            self.format_row_vars[rule["id"]] = {"var": var, "rule": rule}

    def _build_format_catalog_column(self, parent):
        ttk.Label(parent, text="Formate", style="Heading.TLabel").pack(anchor=tk.W, padx=14, pady=(14, 8))
        ttk.Label(
            parent,
            text="Gängige Formate und Größen",
            style="Muted.TLabel",
            wraplength=260,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=14, pady=(0, 8))

        for format_name, values in FORMAT_CATALOG.items():
            item = tk.Frame(
                parent, bg=self.color_panel_light, highlightbackground=self.color_border, highlightthickness=1
            )
            item.pack(fill=tk.X, padx=14, pady=5)
            if values["width_cm"] is None:
                label_text = format_name
            else:
                label_text = f"{format_name} — {values['width_cm']:g} cm × {values['height_cm']:g} cm"
            ttk.Label(item, text=label_text, style="Dark.TLabel", wraplength=260, justify=tk.LEFT).pack(
                anchor=tk.W, padx=10, pady=10
            )

    def _save_output_formats(self):
        if self.format_dialog is None or not self.format_dialog.winfo_exists():
            return
        rules = []
        for row_data in self.format_row_vars.values():
            rule = row_data["rule"].copy()
            selected_format = row_data["var"].get()
            if selected_format in FORMAT_CATALOG:
                rule["format"] = selected_format
            rules.append(rule)
        write_output_format_rules(rules, self.format_doc_path)
        self._set_status("Ausgabeformate gespeichert.")
        self._append_log(f"Ausgabeformate gespeichert: {self.format_doc_path}")
        messagebox.showinfo("Format", "Die Ausgabeformate wurden gespeichert.", parent=self.format_dialog)

    def _close_output_format_dialog(self):
        if self.format_dialog is not None and self.format_dialog.winfo_exists():
            self.format_dialog.destroy()
        self.format_dialog = None
        self.format_table_frame = None
        self.format_row_vars = {}

    def _open_name_mapping_dialog(self):
        if self.mapping_dialog is not None and self.mapping_dialog.winfo_exists():
            self.mapping_dialog.focus_set()
            self.mapping_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Namensmapping")
        dialog.geometry("1100x760")
        dialog.minsize(920, 600)
        dialog.configure(bg=self.color_bg)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", self._close_name_mapping_dialog)
        self.mapping_dialog = dialog

        header = tk.Frame(dialog, bg=self.color_bg)
        header.pack(fill=tk.X, padx=18, pady=(18, 10))

        ttk.Label(header, text="Namensmapping", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text=f"Quelle: {self.mapping_doc_path}",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        body = tk.Frame(dialog, bg=self.color_bg)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))

        canvas = tk.Canvas(body, bg=self.color_bg, highlightthickness=0, bd=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview, style="Tool.Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scrollbar.set)

        table_frame = tk.Frame(canvas, bg=self.color_panel_light)
        self.mapping_table_frame = table_frame
        window_id = canvas.create_window((0, 0), window=table_frame, anchor="nw")

        def _sync_table_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        canvas.bind("<Configure>", _sync_table_width)
        table_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        headers = ["Kategorie", "Aktueller Name", "Neuer Name", "Verwendung"]
        widths = [18, 24, 24, 34]
        for column, (label_text, width) in enumerate(zip(headers, widths, strict=True)):
            label = tk.Label(
                table_frame,
                text=label_text,
                bg=self.color_panel,
                fg=self.color_text,
                font=("Segoe UI", 10, "bold"),
                anchor=tk.W,
                padx=8,
                pady=8,
            )
            label.grid(row=0, column=column, sticky="ew", padx=1, pady=1)
            table_frame.grid_columnconfigure(column, weight=1, minsize=width * 10)

        self.mapping_row_vars = {}
        self._reload_mapping_rows(table_frame)

        button_bar = tk.Frame(dialog, bg=self.color_bg)
        button_bar.pack(fill=tk.X, padx=18, pady=(0, 18))

        ttk.Button(button_bar, text="Speichern", style="Secondary.TButton", command=self._save_name_mapping).pack(
            side=tk.LEFT
        )
        ttk.Button(
            button_bar,
            text="Dry-Run pruefen",
            style="Secondary.TButton",
            command=self._dry_run_name_mapping,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(
            button_bar,
            text="Anwenden und bestaetigen",
            style="Primary.TButton",
            command=self._apply_name_mapping,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            button_bar,
            text="Abbrechen",
            style="Secondary.TButton",
            command=self._close_name_mapping_dialog,
        ).pack(side=tk.RIGHT, padx=(0, 12))

    def _reload_mapping_rows(self, table_frame):
        for child in table_frame.grid_slaves():
            if int(child.grid_info()["row"]) > 0:
                child.destroy()

        resolved_doc, entries = NAMENSMAPPING_MODULE.load_mapping_entries(self.mapping_doc_path)
        self.mapping_doc_path = resolved_doc
        self.mapping_row_vars = {}

        for row_index, entry in enumerate(entries, start=1):
            row_bg = self.color_panel_light if row_index % 2 else self.color_panel
            cells = [entry.category, entry.current_name, None, entry.usage]
            for column, cell_value in enumerate(cells):
                if column == 2:
                    var = tk.StringVar(value=entry.new_name)
                    self.mapping_row_vars[entry.entry_id] = {"var": var, "entry": entry}
                    entry_widget = tk.Entry(
                        table_frame,
                        textvariable=var,
                        bg=self.color_panel,
                        fg=self.color_text,
                        insertbackground=self.color_text,
                        relief=tk.FLAT,
                        highlightbackground=self.color_border,
                        highlightcolor=self.color_blue,
                        font=("Segoe UI", 10),
                    )
                    entry_widget.grid(row=row_index, column=column, sticky="ew", padx=1, pady=1, ipady=6)
                    continue

                label = tk.Label(
                    table_frame,
                    text=cell_value,
                    bg=row_bg,
                    fg=self.color_text,
                    font=("Segoe UI", 9),
                    anchor=tk.W,
                    justify=tk.LEFT,
                    wraplength=280 if column == 3 else 220,
                    padx=8,
                    pady=8,
                )
                label.grid(row=row_index, column=column, sticky="nsew", padx=1, pady=1)

    def _collect_mapping_entries_from_dialog(self):
        entries = []
        for mapping_data in self.mapping_row_vars.values():
            entry = mapping_data["entry"]
            entries.append(
                NAMENSMAPPING_MODULE.replace(
                    entry,
                    new_name=mapping_data["var"].get().strip(),
                )
            )
        entries.sort(key=lambda item: item.line_number)
        return entries

    def _save_name_mapping(self):
        if self.mapping_dialog is None or not self.mapping_dialog.winfo_exists():
            return
        entries = self._collect_mapping_entries_from_dialog()
        NAMENSMAPPING_MODULE.write_mapping_entries(self.mapping_doc_path, entries)
        self._set_status("Namensmapping gespeichert.")
        self._append_log(f"Namensmapping gespeichert: {self.mapping_doc_path}")
        messagebox.showinfo("Namensmapping", "Das Mapping wurde gespeichert.", parent=self.mapping_dialog)
        if self.mapping_table_frame is not None:
            self._reload_mapping_rows(self.mapping_table_frame)

    def _dry_run_name_mapping(self):
        entries = self._collect_mapping_entries_from_dialog()
        summary = NAMENSMAPPING_MODULE.run_mapping(
            mapping_doc=self.mapping_doc_path,
            dry_run=True,
            entries=entries,
        )
        summary_text = NAMENSMAPPING_MODULE.format_run_summary(summary)
        self._set_status("Namensmapping Dry-Run abgeschlossen.")
        self._append_log(summary_text)
        messagebox.showinfo("Namensmapping Dry-Run", summary_text, parent=self.mapping_dialog)

    def _apply_name_mapping(self):
        if not messagebox.askyesno(
            "Namensmapping anwenden",
            "Sollen die aktuellen Mapping-Aenderungen gespeichert und direkt angewendet werden?",
            parent=self.mapping_dialog,
        ):
            return

        entries = self._collect_mapping_entries_from_dialog()
        summary = NAMENSMAPPING_MODULE.run_mapping(
            mapping_doc=self.mapping_doc_path,
            dry_run=False,
            entries=entries,
        )
        summary_text = NAMENSMAPPING_MODULE.format_run_summary(summary)
        self._set_status("Namensmapping angewendet.")
        self._append_log(summary_text)
        messagebox.showinfo(
            "Namensmapping",
            summary_text + "\n\nGUI-bezogene Aenderungen werden nach 'GUI aktualisieren' sichtbar.",
            parent=self.mapping_dialog,
        )

    def _close_name_mapping_dialog(self):
        if self.mapping_dialog is not None and self.mapping_dialog.winfo_exists():
            self.mapping_dialog.destroy()
        self.mapping_dialog = None
        self.mapping_table_frame = None
