"""Tk-GUI fuer die ma_analyse-Pipeline."""

from __future__ import annotations

import contextlib
import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
import traceback

try:
    import tkinter as tk
    from tkinter import messagebox, ttk

    HAS_TKINTER = True
except ImportError:
    tk = None
    ttk = None
    messagebox = None
    HAS_TKINTER = False

from ..analysis.components.time_windows import MAX_CALENDAR_WEEK, MONTH_DAY_COUNTS, MONTH_NAMES
from ..analysis.templates import (
    DEFAULT_OUTDOOR_COLUMN,
    DEFAULT_SETPOINT_MAX,
    DEFAULT_SETPOINT_MIN,
    DEFAULT_TEMPERATURE_YMAX,
    DEFAULT_TEMPERATURE_YMIN,
    HEATING_YEAR_TEMPLATE,
    PLOT_TEMPLATE_CHOICES,
    get_plot_template_spec,
    is_time_filtered_template,
    list_heating_year_overlay_sources,
    template_requires_single_room,
    template_uses_overlay_options,
    validate_template_request,
)
from ..app.commands import build_runtime_args, execute_steps, get_comfort_output_settings, run_all
from ..core.config import DATENBANK_DIR, INPUT_DIR, OUTPUT_DIR, ROOMS
from ..core.logging import command_log, should_log_command
from ..settings.formats import ensure_output_format_doc
from ..settings.naming import LEGACY_MAPPING_DOC as NAMENSMAPPING_DOC
from ..settings.plot_templates import OPERATIVE_OVERLAY_ID, OUTDOOR_OVERLAY_ID, get_heating_year_template_defaults
from .dialogs import OUTPUT_FORMAT_DOC, SettingsDialogMixin
from .selection import (
    format_cli_list,
    list_datenbank_variants,
    list_input_variants,
    resolve_variant_list_state,
    strip_variant_suffix,
)
from .singleton import (
    GUI_REFRESH_TIMEOUT_SECONDS,
    GUI_REPLACE_TIMEOUT_SECONDS,
    GuiInstanceController,
    GuiRefreshCoordinator,
    send_refresh_message,
)
from .worker import QueueLogWriter

DISABLED_GUI_COMMANDS = set()
WINDOWS_APP_USER_MODEL_ID = "ma_analyse.gui"


def _set_windows_app_user_model_id():
    """Setzt unter Windows eine stabile App-ID fuer Taskleisten-Gruppierung."""
    if os.name != "nt":
        return
    with contextlib.suppress(Exception):
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_USER_MODEL_ID)


def run_gui(args):
    """Startet die normale GUI und ersetzt eine bereits laufende Instanz."""
    if not HAS_TKINTER:
        print("X Tkinter ist nicht verfuegbar. Bitte fuehren Sie das Skript in einer GUI-faehigen Umgebung aus.")
        raise SystemExit(1)

    if getattr(args, "gui_refresh_port", None):
        run_gui_refresh(args)
        return

    controller = GuiInstanceController()
    if not controller.acquire():
        response = None
        with contextlib.suppress(Exception):
            response = GuiInstanceController.send_message("REPLACE_WITH_NEW")
        if response not in {"RELEASING", "CLOSING"}:
            print("X Die vorhandene GUI konnte nicht fuer den neuen Aufruf freigegeben werden.")
            return

        deadline = time.time() + GUI_REPLACE_TIMEOUT_SECONDS
        while time.time() < deadline:
            if controller.acquire():
                break
            time.sleep(0.1)
        else:
            print("X Neue GUI konnte die vorhandene Instanz nicht abloesen.")
            return

    _set_windows_app_user_model_id()
    root = tk.Tk()
    PipelineGUI(root, args, singleton_controller=controller)
    root.mainloop()


def run_gui_refresh(args):
    """Startet eine neue GUI-Instanz im kontrollierten Refresh-Ablauf."""
    refresh_port = getattr(args, "gui_refresh_port", None)
    if not refresh_port:
        raise SystemExit(1)

    response = send_refresh_message(refresh_port, "REQUEST_RELEASE", timeout=5)
    if response != "RELEASED":
        print("X GUI-Aktualisierung konnte die alte Instanz nicht freigeben.")
        raise SystemExit(1)

    controller = GuiInstanceController()
    deadline = time.time() + 10
    while time.time() < deadline:
        if controller.acquire():
            break
        time.sleep(0.1)
    else:
        print("X Neue GUI konnte die Singleton-Rolle nicht uebernehmen.")
        raise SystemExit(1)

    _set_windows_app_user_model_id()
    root = tk.Tk()
    gui = PipelineGUI(
        root,
        args,
        singleton_controller=controller,
        refresh_port=refresh_port,
    )
    root.update_idletasks()
    gui._focus_window()
    with contextlib.suppress(Exception):
        send_refresh_message(refresh_port, "NEW_GUI_ACTIVE", timeout=5)
    root.mainloop()


def build_gui_restart_argv(args, refresh_port):
    """Baut den CLI-Aufruf, mit dem sich die GUI selbst neu startet."""
    argv = [sys.executable, "-m", "ma_analyse", "gui"]
    template_defaults = get_heating_year_template_defaults()

    option_values = [
        ("--input-dir", getattr(args, "input_dir", None), INPUT_DIR),
        ("--datenbank-dir", getattr(args, "datenbank_dir", None), DATENBANK_DIR),
        ("--output-root", getattr(args, "output_root", None), OUTPUT_DIR),
        ("--run-id", getattr(args, "run_id", None), None),
        ("--variants", format_cli_list(getattr(args, "variants", None)), None),
        ("--rooms", format_cli_list(getattr(args, "rooms", None)), None),
        ("--view", getattr(args, "view", None), "bar"),
        ("--month", getattr(args, "month", None), None),
        ("--week", getattr(args, "week", None), None),
        ("--day", getattr(args, "day", None), None),
        ("--heating-mode", getattr(args, "heating_mode", None), "compare"),
        ("--heating-series-layout", getattr(args, "heating_series_layout", None), "separate"),
        ("--export-format", getattr(args, "export_format", None), "csv"),
        ("--template", getattr(args, "template", None), HEATING_YEAR_TEMPLATE),
        (
            "--setpoint-min",
            getattr(args, "setpoint_min", None),
            template_defaults.get("setpoint_min", DEFAULT_SETPOINT_MIN),
        ),
        (
            "--setpoint-max",
            getattr(args, "setpoint_max", None),
            template_defaults.get("setpoint_max", DEFAULT_SETPOINT_MAX),
        ),
        (
            "--temperature-ymin",
            getattr(args, "temperature_ymin", None),
            template_defaults.get("temperature_ymin", DEFAULT_TEMPERATURE_YMIN),
        ),
        (
            "--temperature-ymax",
            getattr(args, "temperature_ymax", None),
            template_defaults.get("temperature_ymax", DEFAULT_TEMPERATURE_YMAX),
        ),
        (
            "--outdoor-column",
            getattr(args, "outdoor_column", None),
            template_defaults.get("outdoor_column", DEFAULT_OUTDOOR_COLUMN),
        ),
    ]

    for option_name, value, default_value in option_values:
        if value is None:
            continue
        if default_value is not None and value == default_value:
            continue
        argv.extend([option_name, str(value)])

    if getattr(args, "debug", True):
        argv.append("--debug")
    else:
        argv.append("--no-debug")

    if getattr(args, "show_setpoint_band", template_defaults.get("show_setpoint_band", True)) is False:
        argv.append("--no-setpoint-band")
    if getattr(args, "show_outdoor_temperature", template_defaults.get("show_outdoor_temperature", True)) is False:
        argv.append("--no-outdoor-temperature")
    if getattr(args, "show_operative_temperature", template_defaults.get("show_operative_temperature", True)) is False:
        argv.append("--no-operative-temperature")

    window_geometry = getattr(args, "gui_window_geometry", None)
    if isinstance(window_geometry, dict):
        for option_name, key in (
            ("--gui-window-x", "x"),
            ("--gui-window-y", "y"),
            ("--gui-window-width", "width"),
            ("--gui-window-height", "height"),
        ):
            value = window_geometry.get(key)
            if value is not None:
                argv.extend([option_name, str(value)])

    argv.extend(
        [
            "--gui-window-maximized",
            "1" if getattr(args, "gui_window_maximized", False) else "0",
        ]
    )
    argv.extend(["--gui-refresh-port", str(refresh_port)])
    return argv


