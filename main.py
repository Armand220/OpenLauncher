#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import customtkinter as ctk
from pathlib import Path
import shutil
import webbrowser
import subprocess
import re
import platform
import threading
import datetime

from profile_manager import ProfileManager
from account_manager import AccountManager
from launcher_core import LauncherCore
from ui_tabs import build_tabs

DEFAULT_VERSION = "1.21.1"
DEFAULT_USERNAME = "OfflinePlayer"
PURPLE       = "#9B59B6"
PURPLE_DARK  = "#6C3483"
PURPLE_LIGHT = "#A569BD"
PURPLE_GLOW  = "#C39BD3"
BG_DARK      = "#141414"
BG_FRAME     = "#1E1E1E"
BG_CARD      = "#252525"
BORDER_COLOR = "#333333"
TEXT_LIGHT   = "#E8E8E8"
TEXT_DIM     = "#888888"
ACCENT_GREEN = "#2ECC71"
ACCENT_RED   = "#E74C3C"
ACCENT_YELLOW= "#F1C40F"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

class OpenLauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OpenLauncher v6.0")
        self.geometry("1280x780")
        self.minsize(1050, 680)
        self.configure(fg_color=BG_DARK)

        # Animation state
        self._launch_btn = None
        self._launch_animating = False
        self._pulse_step = 0
        self._bounce_active = False
        self._flash_counter = 0

        # Fade-in on startup
        self.attributes("-alpha", 0.0)
        self.after(50, self._fade_in)

        # Per-session log file -- keep last 5, prune older ones
        import glob as _glob
        _ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = Path(f"launcher_{_ts}.log")
        _old_logs = sorted(_glob.glob("launcher_????????_??????.log"))
        while len(_old_logs) >= 5:
            try:
                Path(_old_logs.pop(0)).unlink()
            except Exception:
                pass

        import sys
        if getattr(sys, "frozen", False):
            _script_dir = os.path.dirname(sys.executable)
        else:
            _script_dir = os.path.dirname(os.path.abspath(__file__))
        self.workdir_var = tk.StringVar(value=os.path.join(_script_dir, "minecraft_offline"))
        self.profile_manager = ProfileManager(self.workdir_var.get())
        self.account_manager = AccountManager(self.workdir_var.get())

        self.current_profile = None
        self.build_ui()
        self.refresh_profiles()
        self.refresh_accounts()

        self.launcher_core = None
        self._dot_breathing = False
        self._dot_breathe_step = 0
        self.after(1200, self._start_dot_breathe)

    def build_ui(self):
        # ── Header bar ──────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=BG_FRAME, corner_radius=0, height=52)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        self._title_label = ctk.CTkLabel(
            header, text="  ",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=PURPLE_GLOW
        )
        self._title_label.pack(side="left", padx=(18, 6), pady=10)
        self._version_label = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_DIM
        )
        self._version_label.pack(side="left", pady=16)
        # Typewriter animation starts after fade-in
        self.after(400, lambda: self._typewriter("  OpenLauncher", 0))

        # Workdir row inside header
        ctk.CTkLabel(header, text="Work Dir:", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left", padx=(30, 4))
        self.dir_entry = ctk.CTkEntry(
            header, textvariable=self.workdir_var, width=300,
            corner_radius=8, fg_color=BG_DARK, text_color=TEXT_LIGHT,
            border_color=BORDER_COLOR, border_width=1
        )
        self.dir_entry.pack(side="left", padx=4, fill="x", expand=True)
        ctk.CTkButton(header, text="Browse", width=80, height=30, corner_radius=8,
                      fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=self.browse_workdir).pack(side="left", padx=(4, 2))
        ctk.CTkButton(header, text="Refresh", width=76, height=30, corner_radius=8,
                      fg_color=BG_CARD, hover_color=BORDER_COLOR,
                      command=self.refresh_profiles).pack(side="left", padx=(2, 14))

        # Animated accent line under header
        self._accent_canvas = tk.Canvas(self, height=3, highlightthickness=0, bg=PURPLE_DARK)
        self._accent_canvas.pack(fill="x")
        self._accent_step = 0
        self.after(600, self._animate_accent_line)

        # ── Main content row ─────────────────────────────────────────────────────
        main_row = ctk.CTkFrame(self, fg_color="transparent")
        main_row.pack(fill="both", expand=True, padx=14, pady=(10, 6))

        # LEFT PANEL
        left_frame = ctk.CTkFrame(main_row, fg_color=BG_FRAME, corner_radius=14,
                                  border_color=BORDER_COLOR, border_width=1)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.tabview = ctk.CTkTabview(
            left_frame, width=450, corner_radius=10,
            fg_color=BG_CARD,
            segmented_button_fg_color=BG_FRAME,
            segmented_button_selected_color=PURPLE,
            segmented_button_selected_hover_color=PURPLE_DARK,
            segmented_button_unselected_color=BG_FRAME,
            segmented_button_unselected_hover_color=BG_CARD,
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tabview.add("Mods")
        self.tabview.add("Resource Packs")
        self.tabview.add("Worlds")
        self.tabview.add("Java")
        self.tabview.add("Accounts")

        self.ui_refs = build_tabs(self.tabview, self.profile_manager, self.workdir_var,
                                   self.log, self.refresh_profiles, self.get_selected_profile)
        self.build_accounts_tab(self.tabview.tab("Accounts"))

        # RIGHT PANEL
        right_frame = ctk.CTkFrame(main_row, fg_color=BG_FRAME, corner_radius=14,
                                   border_color=BORDER_COLOR, border_width=1)
        right_frame.pack(side="right", fill="both", expand=True)

        # Profile panel header
        prof_hdr = ctk.CTkFrame(right_frame, fg_color=BG_CARD, corner_radius=10)
        prof_hdr.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(prof_hdr, text="Profiles",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=PURPLE_GLOW).pack(side="left", padx=12, pady=8)

        self.profile_count_label = ctk.CTkLabel(
            prof_hdr, text="0 profiles",
            font=ctk.CTkFont(size=11), text_color=TEXT_DIM)
        self.profile_count_label.pack(side="right", padx=12)

        # Profile listbox with a subtle inner border
        lb_frame = ctk.CTkFrame(right_frame, fg_color=BG_DARK, corner_radius=10,
                                border_color=BORDER_COLOR, border_width=1)
        lb_frame.pack(fill="both", expand=True, padx=10, pady=6)

        self.profile_listbox = tk.Listbox(
            lb_frame,
            bg=BG_DARK, fg=TEXT_LIGHT,
            selectbackground=PURPLE, selectforeground="white",
            font=("Segoe UI", 11),
            relief="flat", borderwidth=0, highlightthickness=0,
            activestyle="none", cursor="hand2"
        )
        self.profile_listbox.pack(fill="both", expand=True, padx=6, pady=6)
        self.profile_listbox.bind("<Double-Button-1>", self.launch_selected)
        self.profile_listbox.bind("<<ListboxSelect>>", self.on_profile_selected)

        # Profile details strip
        self._profile_details_label = ctk.CTkLabel(
            right_frame, text="", font=ctk.CTkFont(size=10),
            text_color=TEXT_DIM, anchor="w")
        self._profile_details_label.pack(fill="x", padx=16, pady=(0, 2))

        # Action buttons -- row 1: Launch + Stop
        action_row1 = ctk.CTkFrame(right_frame, fg_color="transparent")
        action_row1.pack(fill="x", padx=10, pady=(0, 2))

        self._launch_btn = ctk.CTkButton(
            action_row1, text="  Launch", height=40, corner_radius=10,
            fg_color=PURPLE, hover_color=PURPLE_DARK,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_launch_click)
        self._launch_btn.pack(side="left", padx=(0, 2), expand=True, fill="x")

        self._stop_btn = ctk.CTkButton(
            action_row1, text="Stop", height=40, corner_radius=10,
            fg_color="#3a1a1a", hover_color="#5a2a2a", text_color="#e08080",
            font=ctk.CTkFont(size=12),
            state="disabled",
            command=self._on_stop_click)
        self._stop_btn.pack(side="left", padx=(2, 0), expand=True, fill="x")

        # Action buttons -- row 2: Add + Edit + Delete
        action_row2 = ctk.CTkFrame(right_frame, fg_color="transparent")
        action_row2.pack(fill="x", padx=10, pady=(0, 2))

        ctk.CTkButton(action_row2, text="Add", height=34, corner_radius=10,
                      fg_color=BG_CARD, hover_color=BORDER_COLOR, text_color=TEXT_LIGHT,
                      font=ctk.CTkFont(size=12),
                      command=self.add_profile_dialog).pack(side="left", padx=(0, 2), expand=True, fill="x")
        ctk.CTkButton(action_row2, text="Edit", height=34, corner_radius=10,
                      fg_color=BG_CARD, hover_color=BORDER_COLOR, text_color=TEXT_LIGHT,
                      font=ctk.CTkFont(size=12),
                      command=self.edit_profile_dialog).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(action_row2, text="Delete", height=34, corner_radius=10,
                      fg_color="#3a1a1a", hover_color="#5a2a2a", text_color="#e08080",
                      font=ctk.CTkFont(size=12),
                      command=self.delete_profile).pack(side="left", padx=(2, 0), expand=True, fill="x")

        repair_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        repair_frame.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkButton(repair_frame, text="Repair Instance", height=28, corner_radius=8,
                      fg_color=BG_CARD, hover_color=BORDER_COLOR, text_color=TEXT_DIM,
                      font=ctk.CTkFont(size=11),
                      command=self._on_repair_click).pack(fill="x")

        # ── Progress bar (inside right panel, above console) ─────────────────────
        progress_frame = ctk.CTkFrame(right_frame, fg_color=BG_CARD, corner_radius=10)
        progress_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.progress_label = ctk.CTkLabel(
            progress_frame, text="Ready",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=PURPLE_LIGHT, width=80)
        self.progress_label.pack(side="left", padx=(10, 4), pady=6)

        self.progress_bar = ctk.CTkProgressBar(
            progress_frame, height=10, corner_radius=5,
            progress_color=PURPLE, fg_color=BG_DARK)
        self.progress_bar.pack(side="left", padx=4, fill="x", expand=True, pady=6)
        self.progress_bar.set(0)

        self._progress_pct_label = ctk.CTkLabel(
            progress_frame, text="", width=38,
            font=ctk.CTkFont(size=10), text_color=TEXT_DIM)
        self._progress_pct_label.pack(side="right", padx=(0, 8))

        # ── Log panel ────────────────────────────────────────────────────────────
        log_frame = ctk.CTkFrame(self, fg_color=BG_FRAME, corner_radius=14,
                                  border_color=BORDER_COLOR, border_width=1)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        log_hdr = ctk.CTkFrame(log_frame, fg_color=BG_CARD, corner_radius=10)
        log_hdr.pack(fill="x", padx=8, pady=(8, 0))
        ctk.CTkLabel(log_hdr, text="Console",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=PURPLE_LIGHT).pack(side="left", padx=10, pady=5)
        self._log_status_dot = ctk.CTkLabel(log_hdr, text="●", text_color=TEXT_DIM,
                                             font=ctk.CTkFont(size=10))
        self._log_status_dot.pack(side="right", padx=10)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap="word", height=7,
            bg="#0e0e0e", fg=TEXT_LIGHT,
            insertbackground="white",
            font=("Consolas", 10), relief="flat", borderwidth=0,
            selectbackground=PURPLE_DARK, selectforeground="white"
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.log_text.tag_configure("INFO",    foreground=TEXT_LIGHT)
        self.log_text.tag_configure("DEBUG",   foreground=TEXT_DIM)
        self.log_text.tag_configure("WARNING", foreground=ACCENT_YELLOW)
        self.log_text.tag_configure("ERROR",   foreground=ACCENT_RED)
        self.log_text.tag_configure("SUCCESS", foreground=ACCENT_GREEN)
        self.log_text.tag_configure("FLASH",   foreground=PURPLE_GLOW)

        # Initialise launcher core
        try:
            self.launcher_core = LauncherCore(
                self.workdir_var.get(),
                self.profile_manager,
                self.account_manager,
                self.log,
                self.update_progress
            )
        except Exception as e:
            self.log(f"Failed to initialise LauncherCore: {e}", "ERROR")
            messagebox.showerror("Error", f"Could not initialise launcher core:\n{e}")

    # ── Typewriter title ─────────────────────────────────────────────────────
    def _typewriter(self, full_text, idx):
        if not hasattr(self, "_title_label"):
            return
        self._title_label.configure(text=full_text[:idx + 1])
        if idx + 1 < len(full_text):
            self.after(55, lambda: self._typewriter(full_text, idx + 1))
        else:
            # Show version badge after title finishes
            self.after(120, lambda: self._version_label.configure(text="v6.0"))

    # ── Animated accent line (sweeping highlight) ─────────────────────────────
    def _animate_accent_line(self):
        if not hasattr(self, "_accent_canvas"):
            return
        try:
            w = self._accent_canvas.winfo_width()
            if w < 2:
                self.after(100, self._animate_accent_line)
                return
            self._accent_canvas.delete("all")
            # Draw base
            self._accent_canvas.configure(bg=PURPLE_DARK)
            # Sweeping bright segment
            pos = (self._accent_step % 120) / 120.0
            cx = int(pos * w)
            hw = int(w * 0.18)
            x0, x1 = max(0, cx - hw), min(w, cx + hw)
            self._accent_canvas.create_rectangle(x0, 0, x1, 3, fill=PURPLE_GLOW, outline="")
            self._accent_step += 1
        except Exception:
            return
        self.after(22, self._animate_accent_line)

    # ── Idle status-dot breathing ────────────────────────────────────────────
    def _start_dot_breathe(self):
        self._dot_breathe_step = 0
        self._dot_breathing = True
        self._do_dot_breathe()

    def _stop_dot_breathe(self):
        self._dot_breathing = False

    def _do_dot_breathe(self):
        if not getattr(self, "_dot_breathing", False):
            return
        if not hasattr(self, "_log_status_dot"):
            return
        # Sine-wave interpolation between dim and purple
        import math
        t = (math.sin(self._dot_breathe_step * 0.12) + 1) / 2
        color = self._lerp_color(TEXT_DIM, PURPLE_LIGHT, t)
        try:
            self._log_status_dot.configure(text_color=color)
        except Exception:
            return
        self._dot_breathe_step += 1
        self.after(40, self._do_dot_breathe)


    # ── Profile list selection flash ─────────────────────────────────────────
    def _flash_profile_selection(self):
        """Briefly highlight selected profile row with a bright bg then settle."""
        colors = [PURPLE_GLOW, PURPLE_LIGHT, PURPLE, PURPLE]
        def _step(i):
            if i >= len(colors):
                return
            try:
                self.profile_listbox.configure(selectbackground=colors[i])
            except Exception:
                return
            self.after(90, lambda: _step(i + 1))
        _step(0)

    # ── Startup fade-in ──────────────────────────────────────────────────────
    def _fade_in(self, alpha=0.0):
        alpha = min(alpha + 0.07, 1.0)
        self.attributes("-alpha", alpha)
        if alpha < 1.0:
            self.after(18, lambda: self._fade_in(alpha))

    # ── Launch button pulse ──────────────────────────────────────────────────
    def _on_launch_click(self):
        self._start_launch_pulse()
        self._start_bounce()
        if hasattr(self, "_stop_btn"):
            self._stop_btn.configure(state="normal")
        name = self.get_selected_profile()
        if name:
            self.title(f"OpenLauncher v6.0  --  Playing: {name}")
        self.launch_selected()

    def _on_stop_click(self):
        if self.launcher_core:
            self.launcher_core.stop()
        if hasattr(self, "_stop_btn"):
            self._stop_btn.configure(state="disabled")

    def _on_repair_click(self):
        name = self.get_selected_profile()
        if not name:
            return
        profile = self.profile_manager.get_profile(name)
        if not profile:
            return
        if not messagebox.askyesno("Repair Instance",
                f"Re-download the client JAR and libraries for '{name}'?\n\n"
                "Saves, mods, and configs will not be touched."):
            return
        if self.launcher_core:
            self._start_bounce()
            self.launcher_core.repair_instance(profile.get("version", ""), name)

    def _start_launch_pulse(self):
        self._launch_animating = True
        self._pulse_step = 0
        self._animate_launch_btn()

    def _animate_launch_btn(self):
        if not self._launch_animating or self._launch_btn is None:
            return
        # Alternate between light and dark purple rapidly for a flash feel
        colors = [PURPLE_GLOW, PURPLE_DARK, PURPLE_GLOW, PURPLE_DARK,
                  PURPLE,      PURPLE_DARK, PURPLE_GLOW, PURPLE_DARK,
                  PURPLE_GLOW, PURPLE_DARK, PURPLE,      PURPLE_DARK]
        color = colors[self._pulse_step % len(colors)]
        try:
            self._launch_btn.configure(fg_color=color)
        except Exception:
            return
        self._pulse_step += 1
        if self._pulse_step < len(colors):
            self.after(120, self._animate_launch_btn)
        else:
            self._launch_animating = False
            try:
                self._launch_btn.configure(fg_color=PURPLE)
            except Exception:
                pass

    # ── Indeterminate progress bar ────────────────────────────────────────────
    def _start_bounce(self):
        if self._bounce_active:
            return
        self._bounce_active = True
        self._stop_dot_breathe()
        try:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        except Exception:
            pass

    def _stop_bounce(self):
        self._bounce_active = False
        try:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)
            if hasattr(self, "_progress_pct_label"):
                self._progress_pct_label.configure(text="")
        except Exception:
            pass
        if hasattr(self, "_stop_btn"):
            try:
                self._stop_btn.configure(state="disabled")
            except Exception:
                pass
        try:
            self.title("OpenLauncher v6.0")
        except Exception:
            pass
        self._start_dot_breathe()

    # ---------- Accounts tab ----------
    def build_accounts_tab(self, parent):
        ctk.CTkLabel(parent, text="Account Manager", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=PURPLE_GLOW).pack(anchor="w", padx=10, pady=(10, 5))

        self.accounts_listbox = tk.Listbox(
            parent, bg=BG_DARK, fg=TEXT_LIGHT,
            selectbackground=PURPLE, selectforeground="white",
            font=("Segoe UI", 11), relief="flat", borderwidth=0,
            highlightthickness=0, activestyle="none", cursor="hand2")
        self.accounts_listbox.pack(fill="both", expand=True, padx=10, pady=5)
        self.accounts_listbox.bind("<<ListboxSelect>>", self.on_account_selected)

        # --- Skin selection frame ---
        skin_frame = ctk.CTkFrame(parent, fg_color="transparent")
        skin_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(skin_frame, text="Skin:", font=ctk.CTkFont(size=12)).pack(side="left", padx=5)
        self.skin_label = ctk.CTkLabel(skin_frame, text="None selected", text_color=TEXT_DIM, width=250, anchor="w")
        self.skin_label.pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(skin_frame, text="Select Skin (PNG)", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.select_skin).pack(side="right", padx=2)
        ctk.CTkButton(skin_frame, text="Clear Skin", corner_radius=8, fg_color="#555", hover_color="#777", command=self.clear_skin).pack(side="right", padx=2)

        # --- Account action buttons ---
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btn_frame, text="Add Account", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.add_account_dialog).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="Remove Account", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.remove_account).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="Rename Account", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.rename_account_dialog).pack(side="left", padx=2, expand=True, fill="x")

        self.refresh_accounts()

    def on_account_selected(self, event):
        selection = self.accounts_listbox.curselection()
        if not selection:
            return
        name = self.accounts_listbox.get(selection[0])
        if name.startswith("No accounts"):
            return
        self.update_skin_display(name)

    def update_skin_display(self, account_name):
        if not account_name:
            self.skin_label.configure(text="None selected")
            return
        skin_path = self.account_manager.get_skin(account_name)
        if skin_path and os.path.exists(skin_path):
            self.skin_label.configure(text=os.path.basename(skin_path), text_color=TEXT_LIGHT)
        else:
            self.skin_label.configure(text="None selected", text_color=TEXT_DIM)

    def select_skin(self):
        selection = self.accounts_listbox.curselection()
        if not selection:
            messagebox.showinfo("No Account", "Select an account first.")
            return
        name = self.accounts_listbox.get(selection[0])
        if name.startswith("No accounts"):
            return

        file_path = filedialog.askopenfilename(
            title="Select Skin PNG",
            filetypes=[("PNG images", "*.png"), ("All files", "*.*")]
        )
        if not file_path:
            return

        # Basic validation: check PNG signature
        try:
            with open(file_path, "rb") as f:
                header = f.read(8)
                if header != b'\x89PNG\r\n\x1a\n':
                    messagebox.showerror("Invalid File", "The selected file is not a valid PNG image.")
                    return
        except Exception as e:
            messagebox.showerror("Error", f"Cannot read file: {e}")
            return

        # Copy to a dedicated skins folder under the workdir
        skin_root = Path(self.workdir_var.get()) / "accounts" / "skins"
        skin_root.mkdir(parents=True, exist_ok=True)
        # Sanitise account name for filename
        safe_name = "".join(c for c in name if c.isalnum() or c in "._-")
        dest = skin_root / f"{safe_name}.png"
        try:
            shutil.copy2(file_path, dest)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy skin: {e}")
            return

        if self.account_manager.set_skin(name, str(dest)):
            self.refresh_accounts()  # refresh list to update internal state
            self.update_skin_display(name)
            self.log(f"Skin set for account '{name}'", "SUCCESS")
        else:
            messagebox.showerror("Error", "Could not update account record.")

    def clear_skin(self):
        selection = self.accounts_listbox.curselection()
        if not selection:
            return
        name = self.accounts_listbox.get(selection[0])
        if name.startswith("No accounts"):
            return
        if messagebox.askyesno("Clear Skin", f"Remove the stored skin for '{name}'?"):
            if self.account_manager.set_skin(name, None):
                self.refresh_accounts()
                self.update_skin_display(name)
                self.log(f"Skin cleared for account '{name}'", "INFO")

    def refresh_accounts(self):
        self.account_manager = AccountManager(self.workdir_var.get())
        self.accounts_listbox.delete(0, tk.END)
        for acc in self.account_manager.get_account_names():
            self.accounts_listbox.insert(tk.END, acc)
        if self.accounts_listbox.size() == 0:
            self.accounts_listbox.insert(tk.END, "No accounts. Click 'Add Account'.")
        else:
            # Auto-select first account and update skin display
            self.accounts_listbox.selection_set(0)
            self.on_account_selected(None)

    def add_account_dialog(self):
        name = ctk.CTkInputDialog(title="Add Account", text="Enter account name (username):").get_input()
        if not name:
            return
        if self.account_manager.add_account(name):
            self.refresh_accounts()
            self.log(f"Account '{name}' added.", "SUCCESS")
        else:
            messagebox.showerror("Error", f"Account '{name}' already exists.")

    def remove_account(self):
        selection = self.accounts_listbox.curselection()
        if not selection:
            return
        name = self.accounts_listbox.get(selection[0])
        if name == "No accounts. Click 'Add Account'.":
            return
        if messagebox.askyesno("Confirm", f"Remove account '{name}'?"):
            self.account_manager.remove_account(name)
            self.refresh_accounts()
            self.log(f"Account '{name}' removed.", "INFO")

    def rename_account_dialog(self):
        selection = self.accounts_listbox.curselection()
        if not selection:
            return
        old_name = self.accounts_listbox.get(selection[0])
        if old_name == "No accounts. Click 'Add Account'.":
            return
        new_name = ctk.CTkInputDialog(title="Rename Account", text=f"Rename '{old_name}' to:").get_input()
        if not new_name or new_name == old_name:
            return
        if self.account_manager.rename_account(old_name, new_name):
            self.refresh_accounts()
            self.log(f"Account renamed from '{old_name}' to '{new_name}'.", "SUCCESS")
        else:
            messagebox.showerror("Error", "Rename failed.")

    # ---------- Profile list handling ----------
    def get_selected_profile(self):
        selection = self.profile_listbox.curselection()
        if not selection:
            return self.current_profile
        name = self.profile_listbox.get(selection[0]).strip()
        if name in ("No profiles. Click 'Add'.", ""):
            return None
        return name

    def refresh_profiles(self):
        self.profile_manager = ProfileManager(self.workdir_var.get())
        self.profile_listbox.delete(0, tk.END)
        names = self.profile_manager.get_profile_names()
        for i, name in enumerate(names):
            self.profile_listbox.insert(tk.END, f"  {name}")
            prof = self.profile_manager.get_profile(name)
            if prof and self._version_warning(prof.get("version", "")):
                self.profile_listbox.itemconfig(i, fg=ACCENT_YELLOW)
        if self.profile_listbox.size() == 0:
            self.profile_listbox.insert(tk.END, "  No profiles. Click 'Add'.")
        if self.profile_listbox.size() > 0:
            self.profile_listbox.selection_set(0)
            self.on_profile_selected(None)
        if hasattr(self, "profile_count_label"):
            n = len(names)
            self.profile_count_label.configure(text=f"{n} profile{'s' if n != 1 else ''}")

    def on_profile_selected(self, event):
        name = self.get_selected_profile()
        if name:
            self.current_profile = name
            self.update_ui_for_profile(name)
            self._flash_profile_selection()
        else:
            self.update_ui_for_profile(None)

    def update_ui_for_profile(self, profile_name):
        if not profile_name:
            self.ui_refs["mods_listbox"].delete(0, tk.END)
            self.ui_refs["rp_listbox"].delete(0, tk.END)
            self.ui_refs["worlds_listbox"].delete(0, tk.END)
            self.ui_refs["memory_slider"].set(2048)
            self.ui_refs["memory_label"].configure(text="2048 MB")
            self.ui_refs["jvm_args_entry"].delete(0, tk.END)
            if hasattr(self, "_profile_details_label"):
                self._profile_details_label.configure(text="")
            return
        profile = self.profile_manager.get_profile(profile_name)
        if not profile:
            return

        # Details strip
        if hasattr(self, "_profile_details_label"):
            version = profile.get("version", "")
            playtime = int(profile.get("play_time_seconds", 0))
            notes = profile.get("notes", "").strip()
            warn = self._version_warning(version)
            parts = []
            if version:
                parts.append(f"v{version}" + ("  ⚠ " + warn if warn else ""))
            if playtime > 0:
                parts.append(self._format_playtime(playtime) + " played")
            if notes:
                parts.append(f'"{notes}"')
            self._profile_details_label.configure(
                text="  " + "   |   ".join(parts) if parts else "",
                text_color=ACCENT_YELLOW if warn else TEXT_DIM)

        self.ui_refs["mods_listbox"].delete(0, tk.END)
        for mod in profile.get("mods", []):
            self.ui_refs["mods_listbox"].insert(tk.END, os.path.basename(mod))

        self.ui_refs["rp_listbox"].delete(0, tk.END)
        for rp in profile.get("resource_packs", []):
            self.ui_refs["rp_listbox"].insert(tk.END, os.path.basename(rp))

        self.ui_refs["worlds_listbox"].delete(0, tk.END)
        instance_dir = Path(self.workdir_var.get()) / "instances" / profile_name
        worlds_dir = instance_dir / "saves"
        if worlds_dir.exists():
            for world_dir in worlds_dir.iterdir():
                if world_dir.is_dir():
                    self.ui_refs["worlds_listbox"].insert(tk.END, world_dir.name)

        memory = int(profile.get("memory", "2048"))
        self.ui_refs["memory_slider"].set(memory)
        self.ui_refs["memory_label"].configure(text=f"{memory} MB")
        self.ui_refs["jvm_args_entry"].delete(0, tk.END)
        self.ui_refs["jvm_args_entry"].insert(0, profile.get("jvm_args", ""))

    # ---------- Version warning ----------
    @staticmethod
    def _version_warning(version):
        if version in ("1.16.5", "1.17.1"):
            return "Known LWJGL/OpenGL instability"
        try:
            parts = version.split(".")
            if int(parts[0]) == 1 and int(parts[1]) < 9:
                return "Very old version -- may have compatibility issues"
        except Exception:
            pass
        return None

    @staticmethod
    def _format_playtime(seconds):
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"

    # ---------- Progress callback ----------
    def update_progress(self, value, text):
        if isinstance(text, tuple) and text[0] == "crash":
            _, exit_code, instance_dir, crash_file = text
            self.after(0, lambda: self._stop_bounce())
            self.after(0, lambda: self.show_crash_dialog(exit_code, instance_dir, crash_file))
            return
        # Stop bounce when returning to idle
        if value == 0 and text == "Ready":
            self.after(0, self._stop_bounce)
        if value is not None and not self._bounce_active:
            self.progress_bar.set(value)
            if hasattr(self, "_progress_pct_label"):
                pct = int(value * 100)
                self._progress_pct_label.configure(text=f"{pct}%" if pct > 0 else "")
        if text:
            self.progress_label.configure(text=text)

    def show_crash_dialog(self, exit_code, instance_dir, crash_file):
        preview = ""
        if crash_file and os.path.exists(crash_file):
            with open(crash_file, "r", encoding="utf-8") as f:
                content = f.read()
                preview = content[:500] + ("..." if len(content) > 500 else "")

        # Determine the MC version from the profile so suggestions are accurate
        profile_name = Path(instance_dir).name if instance_dir else ""
        mc_version = ""
        if profile_name and self.profile_manager:
            prof = self.profile_manager.get_profile(profile_name)
            if prof:
                mc_version = prof.get("version", "")

        dialog = ctk.CTkToplevel(self)
        dialog.title("Minecraft Crashed")
        dialog.geometry("600x400")
        dialog.minsize(500, 300)
        dialog.configure(fg_color=BG_DARK)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Minecraft crashed unexpectedly.", font=ctk.CTkFont(size=16, weight="bold"), text_color="#E74C3C").pack(pady=(10, 5))
        ctk.CTkLabel(dialog, text=f"Exit code: {exit_code}", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack()

        suggestion = "Check the log for more details."
        if exit_code == -1073741819:
            suggestion = "This crash is often caused by graphics driver issues. Please update your GPU drivers."
        elif mc_version in ("1.16.5", "1.17.1"):
            suggestion = "For 1.16.5/1.17.1, try adding JVM flags: -Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true"
        ctk.CTkLabel(dialog, text=f"Suggestion: {suggestion}", font=ctk.CTkFont(size=12), text_color="#F1C40F", wraplength=550).pack(pady=5)

        log_frame = ctk.CTkFrame(dialog, fg_color=BG_FRAME, corner_radius=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        log_text = scrolledtext.ScrolledText(log_frame, wrap="word", height=8, bg=BG_DARK, fg=TEXT_LIGHT, insertbackground="white", font=("Consolas", 10), relief="flat", borderwidth=0)
        log_text.pack(fill="both", expand=True, padx=5, pady=5)
        log_text.insert("1.0", preview)
        log_text.configure(state="disabled")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=10)

        def copy_log():
            if crash_file and os.path.exists(crash_file):
                with open(crash_file, "r", encoding="utf-8") as f:
                    self.clipboard_clear()
                    self.clipboard_append(f.read())
                    self.update()
                messagebox.showinfo("Copied", "Crash log copied to clipboard.")
            else:
                messagebox.showerror("Error", "Log file not found.")

        def open_folder():
            if instance_dir and os.path.exists(instance_dir):
                os.startfile(instance_dir)

        ctk.CTkButton(btn_frame, text="Copy Log", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=copy_log).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="Open Log Folder", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=open_folder).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="Close", corner_radius=8, fg_color=PURPLE_DARK, hover_color=PURPLE_DARK, command=dialog.destroy).pack(side="right", padx=2, expand=True, fill="x")

    # ---------- Logging ----------
    def log(self, message, level="INFO"):
        # Insert with a unique flash tag so we can animate this line
        self._flash_counter += 1
        flash_tag = f"flash_{self._flash_counter}"
        level_colors = {"INFO": TEXT_LIGHT, "DEBUG": TEXT_DIM, "WARNING": ACCENT_YELLOW,
                        "ERROR": ACCENT_RED, "SUCCESS": ACCENT_GREEN}
        glow_color  = {"INFO": "#ffffff", "DEBUG": PURPLE_LIGHT, "WARNING": "#ffe57f",
                        "ERROR": "#ff8888", "SUCCESS": "#7fffc0"}.get(level, "#ffffff")
        final_color = level_colors.get(level, TEXT_LIGHT)

        self.log_text.insert(tk.END, f"[{level}] {message}\n", (level, flash_tag))
        self.log_text.tag_configure(flash_tag, foreground=glow_color)
        self.log_text.see(tk.END)

        # Fade the flash tag back to the normal level colour over ~400ms
        self._fade_log_tag(flash_tag, glow_color, final_color, steps=8)

        # Flash the console status dot
        if hasattr(self, "_log_status_dot"):
            dot_color = {"ERROR": ACCENT_RED, "WARNING": ACCENT_YELLOW,
                         "SUCCESS": ACCENT_GREEN}.get(level, PURPLE_LIGHT)
            self._log_status_dot.configure(text_color=dot_color)
            self.after(600, lambda: self._log_status_dot.configure(text_color=TEXT_DIM)
                       if hasattr(self, "_log_status_dot") else None)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(f"[{level}] {message}\n")

    def _fade_log_tag(self, tag, start_hex, end_hex, steps, step=0):
        """Interpolate a text tag colour from start_hex to end_hex over `steps` frames."""
        if step > steps:
            try:
                self.log_text.tag_configure(tag, foreground=end_hex)
                self.log_text.tag_delete(tag)
            except Exception:
                pass
            return
        t = step / steps
        color = self._lerp_color(start_hex, end_hex, t)
        try:
            self.log_text.tag_configure(tag, foreground=color)
        except Exception:
            return
        self.after(50, lambda: self._fade_log_tag(tag, start_hex, end_hex, steps, step + 1))

    @staticmethod
    def _lerp_color(hex_a, hex_b, t):
        """Linear interpolation between two hex colours."""
        def parse(h):
            h = h.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r1, g1, b1 = parse(hex_a)
        r2, g2, b2 = parse(hex_b)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ---------- Top bar actions ----------
    def browse_workdir(self):
        folder = filedialog.askdirectory(title="Select Minecraft work directory")
        if not folder:
            return
        current = self.workdir_var.get()
        if current != folder:
            result = messagebox.askyesno(
                "Change Work Directory",
                f"Are you sure you want to switch from:\n\n{current}\n\nto:\n\n{folder}\n\n"
                "Your current profiles and instances will NOT be visible in this session.\n"
                "They will remain on disk and you can switch back to see them again.",
                icon='warning'
            )
            if not result:
                return
        self.workdir_var.set(folder)
        self.profile_manager = ProfileManager(folder)
        self.account_manager = AccountManager(folder)
        self.refresh_profiles()
        self.refresh_accounts()
        try:
            self.launcher_core = LauncherCore(
                folder,
                self.profile_manager,
                self.account_manager,
                self.log,
                self.update_progress
            )
        except Exception as e:
            self.log(f"Failed to reinitialise LauncherCore: {e}", "ERROR")
            messagebox.showerror("Error", f"Could not initialise launcher core:\n{e}")
        self.log(f"Work directory changed to: {folder}", "INFO")

    # ---------- Profile management ----------
    def add_profile_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Profile")
        dialog.geometry("500x380")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG_DARK)
        dialog.grab_set()

        row = 0
        ctk.CTkLabel(dialog, text="Profile Name:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        name_e = ctk.CTkEntry(dialog, width=250, corner_radius=8)
        name_e.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Minecraft Version:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        ver_e = ctk.CTkEntry(dialog, width=250, corner_radius=8)
        ver_e.insert(0, DEFAULT_VERSION)
        ver_e.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Mod Loader:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        loader_var = tk.StringVar(value="None")
        loader_menu = ctk.CTkComboBox(dialog, values=["None", "Fabric", "Quilt", "Forge"], variable=loader_var, width=200)
        loader_menu.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Loader Version (optional):").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        version_e = ctk.CTkEntry(dialog, width=200, corner_radius=8, placeholder_text="Leave blank for latest")
        version_e.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Account:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        account_var = tk.StringVar(value="Default")
        account_names = self.account_manager.get_account_names()
        account_menu = ctk.CTkComboBox(dialog, values=["Default"] + account_names, variable=account_var, width=200)
        account_menu.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Notes:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        notes_e = ctk.CTkEntry(dialog, width=250, corner_radius=8, placeholder_text="Optional note...")
        notes_e.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        def do_add():
            n = name_e.get().strip()
            v = ver_e.get().strip()
            loader = loader_var.get()
            loader_ver = version_e.get().strip()
            account = account_var.get()
            notes = notes_e.get().strip()
            if account == "Default":
                account = None
            if not n or not v:
                messagebox.showerror("Error", "Name and Version are required.")
                return
            if self.profile_manager.add_profile(n, v, loader, loader_ver, account=account, notes=notes):
                self.refresh_profiles()
                dialog.destroy()
                self.log(f"Profile '{n}' added with loader {loader}.", "SUCCESS")
            else:
                messagebox.showerror("Error", f"Profile '{n}' already exists.")

        ctk.CTkButton(dialog, text="Add", command=do_add, fg_color=PURPLE, hover_color=PURPLE_DARK, corner_radius=8).grid(row=row, column=0, columnspan=2, pady=15)

    def edit_profile_dialog(self):
        name = self.get_selected_profile()
        if not name:
            return
        profile = self.profile_manager.get_profile(name)
        if not profile:
            return

        current_loader = profile.get("modloader", "None")
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Edit Profile: {name}")
        dialog.geometry("520x430")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG_DARK)
        dialog.grab_set()

        dialog.grid_columnconfigure(0, weight=0)
        dialog.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(dialog, text="Profile Name:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        name_e = ctk.CTkEntry(dialog, width=250, corner_radius=8)
        name_e.insert(0, name)
        name_e.grid(row=row, column=1, padx=5, pady=10, sticky="ew")
        row += 1

        ctk.CTkLabel(dialog, text="Minecraft Version:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        ver_e = ctk.CTkEntry(dialog, width=250, corner_radius=8)
        ver_e.insert(0, profile.get("version", DEFAULT_VERSION))
        ver_e.grid(row=row, column=1, padx=5, pady=10, sticky="ew")
        row += 1

        ctk.CTkLabel(dialog, text="Mod Loader:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        loader_var = tk.StringVar(value=current_loader)
        loader_menu = ctk.CTkComboBox(dialog, values=["None", "Fabric", "Quilt", "Forge"], variable=loader_var, width=200)
        loader_menu.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Loader Version (optional):").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        version_e = ctk.CTkEntry(dialog, width=200, corner_radius=8)
        version_e.insert(0, profile.get("modloader_version", ""))
        version_e.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Java Path (optional):").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        java_e = ctk.CTkEntry(dialog, corner_radius=8)
        java_e.insert(0, profile.get("java_path", ""))
        java_e.grid(row=row, column=1, padx=5, pady=10, sticky="ew")

        def browse_java():
            p = filedialog.askopenfilename(title="Select java", filetypes=[("Java", "java.exe"), ("Java", "java")])
            if not p:
                return
            mc_version = ver_e.get().strip()
            required_major = self._get_required_java_version(mc_version)
            try:
                startupinfo = None
                creationflags = 0
                if platform.system() == "Windows":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    creationflags = subprocess.CREATE_NO_WINDOW
                result = subprocess.run(
                    [p, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    startupinfo=startupinfo,
                    creationflags=creationflags
                )
                output = result.stderr + result.stdout
                match = re.search(r'version "(\d+)\.', output) or re.search(r'version "(\d+)-', output)
                if match:
                    major_ver = int(match.group(1))
                    if major_ver == 1 and "1.8" in output:
                        major_ver = 8
                    if (required_major == 8 and (major_ver == 1 or major_ver == 8)) or (required_major > 8 and major_ver >= required_major):
                        pass
                    else:
                        ans = messagebox.askyesno(
                            "Java Version Mismatch",
                            f"The selected Java version ({major_ver}) does not meet the required version for Minecraft {mc_version} (requires {required_major}).\n\n"
                            "Using an incompatible Java version may cause the game to crash.\n"
                            "Do you still want to use this Java executable?",
                            icon='warning'
                        )
                        if not ans:
                            return
                else:
                    ans = messagebox.askyesno(
                        "Unknown Java Version",
                        "Could not determine the version of the selected Java executable.\n"
                        "Using an incompatible version may cause issues.\n"
                        "Do you still want to use this Java executable?",
                        icon='warning'
                    )
                    if not ans:
                        return
            except Exception as e:
                messagebox.showerror("Error", f"Failed to check Java version: {e}")
                return

            java_e.delete(0, tk.END)
            java_e.insert(0, p)

        ctk.CTkButton(dialog, text="Browse", width=70, height=28, corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=browse_java).grid(row=row, column=2, padx=5, pady=10)
        row += 1

        ctk.CTkLabel(dialog, text="Account:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        account_names = self.account_manager.get_account_names()
        account_var = tk.StringVar(value=profile.get("account") or "Default")
        account_menu = ctk.CTkComboBox(dialog, values=["Default"] + account_names, variable=account_var, width=200)
        account_menu.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Notes:").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        notes_e_edit = ctk.CTkEntry(dialog, corner_radius=8, placeholder_text="Optional note...")
        notes_e_edit.insert(0, profile.get("notes", ""))
        notes_e_edit.grid(row=row, column=1, padx=5, pady=10, sticky="ew")
        row += 1

        def do_update():
            nn = name_e.get().strip()
            vv = ver_e.get().strip()
            loader = loader_var.get()
            loader_ver = version_e.get().strip()
            jj = java_e.get().strip()
            account = account_var.get()
            notes = notes_e_edit.get().strip()
            if account == "Default":
                account = None
            if not nn or not vv:
                messagebox.showerror("Error", "Name and Version required.")
                return
            if loader not in {"None", "Fabric", "Quilt", "Forge"}:
                loader = "None"

            if nn != name:
                if self.profile_manager.add_profile(nn, vv, loader, loader_ver, mods=profile.get("mods", []), resource_packs=profile.get("resource_packs", []), jvm_args=profile.get("jvm_args", ""), memory=profile.get("memory", "2048"), account=account, notes=notes):
                    if jj:
                        self.profile_manager.update_profile(nn, java_path=jj)
                    self.profile_manager.delete_profile(name)
                    self.refresh_profiles()
                    dialog.destroy()
                    self.log(f"Profile renamed to '{nn}'.", "SUCCESS")
                    return
                else:
                    messagebox.showerror("Error", f"Could not rename to '{nn}'. The name may already exist.")
                    return
            else:
                if self.profile_manager.update_profile(name, version=vv, modloader=loader, modloader_version=loader_ver, java_path=jj, account=account, notes=notes):
                    self.refresh_profiles()
                    dialog.destroy()
                    self.log(f"Profile '{name}' updated.", "SUCCESS")
                    return
                else:
                    messagebox.showerror("Error", "Update failed.")
                    return

        ctk.CTkButton(dialog, text="Update", command=do_update, fg_color=PURPLE, hover_color=PURPLE_DARK, corner_radius=8).grid(row=row, column=0, columnspan=3, pady=15)

    def _get_required_java_version(self, mc_version):
        import requests
        try:
            resp = requests.get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json", timeout=10)
            resp.raise_for_status()
            manifest = resp.json()
            version_info = None
            for v in manifest["versions"]:
                if v["id"] == mc_version:
                    version_info = v
                    break
            if not version_info:
                return 8
            resp = requests.get(version_info["url"], timeout=10)
            resp.raise_for_status()
            version_json = resp.json()
            return version_json.get("javaVersion", {}).get("majorVersion", 8)
        except:
            return 8

    def delete_profile(self):
        name = self.get_selected_profile()
        if not name:
            return
        if messagebox.askyesno("Confirm", f"Delete profile '{name}'?"):
            delete_files = messagebox.askyesno(
                "Delete Instance Files",
                f"Also delete the instance folder for '{name}'?\n"
                "This will remove all mods, saves, and configurations."
            )
            instance_dir = Path(self.workdir_var.get()) / "instances" / name
            if self.profile_manager.delete_profile(name):
                if delete_files and instance_dir.exists():
                    try:
                        shutil.rmtree(instance_dir)
                        self.log(f"Instance folder deleted: {instance_dir}", "INFO")
                    except Exception as e:
                        self.log(f"Failed to delete instance folder: {e}", "ERROR")
                        messagebox.showerror("Error", f"Could not delete instance folder:\n{e}")
                self.refresh_profiles()
                self.update_ui_for_profile(None)
                self.log(f"Profile '{name}' deleted.", "SUCCESS")
            else:
                messagebox.showerror("Error", "Delete failed.")

    def launch_selected(self, event=None):
        try:
            if self.launcher_core is None:
                self.log("LauncherCore not initialised – recreating.", "WARNING")
                self.launcher_core = LauncherCore(
                    self.workdir_var.get(),
                    self.profile_manager,
                    self.account_manager,
                    self.log,
                    self.update_progress
                )
                if self.launcher_core is None:
                    messagebox.showerror("Error", "Could not initialise launcher core.")
                    return

            name = self.get_selected_profile()
            if not name:
                return
            profile = self.profile_manager.get_profile(name)
            if not profile:
                return

            version = profile.get("version")
            modloader = profile.get("modloader", "None")
            if modloader not in {"None", "Fabric", "Quilt", "Forge"}:
                modloader = "None"
                self.profile_manager.update_profile(name, modloader=modloader)
                self.refresh_profiles()

            modloader_version = profile.get("modloader_version", "")
            if not version:
                messagebox.showerror("Error", "Profile missing version.")
                return

            profile_account = profile.get("account")
            if profile_account:
                username = profile_account
            else:
                username = DEFAULT_USERNAME

            self.launcher_core.launch(version, username, name, modloader, modloader_version)
        except Exception as e:
            import traceback
            self.log(f"Launch error: {traceback.format_exc()}", "ERROR")
            messagebox.showerror("Launch Error", str(e))

if __name__ == "__main__":
    app = OpenLauncherApp()
    app.mainloop()