class PipelineGUI(SettingsDialogMixin):
    """Grafische Oberflaeche fuer Pipeline-Auswahl und Ausfuehrung.

    Die Klasse verwaltet GUI-Zustand, Validierung und Protokollausgabe. Die
    eigentliche Arbeit wird an die Runner-Funktionen delegiert und in einem
    Hintergrundthread gestartet, damit das Fenster waehrend der Analyse
    bedienbar bleibt.
    """

    def __init__(self, root, args, singleton_controller=None, refresh_port=None):
        self.root = root
        self.args = args
        self.singleton_controller = singleton_controller
        self.refresh_port = refresh_port
        self.refresh_coordinator = None
        self.refresh_recovery_after_id = None
        self.is_refresh_shutdown = False
        self.custom_window_chrome_enabled = False

        self.root.title("ANALYSE TOOLS")
        self.root.minsize(1050, 650)

        self.color_bg = "#0f141a"
        self.color_panel = "#161b22"
        self.color_panel_light = "#1f2630"
        self.color_border = "#30363d"
        self.color_text = "#f0f3f6"
        self.color_muted = "#a9b1ba"
        self.color_blue = "#0078d4"
        self.color_blue_dark = "#005a9e"
        self.window_icon = None

        self._set_window_icon()

        self.command_to_steps = {
            "prepare": ["prepare"],
            "comfort": [],
            "analyze_data": ["analyze"],
            "heating": ["heating"],
            "cooling": ["cooling"],
            "plot-template": ["plot_template"],
            "all": ["overview", "analysis", "heating", "cooling"],
        }
        self.commands = list(self.command_to_steps.keys())
        self.plot_template_defaults = get_heating_year_template_defaults()
        self.fixed_plot_overlays = self.plot_template_defaults.get("default_overlays", [])

        self.analysis_scope = tk.StringVar(value="")
        self.command = tk.StringVar(value="")
        self.prepare_export_format = tk.StringVar(value="")
        self.comfort_type = tk.StringVar(value="")
        self.analysis_level = tk.StringVar(value="")
        self.load_subcommand = tk.StringVar(value="")
        self.heating_mode = tk.StringVar(value="")
        self.heating_view = tk.StringVar(value="")
        self.heating_series_layout = tk.StringVar(value="")
        self.heating_month = tk.StringVar(value=MONTH_NAMES[0])
        self.heating_week = tk.StringVar(value="1")
        self.heating_day = tk.StringVar(value="1")
        self.plot_template = tk.StringVar(value=getattr(args, "template", HEATING_YEAR_TEMPLATE))
        self.plot_setpoint_min = tk.StringVar(
            value=str(
                getattr(args, "setpoint_min", self.plot_template_defaults.get("setpoint_min", DEFAULT_SETPOINT_MIN))
            )
        )
        self.plot_setpoint_max = tk.StringVar(
            value=str(
                getattr(args, "setpoint_max", self.plot_template_defaults.get("setpoint_max", DEFAULT_SETPOINT_MAX))
            )
        )
        self.plot_temperature_ymin = tk.StringVar(
            value=str(
                getattr(
                    args,
                    "temperature_ymin",
                    self.plot_template_defaults.get("temperature_ymin", DEFAULT_TEMPERATURE_YMIN),
                )
            )
        )
        self.plot_temperature_ymax = tk.StringVar(
            value=str(
                getattr(
                    args,
                    "temperature_ymax",
                    self.plot_template_defaults.get("temperature_ymax", DEFAULT_TEMPERATURE_YMAX),
                )
            )
        )
        self.plot_outdoor_column = tk.StringVar(
            value=getattr(
                args, "outdoor_column", self.plot_template_defaults.get("outdoor_column", DEFAULT_OUTDOOR_COLUMN)
            )
        )
        self.plot_show_setpoint_band = tk.BooleanVar(value=False)
        self.plot_show_outdoor_temperature = tk.BooleanVar(value=False)
        self.plot_show_operative_temperature = tk.BooleanVar(value=False)
        self.overlay_source = tk.StringVar(value="")
        self.overlay_column = tk.StringVar(value="")
        self.overlay_label = tk.StringVar(value="")
        self.overlay_axis = tk.StringVar(value="")

        self.selected_steps = []
        self.selected_variants = []
        self.selected_rooms = []
        self.selected_load_subcommand = ""
        self.selected_heating_mode = ""
        self.selected_heating_view = ""
        self.selected_heating_series_layout = ""
        self.selected_prepare_export_format = ""
        self.selected_month = MONTH_NAMES[0]
        self.selected_week = 1
        self.selected_day = 1
        self.selected_comfort_type = ""
        self.selected_plot_template_options = {}
        self.selected_plot_single = True
        self.selected_plot_overview = True
        self.selected_analysis_individual = True
        self.selected_analysis_overview = True
        self.free_overlay_lines = []
        self.overlay_catalog = {"csv": [], "aux": []}

        self.comfort_allowed_by_level = {
            "Analyse Raum": {"plot", "plot_analysis"},
            "Analyse Variante": {"plot_overview", "plot_analysis_overview"},
        }
        self.comfort_default_by_level = {
            "Analyse Raum": "plot",
            "Analyse Variante": "plot_overview",
        }
        self.last_variant_scope = None

        self.variant_names = []
        self.variant_source_kind = None
        self.active_step_card = None
        self.left_scroll_window = None
        self.right_scroll_window = None
        self.right_scrollbar_visible = False
        self.tools_menu = None
        self.mapping_dialog = None
        self.mapping_row_vars = {}
        self.mapping_table_frame = None
        self.mapping_doc_path = NAMENSMAPPING_DOC
        self.format_dialog = None
        self.format_row_vars = {}
        self.format_table_frame = None
        self.format_doc_path = ensure_output_format_doc(OUTPUT_FORMAT_DOC)
        self.log_card = None
        self.log_expand_button = None
        self.log_focus_frame = None
        self.expanded_log_text = None
        self.is_log_expanded = False
        self.bottom_button_frame = None
        self.run_log_text = None
        self.analysis_log_window = None
        self.analysis_log_text = None
        self.analysis_status_var = None
        self.pipeline_queue = None
        self.pipeline_thread = None
        self.pipeline_log_poll_after_id = None
        self.status_var = tk.StringVar(value="Bereit.")
        self.is_running_pipeline = False
        self.maximize_button = None
        self.title_frame = None
        self.title_label = None
        self.is_window_maximized = False
        self.is_minimizing_window = False
        self.normal_window_geometry = None
        self.drag_start_pointer_x = 0
        self.drag_start_pointer_y = 0
        self.drag_start_window_x = 0
        self.drag_start_window_y = 0

        self._setup_style()
        self._build_ui()
        self._populate_variants()
        self._populate_rooms()
        if self.singleton_controller is not None:
            self.singleton_controller.start_listener(self._handle_singleton_message)
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self.root.bind("<Configure>", self._on_window_configure, add="+")
        self.root.bind("<Map>", self._on_window_map, add="+")
        self._apply_initial_window_state()
        self.root.update_idletasks()
        self.normal_window_geometry = self._get_current_window_geometry()
        self._enable_custom_window_chrome()
        self._update_window_state_buttons()
        self._update_dynamic_fields()

    def _setup_style(self):
        self.root.configure(bg=self.color_bg)

        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Title.TLabel",
            background=self.color_bg,
            foreground=self.color_text,
            font=("Segoe UI", 18, "bold"),
        )
        style.configure(
            "Heading.TLabel",
            background=self.color_panel,
            foreground=self.color_text,
            font=("Segoe UI", 13, "bold"),
        )
        style.configure(
            "Dark.TLabel",
            background=self.color_panel,
            foreground=self.color_text,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=self.color_panel,
            foreground=self.color_muted,
            font=("Segoe UI", 9),
        )
        style.configure(
            "TCombobox",
            fieldbackground=self.color_panel_light,
            background=self.color_panel_light,
            foreground=self.color_text,
            arrowcolor=self.color_text,
            bordercolor=self.color_border,
            lightcolor=self.color_border,
            darkcolor=self.color_border,
            font=("Segoe UI", 10),
        )

        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.color_panel_light)],
            foreground=[("readonly", self.color_text)],
        )
        style.configure(
            "TRadiobutton",
            background=self.color_panel,
            foreground=self.color_text,
            font=("Segoe UI", 10),
        )
        style.map(
            "TRadiobutton",
            background=[("active", self.color_panel)],
            foreground=[
                ("disabled", self.color_muted),
                ("active", self.color_text),
            ],
        )
        style.configure(
            "TCheckbutton",
            background=self.color_panel,
            foreground=self.color_text,
            font=("Segoe UI", 10),
        )
        style.map(
            "TCheckbutton",
            background=[("active", self.color_panel)],
            foreground=[("active", self.color_text)],
        )
        style.configure(
            "Primary.TButton",
            background=self.color_blue,
            foreground="white",
            font=("Segoe UI", 11, "bold"),
            padding=(18, 10),
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", self.color_blue_dark)],
        )
        style.configure(
            "Secondary.TButton",
            background=self.color_panel_light,
            foreground=self.color_text,
            font=("Segoe UI", 11),
            padding=(18, 10),
            borderwidth=1,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", self.color_border)],
        )
        style.layout(
            "Tool.Vertical.TScrollbar",
            [
                (
                    "Vertical.Scrollbar.trough",
                    {
                        "sticky": "ns",
                        "children": [
                            (
                                "Vertical.Scrollbar.thumb",
                                {"expand": "1", "sticky": "nswe"},
                            )
                        ],
                    },
                )
            ],
        )
        style.configure(
            "Tool.Vertical.TScrollbar",
            background="#2a313b",
            troughcolor=self.color_bg,
            bordercolor=self.color_bg,
            darkcolor="#2a313b",
            lightcolor="#2a313b",
            arrowcolor=self.color_bg,
            gripcount=0,
            relief="flat",
            borderwidth=0,
            width=8,
        )
        style.map(
            "Tool.Vertical.TScrollbar",
            background=[
                ("active", "#343c47"),
                ("pressed", "#3b4552"),
            ],
            troughcolor=[("active", self.color_bg)],
        )

    def _set_window_icon(self):
        icon_image = self._create_window_icon()
        if icon_image is None:
            return
        self.window_icon = icon_image
        with contextlib.suppress(tk.TclError):
            self.root.iconphoto(True, self.window_icon)

    def _create_window_icon(self):
        if tk is None:
            return None

        size = 32
        image = tk.PhotoImage(width=size, height=size)
        image.put(self.color_bg, to=(0, 0, size, size))

        border_color = self.color_border
        axis_color = self.color_text
        bar_colors = [self.color_blue, "#2a9d8f", "#f77f00", "#d62828"]

        image.put(border_color, to=(3, 3, 29, 5))
        image.put(border_color, to=(3, 27, 29, 29))
        image.put(border_color, to=(3, 3, 5, 29))
        image.put(border_color, to=(27, 3, 29, 29))
        image.put(axis_color, to=(8, 23, 25, 25))
        image.put(axis_color, to=(8, 9, 10, 25))

        bars = [
            (12, 17, 15, 23, bar_colors[0]),
            (16, 13, 19, 23, bar_colors[1]),
            (20, 10, 23, 23, bar_colors[2]),
            (24, 15, 26, 23, bar_colors[3]),
        ]
        for x0, y0, x1, y1, color in bars:
            image.put(color, to=(x0, y0, x1, y1))

        return image

    def _update_left_scroll_region(self, _event=None):
        self.left_scroll_canvas.configure(scrollregion=self.left_scroll_canvas.bbox("all"))

    def _sync_left_scroll_width(self, event):
        self.left_scroll_canvas.itemconfigure(self.left_scroll_window, width=event.width)

    def _update_right_scroll_region(self, _event=None):
        self.right_scroll_canvas.configure(scrollregion=self.right_scroll_canvas.bbox("all"))
        self._update_right_scrollbar_visibility()

    def _sync_right_scroll_width(self, event):
        self.right_scroll_canvas.itemconfigure(self.right_scroll_window, width=event.width)
        self._update_right_scrollbar_visibility()

    def _update_right_scrollbar_visibility(self):
        if not hasattr(self, "right_scrollbar") or self.right_scrollbar is None:
            return
        if getattr(self, "_is_updating_right_scrollbar", False):
            return
        self._is_updating_right_scrollbar = True
        try:
            self.root.update_idletasks()
            content_height = self.right_content.winfo_reqheight()
            viewport_height = self.right_scroll_canvas.winfo_height()
            needs_scrollbar = content_height > viewport_height + 1
            if needs_scrollbar == self.right_scrollbar_visible:
                return
            self.right_scrollbar_visible = needs_scrollbar
            if needs_scrollbar:
                self.right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                return
            self.right_scrollbar.pack_forget()
            self.right_scroll_canvas.yview_moveto(0)
        finally:
            self._is_updating_right_scrollbar = False

    def _should_skip_mousewheel(self, widget):
        widget_class = widget.winfo_class()
        return widget_class in {"Listbox", "Text", "Entry", "TCombobox", "Combobox"}

    def _widget_is_in_left_scroll_area(self, widget):
        current = widget
        while current is not None:
            if current == self.left_scroll_host:
                return True
            parent_name = current.winfo_parent()
            if not parent_name:
                break
            current = current.nametowidget(parent_name)
        return False

    def _widget_is_in_right_scroll_area(self, widget):
        current = widget
        while current is not None:
            if current == self.right_column:
                return True
            parent_name = current.winfo_parent()
            if not parent_name:
                break
            current = current.nametowidget(parent_name)
        return False

    def _on_mousewheel(self, event):
        if self._should_skip_mousewheel(event.widget):
            return
        delta = int(-event.delta / 120)
        if delta == 0:
            return
        if self._widget_is_in_right_scroll_area(event.widget):
            if self.right_scrollbar_visible:
                self.right_scroll_canvas.yview_scroll(delta, "units")
            return
        if self._widget_is_in_left_scroll_area(event.widget):
            self.left_scroll_canvas.yview_scroll(delta, "units")

    def _on_mousewheel_linux_up(self, event):
        if self._should_skip_mousewheel(event.widget):
            return
        if self._widget_is_in_right_scroll_area(event.widget):
            if self.right_scrollbar_visible:
                self.right_scroll_canvas.yview_scroll(-1, "units")
            return
        if self._widget_is_in_left_scroll_area(event.widget):
            self.left_scroll_canvas.yview_scroll(-1, "units")

    def _on_mousewheel_linux_down(self, event):
        if self._should_skip_mousewheel(event.widget):
            return
        if self._widget_is_in_right_scroll_area(event.widget):
            if self.right_scrollbar_visible:
                self.right_scroll_canvas.yview_scroll(1, "units")
            return
        if self._widget_is_in_left_scroll_area(event.widget):
            self.left_scroll_canvas.yview_scroll(1, "units")

    def _build_ui(self):
        self._build_title()
        self._build_main_layout()
        self._build_left_column()
        self._build_right_column()
        self._build_bottom_buttons()

    def _build_title(self):
        self.title_frame = tk.Frame(self.root, bg=self.color_bg)
        self.title_frame.pack(fill=tk.X, padx=22, pady=(18, 8))

        title_left_frame = tk.Frame(self.title_frame, bg=self.color_bg)
        title_left_frame.pack(side=tk.LEFT)

        title_icon_label = tk.Label(
            title_left_frame,
            text="📊",
            bg=self.color_bg,
            fg=self.color_text,
            font=("Segoe UI Emoji", 18),
        )
        title_icon_label.pack(side=tk.LEFT, padx=(0, 10))

        self.title_label = ttk.Label(title_left_frame, text="ANALYSE TOOLS", style="Title.TLabel")
        self.title_label.pack(side=tk.LEFT)

        actions_frame = tk.Frame(self.title_frame, bg=self.color_bg)
        actions_frame.pack(side=tk.RIGHT)

        minimize_label = tk.Label(
            actions_frame,
            text="-",
            bg=self.color_bg,
            fg=self.color_text,
            font=("Segoe UI", 18, "bold"),
            cursor="hand2",
        )
        minimize_label.pack(side=tk.LEFT, padx=(0, 16))
        minimize_label.bind("<Button-1>", lambda event: self._minimize_window())

        self.maximize_button = tk.Label(
            actions_frame,
            text="□",
            bg=self.color_bg,
            fg=self.color_text,
            font=("Segoe UI", 16, "bold"),
            cursor="hand2",
        )
        self.maximize_button.pack(side=tk.LEFT, padx=(0, 16))
        self.maximize_button.bind("<Button-1>", lambda event: self._toggle_maximize_window())

        close_label = tk.Label(
            actions_frame,
            text="X",
            bg=self.color_bg,
            fg=self.color_text,
            font=("Segoe UI", 18, "bold"),
            cursor="hand2",
        )
        close_label.pack(side=tk.LEFT)
        close_label.bind("<Button-1>", lambda event: self._close_window())

        for widget in (self.title_frame, title_left_frame, title_icon_label, self.title_label):
            widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
            widget.bind("<B1-Motion>", self._drag_window, add="+")
            widget.bind("<Double-Button-1>", lambda event: self._toggle_maximize_window(), add="+")

    def _open_tools_menu(self, event=None):
        if self.tools_menu is None:
            self.tools_menu = tk.Menu(
                self.root,
                tearoff=0,
                bg=self.color_panel_light,
                fg=self.color_text,
                activebackground=self.color_blue,
                activeforeground="white",
                relief=tk.FLAT,
            )
            self.tools_menu.add_command(label="Format", command=self._open_output_format_dialog)
            self.tools_menu.add_command(label="Namensmapping", command=self._open_name_mapping_dialog)
            self.tools_menu.add_command(label="GUI aktualisieren", command=self._restart_gui)

        source_widget = event.widget if event is not None else getattr(self, "settings_bottom_button", self.root)
        x_pos = source_widget.winfo_rootx()
        y_pos = source_widget.winfo_rooty() + source_widget.winfo_height()
        self._safe_popup_menu(self.tools_menu, x_pos, y_pos)

    def _handle_singleton_message(self, payload):
        if payload == "FOCUS":
            self.root.after(0, self._focus_window)
            return "FOCUSED"
        if payload == "REPLACE_WITH_NEW":
            if self.singleton_controller is not None:
                self.singleton_controller.stop()
            self.root.after(0, self._close_for_new_gui_invocation)
            return "RELEASING"
        return "IGNORED"

    def _on_window_configure(self, _event=None):
        if self.root.winfo_exists() and not self.is_window_maximized:
            with contextlib.suppress(tk.TclError):
                if self.root.state() != "iconic":
                    self.normal_window_geometry = self._get_current_window_geometry()
        self._update_window_state_buttons()

    def _on_window_map(self, _event=None):
        if self.root.winfo_exists():
            with contextlib.suppress(tk.TclError):
                if self.root.state() == "iconic":
                    return
            delay_ms = 80 if self.is_minimizing_window else 30
            self.root.after(delay_ms, self._restore_custom_window_chrome_after_show)

    def _update_window_state_buttons(self):
        if self.maximize_button is None or not self.root.winfo_exists():
            return
        self.maximize_button.configure(text="❐" if self.is_window_maximized else "□")

    def _apply_initial_window_state(self):
        restored_geometry = self._extract_refresh_window_geometry()
        if restored_geometry is not None:
            self._apply_window_geometry(restored_geometry)
            self.normal_window_geometry = restored_geometry.copy()
            self.is_window_maximized = bool(getattr(self.args, "gui_window_maximized", False))
            if self.is_window_maximized:
                self._apply_window_geometry(self._get_current_monitor_work_area_geometry())
            return

        self.root.geometry("1250x720")
        self.is_window_maximized = False

    def _extract_refresh_window_geometry(self):
        geometry_keys = ("gui_window_x", "gui_window_y", "gui_window_width", "gui_window_height")
        values = {key: getattr(self.args, key, None) for key in geometry_keys}
        if any(value is None for value in values.values()):
            return None

        return {
            "x": int(values["gui_window_x"]),
            "y": int(values["gui_window_y"]),
            "width": int(values["gui_window_width"]),
            "height": int(values["gui_window_height"]),
        }

    def _get_current_window_geometry(self):
        self.root.update_idletasks()
        return {
            "x": self.root.winfo_x(),
            "y": self.root.winfo_y(),
            "width": self.root.winfo_width(),
            "height": self.root.winfo_height(),
        }

    def _apply_window_geometry(self, geometry):
        self.root.geometry(f"{geometry['width']}x{geometry['height']}+{geometry['x']}+{geometry['y']}")

    def _get_current_monitor_work_area_geometry(self):
        if os.name == "nt" and self.root.winfo_exists():

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", ctypes.c_ulong),
                ]

            monitor_default_to_nearest = 2
            monitor_handle = ctypes.windll.user32.MonitorFromWindow(
                ctypes.c_void_p(self.root.winfo_id()),
                monitor_default_to_nearest,
            )
            if monitor_handle:
                monitor_info = MONITORINFO()
                monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
                if ctypes.windll.user32.GetMonitorInfoW(
                    ctypes.c_void_p(monitor_handle),
                    ctypes.byref(monitor_info),
                ):
                    work_area = monitor_info.rcWork
                    return {
                        "x": work_area.left,
                        "y": work_area.top,
                        "width": work_area.right - work_area.left,
                        "height": work_area.bottom - work_area.top,
                    }

        return self._get_work_area_geometry()

    def _get_work_area_geometry(self):
        if os.name == "nt":

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                return {
                    "x": rect.left,
                    "y": rect.top,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                }

        return {
            "x": 0,
            "y": 0,
            "width": self.root.winfo_screenwidth(),
            "height": self.root.winfo_screenheight(),
        }

    def _enable_custom_window_chrome(self):
        if not self.root.winfo_exists() or self.custom_window_chrome_enabled:
            return
        with contextlib.suppress(tk.TclError):
            self.root.overrideredirect(True)
            self.custom_window_chrome_enabled = True
        self._ensure_windows_taskbar_button()
        with contextlib.suppress(tk.TclError):
            self.root.after(60, self._ensure_windows_taskbar_button)

    def _ensure_windows_taskbar_button(self):
        """Haelt das rahmenlose Tk-Fenster in der Windows-Taskleiste sichtbar."""
        if os.name != "nt" or not self.root.winfo_exists():
            return

        with contextlib.suppress(Exception):
            user32 = ctypes.windll.user32
            window_handle = self.root.winfo_id()
            taskbar_handle = user32.GetParent(window_handle) or window_handle

            gwl_exstyle = -20
            ws_ex_appwindow = 0x00040000
            ws_ex_toolwindow = 0x00000080
            swp_nosize = 0x0001
            swp_nomove = 0x0002
            swp_nozorder = 0x0004
            swp_framechanged = 0x0020

            get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_window_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)

            style = get_window_long(taskbar_handle, gwl_exstyle)
            style = (style | ws_ex_appwindow) & ~ws_ex_toolwindow
            set_window_long(taskbar_handle, gwl_exstyle, style)
            user32.SetWindowPos(
                taskbar_handle,
                0,
                0,
                0,
                0,
                0,
                swp_nomove | swp_nosize | swp_nozorder | swp_framechanged,
            )

    def _disable_custom_window_chrome(self):
        if not self.root.winfo_exists() or not self.custom_window_chrome_enabled:
            return
        with contextlib.suppress(tk.TclError):
            self.root.overrideredirect(False)
            self.custom_window_chrome_enabled = False

    def _restore_custom_window_chrome_after_show(self):
        if not self.root.winfo_exists():
            return
        with contextlib.suppress(tk.TclError):
            if self.root.state() == "iconic":
                return
        self.is_minimizing_window = False
        self._enable_custom_window_chrome()
        if self.is_window_maximized:
            self._apply_window_geometry(self._get_current_monitor_work_area_geometry())
        self._update_window_state_buttons()

    def _start_window_drag(self, event):
        if self.is_window_maximized:
            return
        self.drag_start_pointer_x = event.x_root
        self.drag_start_pointer_y = event.y_root
        self.drag_start_window_x = self.root.winfo_x()
        self.drag_start_window_y = self.root.winfo_y()

    def _drag_window(self, event):
        if self.is_window_maximized:
            return
        offset_x = event.x_root - self.drag_start_pointer_x
        offset_y = event.y_root - self.drag_start_pointer_y
        self.root.geometry(f"+{self.drag_start_window_x + offset_x}+{self.drag_start_window_y + offset_y}")

    def _focus_window(self):
        if not self.root.winfo_exists():
            return
        self._disable_custom_window_chrome()
        self.root.deiconify()
        self.root.lift()
        with contextlib.suppress(tk.TclError):
            self.root.attributes("-topmost", True)
            self.root.after(120, lambda: self.root.attributes("-topmost", False))
        with contextlib.suppress(tk.TclError):
            self.root.focus_force()
        self.root.after(30, self._restore_custom_window_chrome_after_show)

    def _minimize_window(self):
        if not self.root.winfo_exists():
            return

        self.is_minimizing_window = True
        self._disable_custom_window_chrome()
        self.root.update_idletasks()

        def finish_minimize():
            if not self.root.winfo_exists():
                return
            with contextlib.suppress(tk.TclError):
                self.root.iconify()
            self._update_window_state_buttons()
            self.root.after(250, self._finish_minimize_window)

        self.root.after_idle(finish_minimize)

    def _finish_minimize_window(self):
        if not self.root.winfo_exists():
            return
        with contextlib.suppress(tk.TclError):
            if self.root.state() == "iconic":
                return
        self.is_minimizing_window = False
        self._restore_custom_window_chrome_after_show()

    def _toggle_maximize_window(self):
        if not self.root.winfo_exists():
            return
        if self.is_window_maximized:
            self.is_window_maximized = False
            if self.normal_window_geometry is not None:
                self._apply_window_geometry(self.normal_window_geometry)
        else:
            self.normal_window_geometry = self._get_current_window_geometry()
            self.is_window_maximized = True
            self._apply_window_geometry(self._get_current_monitor_work_area_geometry())
        self._update_window_state_buttons()

    def _close_window(self):
        if self.mapping_dialog is not None and self.mapping_dialog.winfo_exists():
            self.mapping_dialog.destroy()
            self.mapping_dialog = None
        if self.refresh_recovery_after_id is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self.refresh_recovery_after_id)
            self.refresh_recovery_after_id = None
        if self.refresh_coordinator is not None:
            self.refresh_coordinator.close()
            self.refresh_coordinator = None
        if self.singleton_controller is not None:
            self.singleton_controller.stop()
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")
        if self.root.winfo_exists():
            self.root.quit()
            self.root.destroy()

    def _close_for_new_gui_invocation(self):
        if not self.root.winfo_exists():
            return
        self._set_status("Neuer GUI-Aufruf uebernimmt. Diese Instanz wird geschlossen.")
        if self.run_log_text is not None:
            self._append_log("Neuer GUI-Aufruf priorisiert. Alte Instanz wird geschlossen.")
        self.root.after(80, self._close_window)

    def _restart_gui(self):
        if self.is_running_pipeline:
            messagebox.showwarning(
                "GUI aktualisieren",
                "Bitte warten Sie, bis der laufende Befehl abgeschlossen ist.",
                parent=self.root,
            )
            return

        if self.refresh_coordinator is not None:
            return

        self.refresh_coordinator = GuiRefreshCoordinator(self)
        refresh_port = self.refresh_coordinator.start()
        window_geometry = (
            self.normal_window_geometry.copy()
            if self.is_window_maximized and self.normal_window_geometry is not None
            else self._get_current_window_geometry()
        )
        self.args.gui_window_geometry = window_geometry
        self.args.gui_window_maximized = self.is_window_maximized
        argv = build_gui_restart_argv(self.args, refresh_port)
        try:
            subprocess.Popen(argv, cwd=os.getcwd())
        except Exception as exc:
            self.refresh_coordinator.close()
            self.refresh_coordinator = None
            messagebox.showerror(
                "GUI aktualisieren",
                f"Die neue GUI konnte nicht gestartet werden:\n{exc}",
                parent=self.root,
            )
            return

        self._set_status("GUI-Aktualisierung gestartet. Neue Instanz wird vorbereitet.")
        self._append_log("GUI-Aktualisierung gestartet. Warte auf Uebergabe an neue Instanz.")

    def _release_singleton_for_refresh(self):
        if self.refresh_coordinator is None or self.singleton_controller is None:
            return
        self.singleton_controller.stop()
        self.refresh_coordinator.mark_released()
        self._set_status("GUI-Refresh: Singleton freigegeben, warte auf neue Instanz.")

    def _schedule_refresh_timeout_recovery(self):
        if self.refresh_recovery_after_id is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self.refresh_recovery_after_id)
        self.refresh_recovery_after_id = self.root.after(
            GUI_REFRESH_TIMEOUT_SECONDS * 1000,
            self._recover_from_refresh_timeout,
        )

    def _recover_from_refresh_timeout(self):
        if self.is_refresh_shutdown or self.refresh_coordinator is None or self.refresh_coordinator.completed:
            return
        self._append_log(
            "GUI-Aktualisierung wurde nicht abgeschlossen. Die bestehende GUI uebernimmt wieder die Kontrolle."
        )
        self._set_status("GUI-Aktualisierung fehlgeschlagen. Bestehende GUI bleibt aktiv.")
        if self.singleton_controller is not None and self.singleton_controller.acquire():
            self.singleton_controller.start_listener(self._handle_singleton_message)
        if self.refresh_coordinator is not None:
            self.refresh_coordinator.close()
            self.refresh_coordinator = None
        self.refresh_recovery_after_id = None

    def _finalize_refresh_shutdown(self):
        self.is_refresh_shutdown = True
        if self.refresh_coordinator is not None:
            self.refresh_coordinator.close()
            self.refresh_coordinator = None
        self._close_window()

    def _build_main_layout(self):
        self.main_frame = tk.Frame(self.root, bg=self.color_bg)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=22, pady=10)

        self.left_scroll_host = tk.Frame(self.main_frame, bg=self.color_bg)
        self.left_scroll_host.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        self.left_scroll_host.configure(width=270)
        self.left_scroll_host.pack_propagate(False)

        self.left_scroll_canvas = tk.Canvas(
            self.left_scroll_host,
            bg=self.color_bg,
            highlightthickness=0,
            bd=0,
        )
        self.left_scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.left_scrollbar = ttk.Scrollbar(
            self.left_scroll_host,
            orient=tk.VERTICAL,
            command=self.left_scroll_canvas.yview,
            style="Tool.Vertical.TScrollbar",
        )
        self.left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.left_scroll_canvas.configure(yscrollcommand=self.left_scrollbar.set)

        self.left_column = tk.Frame(self.left_scroll_canvas, bg=self.color_bg)
        self.left_scroll_window = self.left_scroll_canvas.create_window(
            (0, 0),
            window=self.left_column,
            anchor="nw",
        )

        self.left_column.bind("<Configure>", self._update_left_scroll_region)
        self.left_scroll_canvas.bind("<Configure>", self._sync_left_scroll_width)

        self.right_column = tk.Frame(self.main_frame, bg=self.color_bg)
        self.right_column.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.right_scroll_canvas = tk.Canvas(
            self.right_column,
            bg=self.color_bg,
            highlightthickness=0,
            bd=0,
        )
        self.right_scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.right_scrollbar = ttk.Scrollbar(
            self.right_column,
            orient=tk.VERTICAL,
            command=self.right_scroll_canvas.yview,
            style="Tool.Vertical.TScrollbar",
        )
        self.right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_scrollbar_visible = True
        self.right_scroll_canvas.configure(yscrollcommand=self.right_scrollbar.set)

        self.right_content = tk.Frame(self.right_scroll_canvas, bg=self.color_bg)
        self.right_scroll_window = self.right_scroll_canvas.create_window(
            (0, 0),
            window=self.right_content,
            anchor="nw",
        )

        self.right_content.bind("<Configure>", self._update_right_scroll_region)
        self.right_scroll_canvas.bind("<Configure>", self._sync_right_scroll_width)

        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_mousewheel_linux_up, add="+")
        self.root.bind_all("<Button-5>", self._on_mousewheel_linux_down, add="+")

    def _create_step_card(self, parent, number, title):
        nav_item = tk.Frame(
            parent,
            bg=self.color_panel,
            highlightbackground=self.color_border,
            highlightthickness=1,
            cursor="hand2",
        )
        nav_item.pack(fill=tk.X, pady=6)

        header = tk.Frame(nav_item, bg=self.color_panel, cursor="hand2")
        header.pack(fill=tk.X, padx=14, pady=12)

        number_label = tk.Label(
            header,
            text=str(number),
            bg=self.color_border,
            fg="white",
            width=3,
            height=1,
            font=("Segoe UI", 12, "bold"),
            cursor="hand2",
        )
        number_label.pack(side=tk.LEFT, padx=(0, 12))

        heading = ttk.Label(header, text=title, style="Heading.TLabel")
        heading.pack(side=tk.LEFT)

        status_dot = tk.Label(
            header,
            text="●",
            bg=self.color_panel,
            fg=self.color_panel,
            font=("Segoe UI", 12, "bold"),
            cursor="hand2",
        )
        status_dot.pack(side=tk.RIGHT, padx=(10, 0))

        card = tk.Frame(
            self.right_content,
            bg=self.color_bg,
        )
        summary_frame = tk.Frame(
            card,
            bg=self.color_panel,
            highlightbackground=self.color_border,
            highlightthickness=1,
        )
        ttk.Label(
            summary_frame,
            text="summary",
            style="Dark.TLabel",
        ).pack(anchor=tk.W, padx=18, pady=(18, 6))
        summary_label = ttk.Label(
            summary_frame,
            text="",
            style="Muted.TLabel",
            justify=tk.LEFT,
            wraplength=650,
        )
        summary_label.pack(fill=tk.X, padx=18, pady=(0, 18))

        step_body = tk.Frame(
            card,
            bg=self.color_panel,
            highlightbackground=self.color_border,
            highlightthickness=1,
        )
        step_body.pack(fill=tk.BOTH, expand=True)

        card_header = tk.Frame(step_body, bg=self.color_panel)
        card_header.pack(fill=tk.X, padx=18, pady=(18, 10))
        ttk.Label(card_header, text=title, style="Heading.TLabel").pack(anchor=tk.W)

        content = tk.Frame(step_body, bg=self.color_panel)
        content.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))
        card.step_nav = nav_item
        card.step_header = nav_item
        card.step_number_label = number_label
        card.step_heading = heading
        card.step_status_dot = status_dot
        card.step_summary_frame = summary_frame
        card.step_summary_label = summary_label
        card.step_body = step_body
        card.step_card_header = card_header
        card.step_content = content
        card.step_title = title
        card.step_available = True

        for widget in (nav_item, header, number_label, heading, status_dot):
            widget.bind("<Button-1>", lambda _event, selected_card=card: self._activate_step(selected_card))
        return card, content

    def _build_left_column(self):
        self._build_step_2()
        self._build_subcommand_step()
        self._build_prepare_export_step()
        self._build_step_3()
        self._build_overlay_step()
        self._build_step_1()
        self._build_step_4()
        self._build_step_5()
        self.step_card_order = [
            self.step_2_card,
            self.subcommand_card,
            self.prepare_export_card,
            self.step_3_card,
            self.overlay_card,
            self.step_1_card,
            self.step_4_card,
            self.step_5_card,
        ]
        self.step_card_descriptions = {
            self.step_2_card: "Befehl festlegen",
            self.subcommand_card: "Unterbefehl passend zum Befehl waehlen",
            self.prepare_export_card: "Exportformat fuer prepare waehlen",
            self.step_3_card: "Template auswaehlen",
            self.overlay_card: "Datenlinien fuer Plot-Templates auswaehlen",
            self.step_1_card: "Analyseumfang waehlen",
            self.step_4_card: "Varianten passend zum Befehl auswaehlen",
            self.step_5_card: "Raeume auswaehlen oder automatisch uebernehmen",
        }

    def _build_step_1(self):
        self.step_1_card, content = self._create_step_card(self.left_column, 5, "Analyseumfang")

        button_frame = tk.Frame(content, bg=self.color_panel)
        button_frame.pack(fill=tk.X)

        self.scope_buttons = {}
        for scope in ["Eine Variante", "Mehrere Varianten", "Alle Varianten"]:
            button = tk.Button(
                button_frame,
                text=scope,
                command=lambda value=scope: self._set_analysis_scope(value),
                bg=self.color_panel_light,
                fg=self.color_text,
                activebackground=self.color_blue_dark,
                activeforeground="white",
                relief=tk.FLAT,
                font=("Segoe UI", 10),
                padx=18,
                pady=10,
            )
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
            self.scope_buttons[scope] = button

    def _build_step_2(self):
        self.step_2_card, content = self._create_step_card(self.left_column, 1, "Befehl")

        ttk.Label(content, text="Befehl auswaehlen", style="Dark.TLabel").pack(anchor=tk.W, pady=(0, 6))
        self.command_buttons = {}
        button_frame = tk.Frame(content, bg=self.color_panel)
        button_frame.pack(fill=tk.X)

        for command_name in self.commands:
            button = tk.Button(
                button_frame,
                text=command_name,
                command=lambda value=command_name: self._set_command(value),
                bg=self.color_panel_light,
                fg=self.color_text,
                activebackground=self.color_blue_dark,
                activeforeground="white",
                relief=tk.FLAT,
                font=("Segoe UI", 10),
                anchor=tk.W,
                padx=18,
                pady=10,
            )
            button.pack(fill=tk.X, pady=1)
            self.command_buttons[command_name] = button

    def _build_subcommand_step(self):
        self.subcommand_card, content = self._create_step_card(self.left_column, 2, "Unterbefehle")

        self.comfort_section = tk.Frame(content, bg=self.color_panel)
        ttk.Label(self.comfort_section, text="Comfort Unterbefehle", style="Dark.TLabel").pack(anchor=tk.W, pady=(0, 6))
        _, self.comfort_type_widgets = self._create_selection_button_group(
            self.comfort_section,
            [
                ("plot", "plot"),
                ("plot_analysis", "plot_analysis"),
                ("plot_overview", "plot_overview"),
                ("plot_analysis_overview", "plot_analysis_overview"),
            ],
            self._set_comfort_type,
        )

        self.load_subcommand_section = tk.Frame(content, bg=self.color_panel)
        self.load_subcommand_title = ttk.Label(
            self.load_subcommand_section,
            text="Unterbefehl",
            style="Dark.TLabel",
        )
        self.load_subcommand_title.pack(anchor=tk.W, pady=(0, 6))
        _, self.load_subcommand_buttons = self._create_selection_button_group(
            self.load_subcommand_section,
            [
                ("bar", "bar"),
                ("timeline", "timeline"),
            ],
            self._set_load_subcommand,
        )
        self.load_subcommand_note = ttk.Label(
            self.load_subcommand_section,
            text="bar erzeugt Maximalwertdiagramme. timeline aktiviert die Zeitansichten.",
            style="Muted.TLabel",
            wraplength=640,
            justify=tk.LEFT,
        )
        self.load_subcommand_note.pack(anchor=tk.W, pady=(6, 0))

    def _build_prepare_export_step(self):
        self.prepare_export_card, content = self._create_step_card(self.left_column, 3, "Exportformat")

        button_frame = tk.Frame(content, bg=self.color_panel)
        button_frame.pack(fill=tk.X)
        self.prepare_export_buttons = {}
        export_options = [
            ("csv", "csv"),
            ("excel", "excel"),
            ("both", "both"),
        ]
        for value, label in export_options:
            button = tk.Button(
                button_frame,
                text=label,
                command=lambda selected=value: self._set_prepare_export_format(selected),
                bg=self.color_panel_light,
                fg=self.color_text,
                activebackground=self.color_blue_dark,
                activeforeground="white",
                relief=tk.FLAT,
                font=("Segoe UI", 10),
                padx=18,
                pady=10,
            )
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
            self.prepare_export_buttons[value] = button

        self.prepare_export_note = ttk.Label(
            content,
            text="CSV ist das operative Standardformat fuer die Folgeskripte.",
            style="Muted.TLabel",
            wraplength=640,
            justify=tk.LEFT,
        )
        self.prepare_export_note.pack(anchor=tk.W, pady=(10, 0))

    def _create_selection_button_group(self, parent, options, command, columns=2, wraplength=240):
        """Erzeugt eine Einzelauswahl als Button-Raster mit festem 2-Spalten-Muster."""
        frame = tk.Frame(parent, bg=self.color_panel)
        frame.pack(fill=tk.X)

        for column in range(columns):
            frame.grid_columnconfigure(column, weight=1)

        buttons = {}
        for index, (value, label) in enumerate(options):
            button = tk.Button(
                frame,
                text=label,
                command=lambda selected=value: command(selected),
                bg=self.color_panel_light,
                fg=self.color_text,
                activebackground=self.color_blue_dark,
                activeforeground="white",
                disabledforeground=self.color_muted,
                relief=tk.FLAT,
                font=("Segoe UI", 10),
                justify=tk.CENTER,
                wraplength=wraplength,
                padx=18,
                pady=10,
            )
            button.grid(
                row=index // columns,
                column=index % columns,
                sticky="ew",
                padx=1,
                pady=1,
            )
            buttons[value] = button

        return frame, buttons

    def _enable_dynamic_button_group_height(self, frame, buttons, columns=2):
        """Laesst ein Button-Raster vertikal mit seinem Container mitwachsen."""
        if not buttons:
            return

        row_count = (len(buttons) + columns - 1) // columns
        for row in range(row_count):
            frame.grid_rowconfigure(row, weight=1, uniform="dynamic_button_rows")

        for button in buttons.values():
            button.grid_configure(sticky="nsew")

    def _build_step_3(self):
        self.step_3_card, content = self._create_step_card(self.left_column, 4, "Template")

        self.heating_mode_section = tk.Frame(content, bg=self.color_panel)
        self.load_mode_title = ttk.Label(self.heating_mode_section, text="Heizvergleich Modus", style="Dark.TLabel")
        self.load_mode_title.pack(anchor=tk.W, pady=(0, 6))
        _, self.heating_mode_buttons = self._create_selection_button_group(
            self.heating_mode_section,
            [
                ("single", "single"),
                ("compare", "compare"),
            ],
            self._set_heating_mode,
        )

        self.heating_note = ttk.Label(
            self.heating_mode_section,
            text="single erzeugt getrennte Ausgaben. compare fasst mehrere Datenreihen oder Varianten in einer Ausgabe zusammen.",
            style="Muted.TLabel",
            wraplength=640,
            justify=tk.LEFT,
        )
        self.heating_note.pack(anchor=tk.W, pady=(6, 0))

        self.heating_layout_section = tk.Frame(content, bg=self.color_panel)
        self.heating_layout_title = ttk.Label(self.heating_layout_section, text="Diagrammausgabe", style="Dark.TLabel")
        self.heating_layout_title.pack(anchor=tk.W, pady=(0, 6))
        _, self.heating_layout_buttons = self._create_selection_button_group(
            self.heating_layout_section,
            [
                ("separate", "separate"),
                ("combined", "combined"),
            ],
            self._set_heating_series_layout,
        )
        self.heating_layout_note = ttk.Label(
            self.heating_layout_section,
            text="Waehlt, ob mehrere Linien gemeinsam oder einzeln dargestellt werden sollen.",
            style="Muted.TLabel",
            wraplength=640,
            justify=tk.LEFT,
        )
        self.heating_layout_note.pack(anchor=tk.W, pady=(6, 0))

        self.analysis_section = tk.Frame(content, bg=self.color_panel)
        ttk.Label(self.analysis_section, text="Analyseebene", style="Dark.TLabel").pack(anchor=tk.W, pady=(0, 6))
        _, self.analysis_level_buttons = self._create_selection_button_group(
            self.analysis_section,
            [
                ("Analyse Raum", "Analyse Raum"),
                ("Analyse Variante", "Analyse Variante"),
            ],
            self._set_analysis_level,
        )
        self.analysis_note = ttk.Label(
            self.analysis_section,
            text="Steuert, ob die Auswertung raumbezogen oder variantenbezogen arbeitet.",
            style="Muted.TLabel",
            wraplength=640,
            justify=tk.LEFT,
        )
        self.analysis_note.pack(anchor=tk.W, pady=(6, 0))

        self.heating_view_section = tk.Frame(content, bg=self.color_panel)
        self.load_view_title = ttk.Label(self.heating_view_section, text="Heizvergleich Ansichten", style="Dark.TLabel")
        self.load_view_title.pack(anchor=tk.W, pady=(0, 6))
        self.heating_time_view_section = tk.Frame(self.heating_view_section, bg=self.color_panel)
        self.heating_time_view_section.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.heating_time_view_section, text="Zeitansichten", style="Dark.TLabel").pack(
            anchor=tk.W, pady=(0, 6)
        )

        self.heating_time_view_layout = tk.Frame(self.heating_time_view_section, bg=self.color_panel)
        self.heating_time_view_layout.pack(fill=tk.BOTH, expand=True)

        self.heating_time_view_buttons_section = tk.Frame(self.heating_time_view_layout, bg=self.color_panel)
        self.heating_time_view_buttons_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 20))
        self.heating_view_button_group_frame, self.heating_view_buttons = self._create_selection_button_group(
            self.heating_time_view_buttons_section,
            [
                ("year", "year"),
                ("month", "month"),
                ("week", "week"),
                ("day", "day"),
            ],
            self._set_heating_view,
        )
        self._enable_dynamic_button_group_height(
            self.heating_view_button_group_frame,
            self.heating_view_buttons,
        )
        self.heating_view_button_group_frame.pack(fill=tk.BOTH, expand=True)

        self.heating_view_detail_section = tk.Frame(self.heating_time_view_layout, bg=self.color_panel)
        self.heating_view_detail_section.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.heating_view_detail_title = ttk.Label(
            self.heating_view_detail_section,
            text="Detailauswahl",
            style="Dark.TLabel",
        )
        self.heating_view_detail_title.pack(anchor=tk.W, pady=(0, 6))

        self.heating_view_note = ttk.Label(
            self.heating_view_detail_section,
            text="Keine Zusatzangaben fuer die aktuelle Heizansicht erforderlich.",
            style="Muted.TLabel",
            wraplength=320,
            justify=tk.LEFT,
        )
        self.heating_view_note.pack(anchor=tk.W, pady=(0, 8))

        self.heating_month_container = tk.Frame(self.heating_view_detail_section, bg=self.color_panel)
        self.heating_month_label = ttk.Label(self.heating_month_container, text="Monat", style="Dark.TLabel")
        self.heating_month_label.pack(anchor=tk.W, pady=(0, 4))
        self.heating_month_combo = ttk.Combobox(
            self.heating_month_container,
            textvariable=self.heating_month,
            values=MONTH_NAMES,
            state="readonly",
        )
        self.heating_month_combo.pack(fill=tk.X)
        self.heating_month_combo.bind("<<ComboboxSelected>>", lambda event: self._update_dynamic_fields())

        self.heating_week_container = tk.Frame(self.heating_view_detail_section, bg=self.color_panel)
        self.heating_week_label = ttk.Label(self.heating_week_container, text="Kalenderwoche", style="Dark.TLabel")
        self.heating_week_label.pack(anchor=tk.W, pady=(0, 4))
        self.heating_week_entry = tk.Entry(
            self.heating_week_container,
            textvariable=self.heating_week,
            bg=self.color_panel_light,
            fg=self.color_text,
            insertbackground=self.color_text,
            relief=tk.FLAT,
            highlightbackground=self.color_border,
            highlightcolor=self.color_blue,
            font=("Segoe UI", 10),
        )
        self.heating_week_entry.pack(fill=tk.X)

        self.heating_day_container = tk.Frame(self.heating_view_detail_section, bg=self.color_panel)
        self.heating_day_label = ttk.Label(self.heating_day_container, text="Tag", style="Dark.TLabel")
        self.heating_day_label.pack(anchor=tk.W, pady=(0, 4))
        self.heating_day_combo = ttk.Combobox(
            self.heating_day_container,
            textvariable=self.heating_day,
            state="readonly",
        )
        self.heating_day_combo.pack(fill=tk.X)
        self.heating_day_combo.bind("<<ComboboxSelected>>", lambda event: self._update_dynamic_fields())

        self.plot_template_section = tk.Frame(content, bg=self.color_panel)
        ttk.Label(self.plot_template_section, text="Template", style="Dark.TLabel").pack(anchor=tk.W, pady=(0, 6))

        self.plot_template_grid = tk.Frame(self.plot_template_section, bg=self.color_panel)
        self.plot_template_grid.pack(fill=tk.X)
        for column in range(2):
            self.plot_template_grid.grid_columnconfigure(column, weight=1)

        self.plot_template_combo = self._create_labeled_entry(
            self.plot_template_grid,
            "Template",
            self.plot_template,
            row=0,
            column=0,
            values=PLOT_TEMPLATE_CHOICES,
        )
        self.plot_template_combo.bind("<<ComboboxSelected>>", lambda event: self._update_dynamic_fields())
        self.plot_template_note = ttk.Label(
            self.plot_template_section,
            text="Templates nutzen eine oder mehrere Varianten. Die meisten Templates erwarten genau einen Raum; Raumvergleich-Templates erlauben mehrere Raeume.",
            style="Muted.TLabel",
            wraplength=640,
            justify=tk.LEFT,
        )
        self.plot_template_note.pack(anchor=tk.W, pady=(8, 0))

    def _get_fixed_plot_overlay(self, overlay_id, fallback=None):
        for overlay in self.fixed_plot_overlays:
            if isinstance(overlay, dict) and overlay.get("id") == overlay_id:
                return overlay
        return fallback or {}

    def _format_fixed_overlay_source(self, overlay):
        source = overlay.get("source", "")
        column = overlay.get("column", "")
        if source == "aux":
            return f"REPORT-AUX.prn:{column}"
        if source == "csv":
            fallback_columns = overlay.get("fallback_columns", [])
            if fallback_columns:
                return f"{column}, Fallback {', '.join(fallback_columns)}"
            return column
        return column

    def _build_overlay_step(self):
        self.overlay_card, content = self._create_step_card(self.left_column, 5, "Überlagerungen")

        axis_section = tk.Frame(content, bg=self.color_panel)
        axis_section.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(axis_section, text="Temperaturachse", style="Dark.TLabel").pack(anchor=tk.W, pady=(0, 8))
        axis_grid = tk.Frame(
            axis_section,
            bg=self.color_panel_light,
            highlightbackground=self.color_border,
            highlightthickness=1,
        )
        axis_grid.pack(fill=tk.X)
        axis_grid.grid_columnconfigure(0, weight=1)
        axis_grid.grid_columnconfigure(1, weight=1)
        self.plot_temperature_ymin_entry = self._create_labeled_entry(
            axis_grid,
            "Min [°C]",
            self.plot_temperature_ymin,
            row=0,
            column=0,
        )
        self.plot_temperature_ymax_entry = self._create_labeled_entry(
            axis_grid,
            "Max [°C]",
            self.plot_temperature_ymax,
            row=0,
            column=1,
        )

        fixed_section = tk.Frame(content, bg=self.color_panel)
        fixed_section.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(fixed_section, text="Feste Linien", style="Dark.TLabel").pack(anchor=tk.W, pady=(0, 8))

        heat_row = tk.Frame(
            fixed_section, bg=self.color_panel_light, highlightbackground=self.color_border, highlightthickness=1
        )
        heat_row.pack(fill=tk.X, pady=3)
        ttk.Label(heat_row, text="Heizleistung [W]", style="Dark.TLabel").pack(anchor=tk.W, padx=10, pady=(8, 2))
        ttk.Label(heat_row, text="Pflichtlinie auf der linken Achse", style="Muted.TLabel").pack(
            anchor=tk.W,
            padx=10,
            pady=(0, 8),
        )

        self.setpoint_row = tk.Frame(
            fixed_section, bg=self.color_panel_light, highlightbackground=self.color_border, highlightthickness=1
        )
        self.setpoint_row.pack(fill=tk.X, pady=3)
        ttk.Checkbutton(
            self.setpoint_row,
            text="Sollwertband",
            variable=self.plot_show_setpoint_band,
            command=self._update_dynamic_fields,
            style="TCheckbutton",
        ).pack(anchor=tk.W, padx=10, pady=(8, 4))
        setpoint_grid = tk.Frame(self.setpoint_row, bg=self.color_panel_light)
        setpoint_grid.pack(fill=tk.X, padx=10, pady=(0, 8))
        setpoint_grid.grid_columnconfigure(0, weight=1)
        setpoint_grid.grid_columnconfigure(1, weight=1)
        self.plot_setpoint_min_entry = self._create_labeled_entry(
            setpoint_grid,
            "Min [°C]",
            self.plot_setpoint_min,
            row=0,
            column=0,
        )
        self.plot_setpoint_max_entry = self._create_labeled_entry(
            setpoint_grid,
            "Max [°C]",
            self.plot_setpoint_max,
            row=0,
            column=1,
        )

        outdoor_overlay = self._get_fixed_plot_overlay(
            OUTDOOR_OVERLAY_ID,
            {"label": "Außenlufttemperatur", "source": "aux", "column": DEFAULT_OUTDOOR_COLUMN},
        )
        operative_overlay = self._get_fixed_plot_overlay(
            OPERATIVE_OVERLAY_ID,
            {
                "label": "Operative Temperatur",
                "source": "csv",
                "column": "temperatures_top",
                "fallback_columns": ["local_de_comf_diag_t_top"],
            },
        )
        fixed_overlay_rows = [
            (
                outdoor_overlay.get("label", "Außenlufttemperatur"),
                self.plot_show_outdoor_temperature,
                f"{self._format_fixed_overlay_source(outdoor_overlay)}, rechte Achse",
            ),
            (
                operative_overlay.get("label", "Operative Temperatur"),
                self.plot_show_operative_temperature,
                f"{self._format_fixed_overlay_source(operative_overlay)}, rechte Achse",
            ),
        ]
        for label_text, variable, detail in fixed_overlay_rows:
            row = tk.Frame(
                fixed_section,
                bg=self.color_panel_light,
                highlightbackground=self.color_border,
                highlightthickness=1,
            )
            row.pack(fill=tk.X, pady=3)
            ttk.Checkbutton(
                row,
                text=label_text,
                variable=variable,
                command=self._update_dynamic_fields,
                style="TCheckbutton",
            ).pack(anchor=tk.W, padx=10, pady=(8, 2))
            ttk.Label(row, text=detail, style="Muted.TLabel").pack(anchor=tk.W, padx=10, pady=(0, 8))

        free_section = tk.Frame(content, bg=self.color_panel)
        free_section.pack(fill=tk.BOTH, expand=True)
        ttk.Label(free_section, text="Freie Datenlinien", style="Dark.TLabel").pack(anchor=tk.W, pady=(0, 8))

        editor = tk.Frame(free_section, bg=self.color_panel)
        editor.pack(fill=tk.X)
        for column in range(4):
            editor.grid_columnconfigure(column, weight=1)

        self.overlay_source_combo = self._create_labeled_entry(
            editor,
            "Quelle",
            self.overlay_source,
            row=0,
            column=0,
            values=["csv", "aux"],
        )
        self.overlay_source_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_overlay_column_options())
        self.overlay_column_combo = self._create_labeled_entry(
            editor,
            "Spalte",
            self.overlay_column,
            row=0,
            column=1,
            values=[],
        )
        self.overlay_column_combo.bind("<<ComboboxSelected>>", lambda _event: self._prefill_overlay_label())
        self.overlay_label_entry = self._create_labeled_entry(
            editor,
            "Anzeigename",
            self.overlay_label,
            row=0,
            column=2,
        )
        self.overlay_axis_combo = self._create_labeled_entry(
            editor,
            "Achse",
            self.overlay_axis,
            row=0,
            column=3,
            values=["temperature", "heat"],
        )

        button_row = tk.Frame(free_section, bg=self.color_panel)
        button_row.pack(fill=tk.X, pady=(8, 8))
        ttk.Button(
            button_row, text="Linie hinzufügen", style="Primary.TButton", command=self._add_free_overlay_line
        ).pack(side=tk.LEFT)
        ttk.Button(
            button_row,
            text="Linie entfernen",
            style="Secondary.TButton",
            command=self._remove_selected_free_overlay_line,
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.overlay_lines_listbox = tk.Listbox(
            free_section,
            height=6,
            selectmode=tk.BROWSE,
            bg=self.color_panel_light,
            fg=self.color_text,
            selectbackground=self.color_blue,
            selectforeground="white",
            highlightbackground=self.color_border,
            highlightcolor=self.color_blue,
            relief=tk.FLAT,
            exportselection=False,
            font=("Segoe UI", 10),
        )
        self.overlay_lines_listbox.pack(fill=tk.BOTH, expand=True)

    def _create_labeled_entry(self, parent, label_text, textvariable, row, column, values=None):
        """Erzeugt ein beschriftetes Eingabefeld im Optionsraster."""
        container = tk.Frame(parent, bg=self.color_panel)
        container.grid(row=row, column=column, sticky="ew", padx=2, pady=4)
        ttk.Label(container, text=label_text, style="Dark.TLabel").pack(anchor=tk.W, pady=(0, 4))
        if values is not None:
            widget = ttk.Combobox(container, textvariable=textvariable, values=values, state="readonly")
        else:
            widget = tk.Entry(
                container,
                textvariable=textvariable,
                bg=self.color_panel_light,
                fg=self.color_text,
                insertbackground=self.color_text,
                relief=tk.FLAT,
                highlightbackground=self.color_border,
                highlightcolor=self.color_blue,
                font=("Segoe UI", 10),
            )
        widget.pack(fill=tk.X)
        return widget

    def _build_step_4(self):
        self.step_4_card, content = self._create_step_card(self.left_column, 6, "Varianten")

        left = tk.Frame(content, bg=self.color_panel)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 20))

        right = tk.Frame(content, bg=self.color_panel)
        right.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        self.variants_listbox = tk.Listbox(
            left,
            height=6,
            selectmode=tk.MULTIPLE,
            bg=self.color_panel_light,
            fg=self.color_text,
            selectbackground=self.color_blue,
            selectforeground="white",
            highlightbackground=self.color_border,
            highlightcolor=self.color_blue,
            relief=tk.FLAT,
            exportselection=False,
            font=("Segoe UI", 10),
        )
        self.variants_listbox.pack(fill=tk.BOTH, expand=True)
        self.variants_listbox.bind("<<ListboxSelect>>", lambda _event: self._handle_variant_selection_changed())

        self.variant_note = ttk.Label(
            right,
            text="Es ist aktuell keine Variante ausgewaehlt. Bitte waehlen Sie mindestens eine Variante.",
            style="Muted.TLabel",
            wraplength=330,
        )
        self.variant_note.pack(anchor=tk.W)

    def _build_step_5(self):
        self.step_5_card, content = self._create_step_card(self.left_column, 7, "Raeume")

        self.step_5_left = tk.Frame(content, bg=self.color_panel)
        self.step_5_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 20))

        self.step_5_right = tk.Frame(content, bg=self.color_panel)
        self.step_5_right.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        self.rooms_listbox = tk.Listbox(
            self.step_5_left,
            height=5,
            selectmode=tk.MULTIPLE,
            bg=self.color_panel_light,
            fg=self.color_text,
            selectbackground=self.color_blue,
            selectforeground="white",
            highlightbackground=self.color_border,
            highlightcolor=self.color_blue,
            relief=tk.FLAT,
            exportselection=False,
            font=("Segoe UI", 10),
        )
        self.rooms_listbox.pack(fill=tk.BOTH, expand=True)
        self.rooms_listbox.bind("<<ListboxSelect>>", lambda _event: self._handle_room_selection_changed())

        self.room_note = ttk.Label(
            self.step_5_right,
            text="Es ist aktuell kein Raum ausgewaehlt. Bitte waehlen Sie mindestens einen Raum.",
            style="Muted.TLabel",
            wraplength=330,
        )
        self.room_note.pack(anchor=tk.W)

    def _build_right_column(self):
        self.run_log_text = None
        self.steps_list_container = None
        self._activate_first_available_step()

    def _refresh_step_indicators(self):
        visible_cards = [card for card in self.step_card_order if getattr(card, "step_available", True)]

        for index, card in enumerate(visible_cards, start=1):
            card.step_number_label.configure(text=str(index))

        if self.active_step_card not in visible_cards:
            self._activate_first_available_step()
        else:
            self._update_step_nav_styles()

    def _activate_first_available_step(self):
        for card in getattr(self, "step_card_order", []):
            if getattr(card, "step_available", True):
                self._activate_step(card)
                return

    def _activate_next_available_step_after(self, current_card):
        try:
            current_index = self.step_card_order.index(current_card)
        except ValueError:
            return

        for card in self.step_card_order[current_index + 1 :]:
            if getattr(card, "step_available", True) and card.step_nav.winfo_manager() == "pack":
                self._activate_step(card)
                return

    def _advance_after_completed_single_choice(self, current_card):
        if self._is_single_choice_step_complete(current_card):
            self._activate_next_available_step_after(current_card)

    def _is_single_choice_step_complete(self, card):
        selected_command = self.command.get()

        if card is self.subcommand_card:
            if selected_command == "comfort":
                return bool(self.comfort_type.get())
            if selected_command in {"heating", "cooling"}:
                return self.load_subcommand.get() in {"bar", "timeline"}
            return False

        if card is self.prepare_export_card:
            return bool(self.prepare_export_format.get())

        if card is self.step_3_card:
            if selected_command == "plot-template":
                return bool(self.plot_template.get())
            if selected_command == "comfort":
                return bool(self.analysis_level.get())
            if selected_command == "analyze_data":
                return bool(self.heating_series_layout.get())
            if selected_command in {"heating", "cooling"}:
                if self.load_subcommand.get() not in {"bar", "timeline"} or not self.heating_mode.get():
                    return False
                if self.heating_mode.get() == "compare" and not self.heating_series_layout.get():
                    return False
                if self.load_subcommand.get() == "timeline" and self.heating_view.get() not in {
                    "year",
                    "month",
                    "week",
                    "day",
                }:
                    return False
                return True
            return False

        return False

    def _activate_step(self, card):
        if not getattr(card, "step_available", True):
            return
        for step_card in getattr(self, "step_card_order", []):
            if step_card.winfo_manager() == "pack":
                step_card.pack_forget()
        card.pack(fill=tk.BOTH, expand=True)
        self.active_step_card = card
        self._update_step_nav_styles()
        self.right_scroll_canvas.yview_moveto(0)

    def _update_step_nav_styles(self):
        for card in getattr(self, "step_card_order", []):
            bg = self.color_panel
            number_bg = self.color_border
            dot_color = self.color_blue if card is self.active_step_card else self.color_panel
            card.step_nav.configure(bg=bg, highlightbackground=self.color_border)
            card.step_header.configure(bg=bg)
            card.step_number_label.configure(bg=number_bg)
            card.step_heading.configure(background=bg)
            card.step_status_dot.configure(bg=bg, fg=dot_color)

    def _build_step_summary_text(self, target_card):
        lines = []
        for card in getattr(self, "step_card_order", []):
            if card is target_card:
                break
            if not getattr(card, "step_available", True) or card.step_nav.winfo_manager() != "pack":
                continue
            summary_line = self._get_step_summary_line(card)
            if summary_line:
                lines.append(summary_line)
        return "\n".join(lines)

    def _format_summary_selection(self, singular_label, plural_label, values):
        if not values:
            return ""
        if len(values) == 1:
            return f"{singular_label}: {values[0]}"
        return f"{plural_label}: {len(values)} ausgewaehlt"

    def _get_step_summary_line(self, card):
        if card is self.step_2_card:
            command = self.command.get()
            return f"Befehl: {command}" if command else ""

        if card is self.subcommand_card:
            if self.command.get() == "comfort" and self.comfort_type.get():
                return f"Unterbefehl: {self.comfort_type.get()}"
            if self.command.get() in {"heating", "cooling"} and self.load_subcommand.get():
                return f"Unterbefehl: {self.load_subcommand.get()}"
            return ""

        if card is self.prepare_export_card and self.prepare_export_format.get():
            return f"Exportformat: {self.prepare_export_format.get()}"

        if card is self.step_3_card:
            selected_command = self.command.get()
            if selected_command == "plot-template":
                template_label = self.plot_template.get()
                spec = get_plot_template_spec(template_label)
                if spec is None or spec.view == "year":
                    return f"Template: {template_label}"
                if spec.view == "month":
                    return f"Template: {template_label}, Monat {self.heating_month.get()}"
                if spec.view == "week":
                    return f"Template: {template_label}, KW {self.heating_week.get()}"
                if spec.view == "day":
                    return f"Template: {template_label}, {self.heating_day.get()}. {self.heating_month.get()}"
                return f"Template: {template_label}"
            if selected_command == "comfort" and self.analysis_level.get():
                return f"Analyseebene: {self.analysis_level.get()}"
            if selected_command == "analyze_data" and self.heating_series_layout.get():
                return f"Excel-Ausgabe: {self.heating_series_layout.get()}"
            if selected_command in {"heating", "cooling"}:
                parts = []
                if self.heating_mode.get():
                    parts.append(f"Modus {self.heating_mode.get()}")
                if self.heating_mode.get() == "compare" and self.heating_series_layout.get():
                    parts.append(f"Ausgabe {self.heating_series_layout.get()}")
                if self.load_subcommand.get() == "timeline" and self.heating_view.get():
                    view_label = self.heating_view.get()
                    if view_label == "month":
                        view_label = f"month {self.heating_month.get()}"
                    elif view_label == "week":
                        view_label = f"week KW {self.heating_week.get()}"
                    elif view_label == "day":
                        view_label = f"day {self.heating_month.get()} {self.heating_day.get()}"
                    parts.append(f"Ansicht {view_label}")
                return f"Optionen: {', '.join(parts)}" if parts else ""
            return ""

        if card is self.overlay_card:
            parts = []
            if self.plot_show_setpoint_band.get():
                parts.append(f"Sollwertband {self.plot_setpoint_min.get()}-{self.plot_setpoint_max.get()} °C")
            if self.plot_show_outdoor_temperature.get():
                parts.append("Außenluft")
            if self.plot_show_operative_temperature.get():
                parts.append("Operative Temperatur")
            if self.free_overlay_lines:
                line_label = "freie Linie" if len(self.free_overlay_lines) == 1 else "freie Linien"
                parts.append(f"{len(self.free_overlay_lines)} {line_label}")
            return f"Überlagerungen: {', '.join(parts)}" if parts else ""

        if card is self.step_1_card and self.analysis_scope.get():
            return f"Analyseumfang: {self.analysis_scope.get()}"

        if card is self.step_4_card:
            if self.analysis_scope.get() == "Alle Varianten" and self.command.get() != "plot-template":
                return f"Varianten: alle ({len(self.variant_names)})"
            return self._format_summary_selection("Variante", "Varianten", self._get_selected_variants())

        if card is self.step_5_card:
            return self._format_summary_selection("Raum", "Raeume", self._get_selected_rooms())

        return ""

    def _update_step_summaries(self):
        for card in getattr(self, "step_card_order", []):
            summary_text = self._build_step_summary_text(card)
            card.step_summary_label.configure(text=summary_text)
            if summary_text and card.step_summary_frame.winfo_manager() != "pack":
                card.step_summary_frame.pack(
                    fill=tk.X,
                    pady=(0, 12),
                    before=card.step_body,
                )
            elif not summary_text and card.step_summary_frame.winfo_manager() == "pack":
                card.step_summary_frame.pack_forget()
        self._update_right_scrollbar_visibility()

    def _set_status(self, message):
        self.status_var.set(message)
        if self.analysis_status_var is not None:
            self.analysis_status_var.set(message)
        self.root.update_idletasks()

    def _append_log(self, text, clear=False):
        if clear:
            self._clear_log_widgets()
        if self.run_log_text is None:
            return
        if text:
            self._append_log_text(text.rstrip() + "\n")

    def _clear_log_widgets(self):
        for text_widget in (self.run_log_text, self.expanded_log_text, self.analysis_log_text):
            if text_widget is None:
                continue
            with contextlib.suppress(tk.TclError):
                text_widget.configure(state=tk.NORMAL)
                text_widget.delete("1.0", tk.END)
                text_widget.configure(state=tk.DISABLED)

    def _append_log_text(self, text):
        if not text:
            return
        for text_widget in (self.run_log_text, self.expanded_log_text, self.analysis_log_text):
            if text_widget is None:
                continue
            with contextlib.suppress(tk.TclError):
                text_widget.configure(state=tk.NORMAL)
                text_widget.insert(tk.END, text)
                text_widget.see(tk.END)
                text_widget.configure(state=tk.DISABLED)

    def _expand_log_panel(self):
        if self.is_log_expanded:
            return

        self.is_log_expanded = True
        if self.log_expand_button is not None:
            self.log_expand_button.configure(text="⤡")

        if self.main_frame is not None:
            self.main_frame.pack_forget()
        if self.bottom_button_frame is not None:
            self.bottom_button_frame.pack_forget()

        self.log_focus_frame = tk.Frame(self.root, bg=self.color_bg)
        self.log_focus_frame.pack(fill=tk.BOTH, expand=True, padx=22, pady=10)

        focus_card = tk.Frame(
            self.log_focus_frame,
            bg=self.color_panel_light,
            highlightbackground=self.color_border,
            highlightthickness=1,
        )
        focus_card.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(focus_card, bg=self.color_panel_light)
        header.pack(fill=tk.X, padx=16, pady=(14, 10))
        ttk.Label(header, text="Status und Protokoll", style="Heading.TLabel").pack(side=tk.LEFT, anchor=tk.W)

        collapse_button = tk.Button(
            header,
            text="⤡",
            command=self._collapse_log_panel,
            bg=self.color_panel_light,
            fg=self.color_text,
            activebackground=self.color_blue_dark,
            activeforeground="white",
            relief=tk.FLAT,
            font=("Segoe UI Symbol", 12, "bold"),
            width=3,
            cursor="hand2",
        )
        collapse_button.pack(side=tk.RIGHT)

        ttk.Label(
            focus_card,
            textvariable=self.status_var,
            style="Muted.TLabel",
        ).pack(anchor=tk.W, padx=16, pady=(0, 8))

        body = tk.Frame(focus_card, bg=self.color_panel_light)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        self.expanded_log_text = tk.Text(
            body,
            bg=self.color_panel,
            fg=self.color_text,
            insertbackground=self.color_text,
            relief=tk.FLAT,
            highlightbackground=self.color_border,
            highlightcolor=self.color_blue,
            font=("Consolas", 9),
            wrap=tk.WORD,
        )
        scrollbar = ttk.Scrollbar(
            body,
            orient=tk.VERTICAL,
            command=self.expanded_log_text.yview,
            style="Tool.Vertical.TScrollbar",
        )
        self.expanded_log_text.configure(yscrollcommand=scrollbar.set)
        self.expanded_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.expanded_log_text.configure(state=tk.NORMAL)
        if self.run_log_text is not None:
            with contextlib.suppress(tk.TclError):
                existing_log = self.run_log_text.get("1.0", "end-1c")
                if existing_log:
                    self.expanded_log_text.insert(tk.END, existing_log)
        self.expanded_log_text.see(tk.END)
        self.expanded_log_text.configure(state=tk.DISABLED)

    def _collapse_log_panel(self):
        if not self.is_log_expanded:
            return

        self.is_log_expanded = False
        self.expanded_log_text = None
        if self.log_focus_frame is not None:
            with contextlib.suppress(tk.TclError):
                self.log_focus_frame.destroy()
        self.log_focus_frame = None

        if self.log_expand_button is not None:
            self.log_expand_button.configure(text="⤢")

        if self.main_frame is not None:
            self.main_frame.pack(fill=tk.BOTH, expand=True, padx=22, pady=10, after=self.title_frame)
        if self.bottom_button_frame is not None:
            self.bottom_button_frame.pack(fill=tk.X, padx=22, pady=(0, 18), after=self.main_frame)

    def _create_analysis_log_window(self, command_name):
        if self.analysis_log_window is not None and self.analysis_log_window.winfo_exists():
            self.analysis_log_window.destroy()

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Analyse laeuft: {command_name}")
        dialog.geometry("980x560")
        dialog.minsize(760, 420)
        dialog.configure(bg=self.color_bg)
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", self._handle_analysis_log_window_close)

        header = tk.Frame(dialog, bg=self.color_bg)
        header.pack(fill=tk.X, padx=18, pady=(16, 8))
        ttk.Label(header, text="Status und Protokoll", style="Heading.TLabel").pack(anchor=tk.W)

        self.analysis_status_var = tk.StringVar(value=self.status_var.get())
        ttk.Label(
            header,
            textvariable=self.analysis_status_var,
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(6, 0))

        body = tk.Frame(dialog, bg=self.color_bg)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))

        text_widget = tk.Text(
            body,
            bg=self.color_panel,
            fg=self.color_text,
            insertbackground=self.color_text,
            relief=tk.FLAT,
            highlightbackground=self.color_border,
            highlightcolor=self.color_blue,
            font=("Consolas", 9),
            wrap=tk.WORD,
        )
        scrollbar = ttk.Scrollbar(
            body,
            orient=tk.VERTICAL,
            command=text_widget.yview,
            style="Tool.Vertical.TScrollbar",
        )
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.configure(state=tk.DISABLED)

        self.analysis_log_window = dialog
        self.analysis_log_text = text_widget
        dialog.lift()

    def _handle_analysis_log_window_close(self):
        if self.is_running_pipeline:
            messagebox.showinfo(
                "Analyse laeuft",
                "Das Protokollfenster bleibt waehrend der laufenden Analyse geoeffnet.",
                parent=self.analysis_log_window if self.analysis_log_window is not None else self.root,
            )
            return
        self._destroy_analysis_log_window()

    def _destroy_analysis_log_window(self):
        if self.analysis_log_window is not None:
            with contextlib.suppress(tk.TclError):
                self.analysis_log_window.destroy()
        self.analysis_log_window = None
        self.analysis_log_text = None
        self.analysis_status_var = None

    def _schedule_pipeline_log_polling(self):
        if self.pipeline_log_poll_after_id is None:
            self.pipeline_log_poll_after_id = self.root.after(80, self._poll_pipeline_log_queue)

    def _poll_pipeline_log_queue(self):
        self.pipeline_log_poll_after_id = None
        if self.pipeline_queue is None:
            return

        completed_result = None
        while True:
            try:
                message_type, payload = self.pipeline_queue.get_nowait()
            except queue.Empty:
                break

            if message_type == "log":
                self._append_log_text(payload)
            elif message_type == "done":
                completed_result = payload

        if completed_result is not None:
            self._finish_pipeline_run(*completed_result)
            return

        if self.is_running_pipeline:
            self._schedule_pipeline_log_polling()

    def _run_pipeline_worker(
        self,
        selected_command,
        steps,
        variants,
        rooms,
        heating_mode,
        prepare_options,
        comfort_options,
        heating_options,
        plot_template_options,
    ):
        success = True
        writer = QueueLogWriter(self.pipeline_queue)

        def _execute_selected_command():
            if selected_command == "all":
                all_args = build_runtime_args(
                    self.args,
                    variants=variants,
                    rooms=rooms,
                )
                run_all(all_args)
                return

            execute_steps(
                self.args,
                steps=steps,
                variants=variants,
                rooms=rooms,
                heating_mode=heating_mode,
                prepare_options=prepare_options,
                comfort_options=comfort_options,
                heating_options=heating_options,
                plot_template_options=plot_template_options,
            )

        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                if should_log_command(selected_command):
                    with command_log(selected_command) as log_file:
                        print(f"Logdatei: {log_file}")
                        _execute_selected_command()
                    print(f"Log gespeichert: {log_file}")
                    return

                _execute_selected_command()
        except SystemExit as exc:
            success = exc.code in (0, None)
            if not success:
                self.pipeline_queue.put(("log", f"X Prozess beendet mit Exit-Code {exc.code}\n"))
        except Exception:
            success = False
            self.pipeline_queue.put(("log", traceback.format_exc()))
        finally:
            self.pipeline_queue.put(("done", (selected_command, success)))

    def _finish_pipeline_run(self, selected_command, success):
        self.is_running_pipeline = False
        self.pipeline_thread = None
        self.pipeline_queue = None
        self.start_button.configure(state=tk.NORMAL)
        self.reset_button.configure(state=tk.NORMAL)

        if success:
            self._set_status(f"Pipeline abgeschlossen: {selected_command}")
            self._destroy_analysis_log_window()
            messagebox.showinfo("Analyse", "Der Befehl wurde erfolgreich ausgefuehrt.", parent=self.root)
        else:
            self._set_status(f"Pipeline fehlgeschlagen: {selected_command}")
            if self.analysis_log_window is not None and self.analysis_log_window.winfo_exists():
                self.analysis_log_window.lift()
            messagebox.showerror(
                "Analyse",
                "Bei der Ausfuehrung ist ein Fehler aufgetreten. Details stehen im Protokoll.",
                parent=self.root,
            )

    def _safe_popup_menu(self, menu, x_pos, y_pos):
        try:
            menu.tk_popup(x_pos, y_pos)
        finally:
            menu.grab_release()

    def _open_log_view(self):
        if self.analysis_log_window is not None and self.analysis_log_window.winfo_exists():
            self.analysis_log_window.lift()
            with contextlib.suppress(tk.TclError):
                self.analysis_log_window.focus_force()
            return
        self._expand_log_panel()

    def _build_bottom_buttons(self):
        self.bottom_button_frame = tk.Frame(self.root, bg=self.color_bg)
        self.bottom_button_frame.pack(fill=tk.X, padx=22, pady=(0, 18))

        self.settings_bottom_button = ttk.Button(
            self.bottom_button_frame,
            text="settings",
            style="Secondary.TButton",
            command=self._open_tools_menu,
        )
        self.settings_bottom_button.pack(side=tk.LEFT)

        self.log_bottom_button = ttk.Button(
            self.bottom_button_frame,
            text="log",
            style="Secondary.TButton",
            command=self._open_log_view,
        )
        self.log_bottom_button.pack(side=tk.LEFT, padx=(8, 0))

        self.bottom_status_label = ttk.Label(
            self.bottom_button_frame,
            textvariable=self.status_var,
            style="Muted.TLabel",
        )
        self.bottom_status_label.pack(side=tk.LEFT, padx=(14, 0))

        self.start_button = ttk.Button(
            self.bottom_button_frame,
            text="Start",
            style="Primary.TButton",
            command=self._start_pipeline,
        )
        self.start_button.pack(side=tk.RIGHT)

        self.reset_button = ttk.Button(
            self.bottom_button_frame,
            text="Zuruecksetzen",
            style="Secondary.TButton",
            command=self._reset_fields,
        )
        self.reset_button.pack(side=tk.RIGHT, padx=(0, 12))

    def _populate_variants(self):
        selected_names = []
        if self.variants_listbox.size() > 0 and self.variants_listbox.get(0) != "[Keine Varianten gefunden]":
            selected_names = [self.variants_listbox.get(index) for index in self.variants_listbox.curselection()]

        selected_command = self.command.get()
        if selected_command == "prepare":
            variant_source_kind = "input"
            available_variants = list_input_variants(self.args.input_dir)
            source_dir = INPUT_DIR
        else:
            variant_source_kind = "datenbank"
            available_variants = list_datenbank_variants(self.args.datenbank_dir)
            source_dir = DATENBANK_DIR

        variant_names = sorted({strip_variant_suffix(variant) for variant in available_variants})
        if variant_source_kind == self.variant_source_kind and variant_names == self.variant_names:
            return

        self.variants_listbox.delete(0, tk.END)
        self.variant_source_kind = variant_source_kind
        self.variant_names = variant_names

        if not self.variant_names:
            self.variants_listbox.insert(tk.END, "[Keine Varianten gefunden]")
            self.variants_listbox.configure(state=tk.DISABLED)
            self.variant_note.configure(text=f"Keine Varianten in {source_dir} gefunden.")
            return

        for variant_name in self.variant_names:
            self.variants_listbox.insert(tk.END, variant_name)

        for variant_name in selected_names:
            if variant_name not in self.variant_names:
                continue
            selected_index = self.variant_names.index(variant_name)
            self.variants_listbox.selection_set(selected_index)

    def _populate_rooms(self):
        self.rooms_listbox.delete(0, tk.END)
        for room in ROOMS:
            self.rooms_listbox.insert(tk.END, room)

    def _select_all_rooms(self):
        self.rooms_listbox.configure(state=tk.NORMAL)
        self.rooms_listbox.selection_set(0, tk.END)

    def _set_analysis_scope(self, value):
        self.analysis_scope.set(value)
        self._update_dynamic_fields()
        self._activate_step(self.step_4_card)

    def _set_command(self, value):
        if value in DISABLED_GUI_COMMANDS:
            return
        self.command.set(value)
        self.load_subcommand.set("")
        self._update_dynamic_fields()
        self._activate_next_available_step_after(self.step_2_card)

    def _set_prepare_export_format(self, value):
        self.prepare_export_format.set(value)
        self._update_dynamic_fields()
        self._advance_after_completed_single_choice(self.prepare_export_card)

    def _set_analysis_level(self, value):
        self.analysis_level.set(value)
        self._update_dynamic_fields()
        self._advance_after_completed_single_choice(self.step_3_card)

    def _set_heating_mode(self, value):
        self.heating_mode.set(value)
        self._update_dynamic_fields()
        self._advance_after_completed_single_choice(self.step_3_card)

    def _set_heating_series_layout(self, value):
        self.heating_series_layout.set(value)
        self._update_dynamic_fields()
        self._advance_after_completed_single_choice(self.step_3_card)

    def _set_load_subcommand(self, value):
        self.load_subcommand.set(value)
        if value == "bar":
            self.heating_view.set("bar")
        elif value == "timeline" and self.heating_view.get() == "bar":
            self.heating_view.set("")
        self._update_dynamic_fields()
        self._advance_after_completed_single_choice(self.subcommand_card)

    def _set_comfort_type(self, value):
        self.comfort_type.set(value)
        self._update_dynamic_fields()
        self._advance_after_completed_single_choice(self.subcommand_card)

    def _set_heating_view(self, value):
        self.heating_view.set(value)
        self._update_dynamic_fields()
        self._advance_after_completed_single_choice(self.step_3_card)

    def _update_dynamic_fields(self):
        self._populate_variants()
        self._update_scope_buttons()
        self._update_command_buttons()
        self._update_prepare_export_buttons()
        self._update_analysis_level_buttons()
        self._update_heating_mode_buttons()
        self._update_heating_layout_buttons()
        self._update_load_subcommand_buttons()
        self._update_heating_view_buttons()
        self._update_step_visibility()
        self._update_subcommand_dependent_fields()
        self._update_command_dependent_fields()
        self._update_prepare_export_note()
        self._update_comfort_options_for_analysis_level()
        self._update_heating_detail_fields()
        self._update_variant_field()
        self._update_room_field()
        self._refresh_overlay_catalog()
        self._refresh_step_indicators()
        self._update_step_summaries()

    def _update_step_visibility(self):
        selected_command = self.command.get()
        no_command = not selected_command
        is_prepare = selected_command == "prepare"
        show_subcommands = selected_command in {"comfort", "heating", "cooling"}
        load_without_subcommand = selected_command in {"heating", "cooling"} and self.load_subcommand.get() not in {
            "bar",
            "timeline",
        }
        hide_options_step = no_command or selected_command in {"prepare", "all"} or load_without_subcommand
        show_overlays = selected_command == "plot-template" and template_uses_overlay_options(self.plot_template.get())
        self._set_card_visible(self.subcommand_card, show_subcommands)
        self._set_card_visible(self.prepare_export_card, is_prepare)
        self._set_card_visible(self.step_3_card, not hide_options_step)
        self._set_card_visible(self.overlay_card, show_overlays)
        self._set_card_visible(self.step_4_card, True)
        self._set_card_visible(self.step_5_card, not is_prepare)

    def _set_card_visible(self, card, visible):
        card.step_available = visible
        nav_visible = card.step_nav.winfo_manager() == "pack"
        if visible and not nav_visible:
            self._show_step_card_in_order(card)
        elif not visible and nav_visible:
            card.step_nav.pack_forget()
        if not visible and card.winfo_manager() == "pack":
            card.pack_forget()

    def _show_step_card_in_order(self, card):
        card_index = self.step_card_order.index(card)
        for next_card in self.step_card_order[card_index + 1 :]:
            if next_card.step_nav.winfo_manager() == "pack":
                card.step_nav.pack(fill=tk.X, pady=6, before=next_card.step_nav)
                return
        card.step_nav.pack(fill=tk.X, pady=6)

    def _update_scope_buttons(self):
        for scope, button in self.scope_buttons.items():
            if self.analysis_scope.get() == scope:
                button.configure(bg=self.color_blue, fg="white")
            else:
                button.configure(bg=self.color_panel_light, fg=self.color_text)

    def _update_command_buttons(self):
        for command_name, button in self.command_buttons.items():
            if command_name in DISABLED_GUI_COMMANDS:
                button.configure(
                    state=tk.DISABLED,
                    bg=self.color_panel,
                    fg=self.color_muted,
                    disabledforeground=self.color_muted,
                )
            elif self.command.get() == command_name:
                button.configure(bg=self.color_blue, fg="white")
            else:
                button.configure(
                    state=tk.NORMAL,
                    bg=self.color_panel_light,
                    fg=self.color_text,
                )

    def _update_prepare_export_buttons(self):
        for export_format, button in self.prepare_export_buttons.items():
            if self.prepare_export_format.get() == export_format:
                button.configure(bg=self.color_blue, fg="white")
            else:
                button.configure(bg=self.color_panel_light, fg=self.color_text)

    def _update_selection_button_group(self, buttons, selected_value, disabled_values=None):
        disabled_values = disabled_values or set()
        for value, button in buttons.items():
            if value in disabled_values:
                button.configure(
                    state=tk.DISABLED,
                    bg=self.color_panel,
                    fg=self.color_muted,
                    disabledforeground=self.color_muted,
                )
            elif value == selected_value:
                button.configure(state=tk.NORMAL, bg=self.color_blue, fg="white")
            else:
                button.configure(state=tk.NORMAL, bg=self.color_panel_light, fg=self.color_text)

    def _update_analysis_level_buttons(self):
        self._update_selection_button_group(
            self.analysis_level_buttons,
            self.analysis_level.get(),
        )

    def _update_heating_mode_buttons(self):
        self._update_selection_button_group(
            self.heating_mode_buttons,
            self.heating_mode.get(),
        )

    def _update_heating_layout_buttons(self):
        self._update_selection_button_group(
            self.heating_layout_buttons,
            self.heating_series_layout.get(),
        )

    def _update_load_subcommand_buttons(self):
        self._update_selection_button_group(
            self.load_subcommand_buttons,
            self.load_subcommand.get(),
        )

    def _update_heating_view_buttons(self):
        self._update_selection_button_group(
            self.heating_view_buttons,
            self.heating_view.get(),
        )

    def _update_prepare_export_note(self):
        selected_format = self.prepare_export_format.get()
        if selected_format == "csv":
            self.prepare_export_note.configure(text="CSV ist das operative Standardformat fuer die Folgeskripte.")
            return
        if selected_format == "excel":
            self.prepare_export_note.configure(
                text="Excel dient aktuell nur der uebersichtlicheren Darstellung. Die Folgeskripte verwenden weiterhin CSV-Dateien."
            )
            return
        if selected_format == "both":
            self.prepare_export_note.configure(
                text="CSV + Excel erzeugt operative CSV-Dateien fuer die Pipeline und zusaetzlich XLSX-Dateien zur Ansicht."
            )
            return
        self.prepare_export_note.configure(text="Bitte waehlen Sie ein Exportformat.")

    def _update_subcommand_dependent_fields(self):
        selected_command = self.command.get()
        for section in [
            self.comfort_section,
            self.load_subcommand_section,
        ]:
            section.pack_forget()

        if selected_command == "comfort":
            self.comfort_section.pack(fill=tk.X)
            return

        if selected_command in {"heating", "cooling"}:
            self.load_subcommand_title.configure(
                text="Kuehlvergleich Unterbefehle" if selected_command == "cooling" else "Heizvergleich Unterbefehle"
            )
            self.load_subcommand_note.configure(
                text="bar erzeugt Maximalwertdiagramme. timeline aktiviert die Zeitansichten."
            )
            self.load_subcommand_section.pack(fill=tk.X)

    def _update_command_dependent_fields(self):
        selected_command = self.command.get()
        steps = self.command_to_steps.get(selected_command, [])

        prepare_active = selected_command == "prepare"
        analyze_active = selected_command == "analyze_data"
        all_active = selected_command == "all"
        heating_active = "heating" in steps
        cooling_active = "cooling" in steps
        load_active = heating_active or cooling_active
        comfort_active = selected_command == "comfort"

        for section in [
            self.heating_mode_section,
            self.heating_layout_section,
            self.analysis_section,
            self.heating_view_section,
            self.plot_template_section,
        ]:
            section.pack_forget()

        if not selected_command:
            return

        if all_active:
            return

        if load_active:
            self._set_time_view_buttons_visible(True)
            self.load_mode_title.configure(text="Kuehlvergleich Modus" if cooling_active else "Heizvergleich Modus")
            self.load_view_title.configure(
                text="Kuehlvergleich Ansichten" if cooling_active else "Heizvergleich Ansichten"
            )
            self.heating_layout_title.configure(text="Diagrammausgabe")
            if self.load_subcommand.get() not in {"bar", "timeline"}:
                return
            self.heating_mode_section.pack(fill=tk.X, pady=(0, 12))
            if self.heating_mode.get() == "compare":
                self.heating_layout_section.pack(fill=tk.X, pady=(0, 12))
                self.heating_layout_note.configure(
                    text="Waehlt, ob mehrere Linien einzeln oder gemeinsam dargestellt werden sollen."
                )
            if self.load_subcommand.get() == "timeline":
                self.heating_view_section.pack(fill=tk.X)
            self.heating_note.configure(
                text="single erzeugt getrennte Ausgaben. compare fasst mehrere Datenreihen oder Varianten in einer Ausgabe zusammen."
            )
            return

        if selected_command == "plot-template":
            self.plot_template_section.pack(fill=tk.X)
            spec = get_plot_template_spec(self.plot_template.get())
            if spec is not None and is_time_filtered_template(self.plot_template.get()):
                if self.heating_view.get() != spec.view:
                    self.heating_view.set(spec.view)
                self.load_view_title.configure(text="Template-Zeitwahl")
                self._set_time_view_buttons_visible(False)
                self.heating_view_section.pack(fill=tk.X, pady=(12, 0))
            return

        if comfort_active:
            self.analysis_section.pack(fill=tk.X)
            return

        if analyze_active:
            self.heating_layout_title.configure(text="Excel-Ausgabe")
            self.heating_layout_section.pack(fill=tk.X, pady=(0, 12))
            self.heating_layout_note.configure(
                text="separate erzeugt eine Excel pro Variante. combined erzeugt eine gemeinsame Excel fuer alle ausgewaehlten Varianten und Raeume."
            )
            return

        if prepare_active:
            return

        self.analysis_section.pack(fill=tk.X)

    def _set_time_view_buttons_visible(self, visible):
        buttons_visible = bool(self.heating_time_view_buttons_section.winfo_manager())
        if visible and not buttons_visible:
            self.heating_time_view_buttons_section.pack(
                side=tk.LEFT,
                fill=tk.BOTH,
                expand=True,
                padx=(0, 20),
                before=self.heating_view_detail_section,
            )
            return
        if not visible and buttons_visible:
            self.heating_time_view_buttons_section.pack_forget()

    def _update_comfort_options_for_analysis_level(self):
        allowed_values = self.comfort_allowed_by_level.get(
            self.analysis_level.get(),
            self.comfort_allowed_by_level["Analyse Raum"],
        )

        if (
            self.command.get() == "comfort"
            and self.comfort_type.get()
            and self.comfort_type.get() not in allowed_values
        ):
            self.comfort_type.set("")

        disabled_values = {value for value in self.comfort_type_widgets if value not in allowed_values}
        self._update_selection_button_group(
            self.comfort_type_widgets,
            self.comfort_type.get(),
            disabled_values=disabled_values,
        )

    def _update_heating_detail_fields(self):
        selected_view = self.heating_view.get()
        if self.command.get() == "plot-template":
            spec = get_plot_template_spec(self.plot_template.get())
            if spec is not None:
                selected_view = spec.view
            load_label = "Template-Zeitansicht"
        else:
            load_label = "Kuehlansicht" if self.command.get() == "cooling" else "Heizansicht"
        self.heating_month_container.pack_forget()
        self.heating_week_container.pack_forget()
        self.heating_day_container.pack_forget()

        month_index = MONTH_NAMES.index(self.heating_month.get())
        valid_days = [str(day) for day in range(1, MONTH_DAY_COUNTS[month_index] + 1)]
        self.heating_day_combo.configure(values=valid_days)
        if self.heating_day.get() not in valid_days:
            self.heating_day.set(valid_days[0])

        if not selected_view:
            self.heating_view_note.configure(text="Bitte waehlen Sie eine Zeitansicht.")
            return

        if selected_view == "month":
            self.heating_view_note.configure(
                text=f"Waehlt einen Monat fuer die stuendliche {load_label} mit Tages- und Stundenachse."
            )
            self.heating_month_container.pack(fill=tk.X)
            return

        if selected_view == "week":
            self.heating_view_note.configure(
                text=f"Geben Sie eine Kalenderwoche im Bereich 1 bis {MAX_CALENDAR_WEEK} ein. Die Achse zeigt die echten Tageszahlen dieser Woche."
            )
            self.heating_week_container.pack(fill=tk.X)
            return

        if selected_view == "day":
            self.heating_view_note.configure(text="Waehlt Monat und Tag fuer eine 24-Stunden-Ansicht.")
            self.heating_month_container.pack(fill=tk.X, pady=(0, 8))
            self.heating_day_container.pack(fill=tk.X)
            return

        if selected_view == "year":
            self.heating_view_note.configure(
                text="Die Jahresansicht zeigt Monatslabels zwischen den Grenzen und zusaetzlich eine Stunden-Skalierung."
            )
            return

        self.heating_view_note.configure(text="Die Maximalwert-Ansicht benoetigt keine zusaetzliche Auswahl.")

    def _update_variant_field(self):
        if not self.variant_names:
            return

        scope = self.analysis_scope.get()
        previous_scope = self.last_variant_scope
        state = resolve_variant_list_state(
            len(self.variant_names),
            scope,
            current_selection=self.variants_listbox.curselection(),
            previous_scope=previous_scope,
        )
        selectmode = tk.BROWSE if state.selectmode == "browse" else tk.MULTIPLE
        widget_state = tk.NORMAL if state.enabled else tk.DISABLED
        self.variants_listbox.configure(state=tk.NORMAL, selectmode=selectmode)
        self.variants_listbox.selection_clear(0, tk.END)
        for index in state.selected_indices:
            self.variants_listbox.selection_set(index)
        self.variants_listbox.configure(state=widget_state)
        self._update_variant_note_state(scope)
        self.last_variant_scope = scope

    def _update_variant_note_state(self, scope):
        if not self.variant_names:
            return

        if not scope:
            self.variant_note.configure(text="Bitte waehlen Sie zuerst den Analyseumfang.")
            return

        if self.command.get() == "prepare":
            if scope == "Alle Varianten":
                self.variant_note.configure(
                    text=f"Alle Input-Varianten aus {INPUT_DIR} sind aktiv und werden vorbereitet."
                )
                return

            if not self.variants_listbox.curselection():
                if scope == "Eine Variante":
                    self.variant_note.configure(
                        text="Es ist aktuell keine Input-Variante ausgewaehlt. Bitte waehlen Sie eine Variante."
                    )
                    return

                self.variant_note.configure(
                    text="Es ist aktuell keine Input-Variante ausgewaehlt. Bitte waehlen Sie mindestens eine Variante."
                )
                return

            if scope == "Eine Variante":
                self.variant_note.configure(
                    text="Eine Input-Variante ist aktiv. Es wird genau diese Variante vorbereitet."
                )
                return

            self.variant_note.configure(
                text="Mehrere Input-Varianten sind aktiv. Es werden nur die ausgewaehlten Varianten vorbereitet."
            )
            return

        if scope == "Alle Varianten":
            self.variant_note.configure(
                text=f"Alle Datenbank-Varianten sind aktiv. Die Variantenauswahl wird automatisch aus {DATENBANK_DIR} uebernommen."
            )
            return

        if not self.variants_listbox.curselection():
            if scope == "Eine Variante":
                self.variant_note.configure(
                    text="Es ist aktuell keine Variante ausgewaehlt. Bitte waehlen Sie eine Variante."
                )
                return

            self.variant_note.configure(
                text="Es ist aktuell keine Variante ausgewaehlt. Bitte waehlen Sie mindestens eine Variante."
            )
            return

        if scope == "Eine Variante":
            self.variant_note.configure(
                text="Eine Datenbank-Variante ist aktiv. Es kann genau eine Variante ausgewaehlt werden."
            )
            return

        self.variant_note.configure(
            text="Mehrere Datenbank-Varianten sind aktiv. Es koennen mehrere Varianten ausgewaehlt werden."
        )

    def _update_room_field(self):
        if self.command.get() == "plot-template":
            requires_single_room = template_requires_single_room(self.plot_template.get())
            selectmode = tk.BROWSE if requires_single_room else tk.MULTIPLE
            self.rooms_listbox.configure(state=tk.NORMAL, selectmode=selectmode)
            self._set_step_5_enabled(True)
            if not self.rooms_listbox.curselection():
                self.room_note.configure(text="Fuer plot-template ist aktuell kein Raum ausgewaehlt.")
                return
            if requires_single_room:
                self.room_note.configure(text="Dieses plot-template nutzt genau einen Raum fuer die Diagrammvorlage.")
                return
            self.room_note.configure(text="Dieses plot-template nutzt die ausgewaehlten Raeume fuer den Raumvergleich.")
            return

        if self.command.get() in {"heating", "cooling", "analyze_data", "all"}:
            self.rooms_listbox.configure(state=tk.NORMAL, selectmode=tk.MULTIPLE)
            self._set_step_5_enabled(True)
            if self.command.get() == "all":
                self._update_room_note_state("All")
                return
            self._update_room_note_state(
                "AnalyzeData"
                if self.command.get() == "analyze_data"
                else "Cooling"
                if self.command.get() == "cooling"
                else "Heating"
            )
            return

        level = self.analysis_level.get()
        if level == "Analyse Variante":
            self.rooms_listbox.selection_clear(0, tk.END)
            self.rooms_listbox.configure(state=tk.DISABLED, selectmode=tk.MULTIPLE)
            self._set_step_5_enabled(False)
            self._update_room_note_state(level)
            return

        self.rooms_listbox.configure(state=tk.NORMAL, selectmode=tk.MULTIPLE)
        self._set_step_5_enabled(True)
        self._update_room_note_state(level)

    def _set_step_5_enabled(self, enabled):
        card_bg = self.color_panel if enabled else self.color_panel_light
        header_bg = self.color_panel if enabled else self.color_panel_light
        number_bg = self.color_border
        listbox_bg = self.color_panel_light if enabled else self.color_panel
        listbox_fg = self.color_text if enabled else self.color_muted
        highlight_color = self.color_blue if enabled else self.color_border
        note_color = self.color_muted if enabled else "#8a929c"

        self.step_5_card.configure(bg=card_bg)
        self.step_5_card.step_header.configure(bg=header_bg)
        self.step_5_left.configure(bg=card_bg)
        self.step_5_right.configure(bg=card_bg)
        self.step_5_card.step_number_label.configure(bg=number_bg)
        self.step_5_card.step_heading.configure(background=header_bg, foreground=self.color_text)
        self.rooms_listbox.configure(
            bg=listbox_bg,
            fg=listbox_fg,
            disabledforeground=listbox_fg,
            highlightbackground=self.color_border,
            highlightcolor=highlight_color,
            selectbackground=self.color_blue,
            selectforeground="white",
        )
        self.room_note.configure(foreground=note_color)

    def _update_room_note_state(self, level):
        if level == "AnalyzeData":
            if not self.rooms_listbox.curselection():
                self.room_note.configure(
                    text="Fuer analyze_data ist aktuell kein Raum ausgewaehlt. Bitte waehlen Sie mindestens einen Raum."
                )
                return

            self.room_note.configure(
                text="analyze_data ist aktiv. Die ausgewaehlten Raeume werden direkt fuer die Auswertung verwendet."
            )
            return

        if level == "Heating":
            if not self.rooms_listbox.curselection():
                self.room_note.configure(
                    text="Fuer heating ist aktuell kein Raum ausgewaehlt. Bitte waehlen Sie mindestens einen Raum."
                )
                return

            self.room_note.configure(
                text="Heating ist aktiv. Die ausgewaehlten Raeume werden direkt fuer den Lauf verwendet."
            )
            return

        if level == "Cooling":
            if not self.rooms_listbox.curselection():
                self.room_note.configure(
                    text="Fuer cooling ist aktuell kein Raum ausgewaehlt. Bitte waehlen Sie mindestens einen Raum."
                )
                return

            self.room_note.configure(
                text="Cooling ist aktiv. Die ausgewaehlten Raeume werden direkt fuer den Lauf verwendet."
            )
            return

        if level == "All":
            if not self.rooms_listbox.curselection():
                self.room_note.configure(
                    text="Fuer all ist aktuell kein Raum ausgewaehlt. Bitte waehlen Sie mindestens einen Raum."
                )
                return

            self.room_note.configure(
                text="All ist aktiv. Die ausgewaehlten Raeume werden fuer Comfort-/Analyseuebersichten sowie Heating-/Cooling-Barplots und Jahresplots verwendet."
            )
            return

        if level == "Analyse Variante":
            self.room_note.configure(
                text="Analyse Variante ist aktiv. Die Raumauswahl ist deaktiviert; es werden automatisch alle Raeume verwendet."
            )
            return

        if not self.rooms_listbox.curselection():
            self.room_note.configure(
                text="Es ist aktuell kein Raum ausgewaehlt. Bitte waehlen Sie mindestens einen Raum."
            )
            return

        if level == "Analyse Raum":
            self.room_note.configure(
                text="Analyse Raum ist aktiv. Es koennen einzelne oder mehrere Raeume ausgewaehlt werden."
            )
            return

        self.room_note.configure(
            text="Analyse Variante ist aktiv. Waehlen Sie die Raeume bewusst aus; es wird nichts automatisch uebernommen."
        )

    def _handle_variant_selection_changed(self):
        if self.command.get() == "plot-template":
            self._update_variant_note_state(self.analysis_scope.get())
        else:
            self._update_variant_note_state(self.analysis_scope.get())
        self._refresh_overlay_catalog()
        self._update_step_summaries()

    def _handle_room_selection_changed(self):
        if self.command.get() == "plot-template":
            if template_requires_single_room(self.plot_template.get()):
                self.room_note.configure(text="Dieses plot-template nutzt genau einen Raum fuer die Diagrammvorlage.")
            else:
                self.room_note.configure(
                    text="Dieses plot-template nutzt die ausgewaehlten Raeume fuer den Raumvergleich."
                )
        else:
            self._update_room_note_state(self.analysis_level.get())
        self._refresh_overlay_catalog()
        self._update_step_summaries()

    def _refresh_overlay_catalog(self):
        if (
            self.command.get() != "plot-template"
            or not template_uses_overlay_options(self.plot_template.get())
            or not hasattr(self, "overlay_column_combo")
        ):
            return

        variant_name = None
        if self.variant_names:
            selected_indices = self.variants_listbox.curselection()
            if selected_indices:
                variant_name = self.variant_names[selected_indices[0]]

        room_name = None
        if self.rooms_listbox.size() > 0:
            selected_room_indices = self.rooms_listbox.curselection()
            if selected_room_indices:
                room_name = self.rooms_listbox.get(selected_room_indices[0])

        if not variant_name or not room_name:
            self.overlay_catalog = {"csv": [], "aux": []}
            self._refresh_overlay_column_options()
            return

        try:
            self.overlay_catalog = list_heating_year_overlay_sources(
                self.args.datenbank_dir,
                self.args.input_dir,
                variant_name,
                room_name,
                outdoor_column=self.plot_outdoor_column.get() or DEFAULT_OUTDOOR_COLUMN,
                fixed_overlays=self.fixed_plot_overlays,
            )
        except Exception:
            self.overlay_catalog = {"csv": [], "aux": []}
        self._refresh_overlay_column_options()

    def _refresh_overlay_column_options(self):
        if not hasattr(self, "overlay_column_combo"):
            return
        source = self.overlay_source.get()
        columns = self.overlay_catalog.get(source, [])
        self.overlay_column_combo.configure(values=columns)
        if columns and self.overlay_column.get() not in columns:
            self.overlay_column.set(columns[0])
            self._prefill_overlay_label()
        elif not columns:
            self.overlay_column.set("")

    def _prefill_overlay_label(self):
        if not self.overlay_label.get().strip():
            self.overlay_label.set(self.overlay_column.get())

    def _add_free_overlay_line(self):
        source = self.overlay_source.get()
        column = self.overlay_column.get().strip()
        axis = self.overlay_axis.get()
        label = self.overlay_label.get().strip() or column
        if source not in {"csv", "aux"} or axis not in {"heat", "temperature"} or not column:
            messagebox.showwarning("Warnung", "Bitte waehlen Sie Quelle, Spalte und Achse fuer die Datenlinie.")
            return
        if column not in self.overlay_catalog.get(source, []):
            messagebox.showwarning("Warnung", "Die gewaehlte Spalte ist fuer Variante/Raum aktuell nicht verfuegbar.")
            return
        if any(
            line["source"] == source and line["column"] == column and line["axis"] == axis
            for line in self.free_overlay_lines
        ):
            messagebox.showwarning("Warnung", "Diese Datenlinie ist bereits hinzugefuegt.")
            return

        self.free_overlay_lines.append(
            {
                "source": source,
                "column": column,
                "label": label,
                "axis": axis,
                "enabled": True,
            }
        )
        self.overlay_label.set("")
        self._sync_free_overlay_listbox()
        self._update_step_summaries()

    def _remove_selected_free_overlay_line(self):
        if not hasattr(self, "overlay_lines_listbox"):
            return
        selection = self.overlay_lines_listbox.curselection()
        if not selection:
            return
        del self.free_overlay_lines[selection[0]]
        self._sync_free_overlay_listbox()
        self._update_step_summaries()

    def _sync_free_overlay_listbox(self):
        if not hasattr(self, "overlay_lines_listbox"):
            return
        self.overlay_lines_listbox.delete(0, tk.END)
        for line in self.free_overlay_lines:
            axis_label = "Temperatur [°C]" if line["axis"] == "temperature" else "Leistung [W]"
            self.overlay_lines_listbox.insert(
                tk.END,
                f"{line['label']}  |  {line['source']}:{line['column']}  |  {axis_label}",
            )

    def _reset_fields(self):
        self.analysis_scope.set("")
        self.command.set("")
        self.prepare_export_format.set("")
        self.comfort_type.set("")
        self.analysis_level.set("")
        self.load_subcommand.set("")
        self.heating_mode.set("")
        self.heating_view.set("")
        self.heating_series_layout.set("")
        self.heating_month.set(MONTH_NAMES[0])
        self.heating_week.set("1")
        self.heating_day.set("1")
        self.plot_template.set(HEATING_YEAR_TEMPLATE)
        self.plot_setpoint_min.set(str(self.plot_template_defaults.get("setpoint_min", DEFAULT_SETPOINT_MIN)))
        self.plot_setpoint_max.set(str(self.plot_template_defaults.get("setpoint_max", DEFAULT_SETPOINT_MAX)))
        self.plot_temperature_ymin.set(
            str(self.plot_template_defaults.get("temperature_ymin", DEFAULT_TEMPERATURE_YMIN))
        )
        self.plot_temperature_ymax.set(
            str(self.plot_template_defaults.get("temperature_ymax", DEFAULT_TEMPERATURE_YMAX))
        )
        self.plot_outdoor_column.set(self.plot_template_defaults.get("outdoor_column", DEFAULT_OUTDOOR_COLUMN))
        self.plot_show_setpoint_band.set(False)
        self.plot_show_outdoor_temperature.set(False)
        self.plot_show_operative_temperature.set(False)
        self.overlay_source.set("")
        self.overlay_column.set("")
        self.overlay_label.set("")
        self.overlay_axis.set("")
        self.free_overlay_lines = []

        self.variants_listbox.selection_clear(0, tk.END)
        self.rooms_listbox.selection_clear(0, tk.END)

        self.selected_comfort_type = ""
        self.selected_prepare_export_format = ""
        self.selected_load_subcommand = ""
        self.selected_heating_mode = ""
        self.selected_heating_view = ""
        self.selected_heating_series_layout = ""
        self.selected_month = MONTH_NAMES[0]
        self.selected_week = 1
        self.selected_day = 1
        self.selected_plot_template_options = {}
        self._sync_free_overlay_listbox()

        self._update_dynamic_fields()
        self._activate_first_available_step()

    def _parse_heating_week(self):
        raw_value = self.heating_week.get().strip()
        if not raw_value:
            messagebox.showwarning("Warnung", "Bitte geben Sie eine Kalenderwoche ein.")
            return None
        if not raw_value.isdigit():
            messagebox.showwarning("Warnung", "Die Kalenderwoche muss eine ganze Zahl sein.")
            return None

        week_value = int(raw_value)
        if week_value < 1 or week_value > MAX_CALENDAR_WEEK:
            messagebox.showwarning(
                "Warnung",
                f"Bitte geben Sie eine Kalenderwoche zwischen 1 und {MAX_CALENDAR_WEEK} ein.",
            )
            return None
        return week_value

    def _parse_heating_day(self):
        raw_value = self.heating_day.get().strip()
        if not raw_value:
            messagebox.showwarning("Warnung", "Bitte waehlen Sie einen Tag.")
            return None
        if not raw_value.isdigit():
            messagebox.showwarning("Warnung", "Der Tag muss eine ganze Zahl sein.")
            return None

        day_value = int(raw_value)
        month_index = MONTH_NAMES.index(self.heating_month.get())
        max_days = MONTH_DAY_COUNTS[month_index]
        if day_value < 1 or day_value > max_days:
            messagebox.showwarning(
                "Warnung",
                f"Bitte waehlen Sie fuer {self.heating_month.get()} einen Tag zwischen 1 und {max_days}.",
            )
            return None
        return day_value

    def _parse_float_option(self, raw_value, label):
        raw_value = raw_value.strip()
        if not raw_value:
            messagebox.showwarning("Warnung", f"Bitte geben Sie einen Wert fuer {label} ein.")
            return None
        try:
            return float(raw_value.replace(",", "."))
        except ValueError:
            messagebox.showwarning("Warnung", f"{label} muss eine Zahl sein.")
            return None

    def _get_plot_template_options(self, variants, rooms):
        template = self.plot_template.get()
        spec = get_plot_template_spec(template)
        uses_overlay_options = template_uses_overlay_options(template)
        month = None
        week = None
        day = None

        if spec is not None and spec.view in {"month", "day"}:
            if self.heating_month.get() not in MONTH_NAMES:
                messagebox.showwarning("Warnung", "Bitte waehlen Sie einen gueltigen Monat.")
                return None
            month = self.heating_month.get()
        if spec is not None and spec.view == "week":
            week = self._parse_heating_week()
            if week is None:
                return None
        if spec is not None and spec.view == "day":
            day = self._parse_heating_day()
            if day is None:
                return None

        if uses_overlay_options and self.plot_show_setpoint_band.get():
            setpoint_min = self._parse_float_option(self.plot_setpoint_min.get(), "Sollwert min")
            if setpoint_min is None:
                return None
            setpoint_max = self._parse_float_option(self.plot_setpoint_max.get(), "Sollwert max")
            if setpoint_max is None:
                return None
        else:
            setpoint_min = self.plot_template_defaults.get("setpoint_min", DEFAULT_SETPOINT_MIN)
            setpoint_max = self.plot_template_defaults.get("setpoint_max", DEFAULT_SETPOINT_MAX)
        if uses_overlay_options:
            temperature_ymin = self._parse_float_option(self.plot_temperature_ymin.get(), "Temp.-Achse min")
            if temperature_ymin is None:
                return None
            temperature_ymax = self._parse_float_option(self.plot_temperature_ymax.get(), "Temp.-Achse max")
            if temperature_ymax is None:
                return None
        else:
            temperature_ymin = self.plot_template_defaults.get("temperature_ymin", DEFAULT_TEMPERATURE_YMIN)
            temperature_ymax = self.plot_template_defaults.get("temperature_ymax", DEFAULT_TEMPERATURE_YMAX)

        options = {
            "template": template,
            "setpoint_min": setpoint_min,
            "setpoint_max": setpoint_max,
            "temperature_ymin": temperature_ymin,
            "temperature_ymax": temperature_ymax,
            "outdoor_column": self.plot_outdoor_column.get().strip() or DEFAULT_OUTDOOR_COLUMN,
            "show_setpoint_band": self.plot_show_setpoint_band.get() if uses_overlay_options else False,
            "show_outdoor_temperature": self.plot_show_outdoor_temperature.get() if uses_overlay_options else False,
            "show_operative_temperature": self.plot_show_operative_temperature.get() if uses_overlay_options else False,
            "overlay_lines": [line.copy() for line in self.free_overlay_lines] if uses_overlay_options else [],
            "fixed_overlays": self.fixed_plot_overlays if uses_overlay_options else [],
            "month": month,
            "week": week,
            "day": day,
        }
        errors = validate_template_request(
            options["template"],
            variants,
            rooms,
            options["setpoint_min"],
            options["setpoint_max"],
            options["temperature_ymin"],
            options["temperature_ymax"],
            validate_setpoint_band=options["show_setpoint_band"],
            month=month,
            week=week,
            day=day,
        )
        if errors:
            messagebox.showwarning("Warnung", "\n".join(errors))
            return None
        return options

    def _get_selected_variants(self):
        if not self.variant_names:
            return []
        if self.analysis_scope.get() == "Alle Varianten":
            return self.variant_names.copy()
        if self.command.get() == "plot-template":
            selected_indices = self.variants_listbox.curselection()
            return [self.variant_names[index] for index in selected_indices]
        selected_indices = self.variants_listbox.curselection()
        return [self.variant_names[index] for index in selected_indices]

    def _get_selected_rooms(self):
        if self.command.get() == "prepare":
            return ROOMS.copy()
        if self.command.get() in {"heating", "cooling", "analyze_data", "all", "plot-template"}:
            selected_indices = self.rooms_listbox.curselection()
            return [self.rooms_listbox.get(index) for index in selected_indices]
        if self.analysis_level.get() == "Analyse Variante":
            return ROOMS.copy()
        selected_indices = self.rooms_listbox.curselection()
        return [self.rooms_listbox.get(index) for index in selected_indices]

    def _validate_variant_sources(self, steps, variants):
        if not variants:
            messagebox.showwarning("Warnung", "Bitte waehlen Sie mindestens eine Variante.")
            return False

        return True

    def _start_pipeline(self):
        if self.is_running_pipeline:
            return

        selected_command = self.command.get()
        if not selected_command:
            messagebox.showwarning("Warnung", "Bitte waehlen Sie einen gueltigen Befehl.")
            return

        if selected_command == "prepare" and not self.prepare_export_format.get():
            messagebox.showwarning("Warnung", "Bitte waehlen Sie ein Exportformat.")
            return

        if selected_command == "comfort":
            if not self.analysis_level.get():
                messagebox.showwarning("Warnung", "Bitte waehlen Sie eine Analyseebene.")
                return
            if not self.comfort_type.get():
                messagebox.showwarning("Warnung", "Bitte waehlen Sie einen Comfort-Unterbefehl.")
                return

        if selected_command == "analyze_data" and not self.heating_series_layout.get():
            messagebox.showwarning("Warnung", "Bitte waehlen Sie eine Excel-Ausgabe.")
            return

        if not self.analysis_scope.get():
            messagebox.showwarning("Warnung", "Bitte waehlen Sie den Analyseumfang.")
            return

        if selected_command == "comfort":
            comfort_settings = get_comfort_output_settings(self.comfort_type.get())
            steps = comfort_settings["steps"]
        else:
            steps = self.command_to_steps.get(selected_command, [])

        variants = self._get_selected_variants()
        rooms = self._get_selected_rooms()

        if not steps:
            messagebox.showwarning("Warnung", "Bitte waehlen Sie einen gueltigen Befehl.")
            return
        if not self._validate_variant_sources(steps, variants):
            return
        if not rooms:
            messagebox.showwarning("Warnung", "Bitte waehlen Sie mindestens einen Raum.")
            return
        selected_week = None
        selected_day = None
        plot_template_options = {}
        if selected_command == "plot-template":
            plot_template_options = self._get_plot_template_options(variants, rooms)
            if plot_template_options is None:
                return
        if selected_command in {"heating", "cooling"} and self.load_subcommand.get() not in {"bar", "timeline"}:
            messagebox.showwarning("Warnung", "Bitte waehlen Sie den Unterbefehl bar oder timeline.")
            return
        if selected_command in {"heating", "cooling"} and not self.heating_mode.get():
            messagebox.showwarning("Warnung", "Bitte waehlen Sie den Vergleichsmodus.")
            return
        if (
            selected_command in {"heating", "cooling"}
            and self.heating_mode.get() == "compare"
            and not self.heating_series_layout.get()
        ):
            messagebox.showwarning("Warnung", "Bitte waehlen Sie die Diagrammausgabe.")
            return

        uses_load_detail_options = (
            selected_command in {"heating", "cooling"} and self.load_subcommand.get() == "timeline"
        )
        if uses_load_detail_options:
            if self.heating_view.get() not in {"year", "month", "week", "day"}:
                messagebox.showwarning("Warnung", "Bitte waehlen Sie eine Zeitansicht.")
                return
            if self.heating_view.get() in {"month", "day"} and self.heating_month.get() not in MONTH_NAMES:
                messagebox.showwarning("Warnung", "Bitte waehlen Sie einen gueltigen Monat.")
                return
            if self.heating_view.get() == "week":
                selected_week = self._parse_heating_week()
                if selected_week is None:
                    return
            elif self.heating_view.get() == "day":
                selected_day = self._parse_heating_day()
                if selected_day is None:
                    return
            elif self.heating_view.get() == "month":
                selected_week = None

        self.selected_steps = steps
        self.selected_variants = variants
        self.selected_rooms = rooms
        self.selected_prepare_export_format = self.prepare_export_format.get()
        self.selected_load_subcommand = self.load_subcommand.get()
        self.selected_heating_mode = "single" if selected_command == "all" else self.heating_mode.get()
        if selected_command == "all":
            self.selected_heating_view = "year"
        elif selected_command in {"heating", "cooling"} and self.selected_load_subcommand == "bar":
            self.selected_heating_view = "bar"
        else:
            self.selected_heating_view = self.heating_view.get()
        self.selected_heating_series_layout = (
            "separate" if selected_command == "all" else self.heating_series_layout.get()
        )
        self.selected_month = self.heating_month.get()
        self.selected_week = selected_week if selected_week is not None else 1
        self.selected_day = selected_day if selected_day is not None else int(self.heating_day.get())
        self.selected_comfort_type = self.comfort_type.get()
        self.selected_plot_template_options = plot_template_options
        comfort_options = {}
        if selected_command == "comfort":
            comfort_options = get_comfort_output_settings(self.selected_comfort_type)

        prepare_options = {
            "export_format": self.selected_prepare_export_format,
        }
        heating_options = {
            "view": self.selected_heating_view,
            "month": self.selected_month,
            "week": self.selected_week if self.selected_heating_view == "week" else None,
            "day": self.selected_day if self.selected_heating_view == "day" else None,
            "series_layout": self.selected_heating_series_layout,
        }

        self.is_running_pipeline = True
        self.start_button.configure(state=tk.DISABLED)
        self.reset_button.configure(state=tk.DISABLED)
        self._create_analysis_log_window(selected_command)
        self._set_status(f"Pipeline läuft: {selected_command}")
        self._append_log(f"Starte Pipeline fuer Befehl: {selected_command}", clear=False)
        self.root.update_idletasks()

        self.pipeline_queue = queue.Queue()
        self.pipeline_thread = threading.Thread(
            target=self._run_pipeline_worker,
            args=(
                selected_command,
                steps,
                variants,
                rooms,
                self.selected_heating_mode,
                prepare_options,
                comfort_options,
                heating_options,
                plot_template_options,
            ),
            daemon=True,
        )
        self.pipeline_thread.start()
        self._schedule_pipeline_log_polling()


def run_gui_menu(args):
    """Legacy-Dialogfluss: GUI oeffnen und danach die Auswahl zurueckgeben."""
    root = tk.Tk()
    gui = PipelineGUI(root, args)
    root.mainloop()

    comfort_options = {}
    if gui.command.get() == "comfort":
        comfort_options = get_comfort_output_settings(gui.selected_comfort_type)

    prepare_options = {
        "export_format": gui.selected_prepare_export_format,
    }

    heating_options = {
        "view": gui.selected_heating_view,
        "month": gui.selected_month,
        "week": gui.selected_week if gui.selected_heating_view == "week" else None,
        "day": gui.selected_day if gui.selected_heating_view == "day" else None,
        "series_layout": gui.selected_heating_series_layout,
    }

    return (
        gui.selected_steps,
        gui.selected_variants,
        gui.selected_rooms,
        gui.selected_heating_mode,
        prepare_options,
        comfort_options,
        heating_options,
        gui.selected_plot_template_options,
    )
