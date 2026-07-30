#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import customtkinter as ctk
from pathlib import Path
import shutil
import webbrowser
import subprocess
import re
import platform
import threading

from profile_manager import ProfileManager
from settings_manager import SettingsManager
from launcher_core import LauncherCore
from ui_tabs import build_tabs

DEFAULT_VERSION = "1.21.1"
DEFAULT_USERNAME = "OfflinePlayer"
PURPLE = "#9B59B6"
PURPLE_DARK = "#6C3483"
PURPLE_LIGHT = "#A569BD"
BG_DARK = "#1E1E1E"
BG_FRAME = "#2D2D2D"
TEXT_LIGHT = "#E0E0E0"
TEXT_DIM = "#A0A0A0"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

class OpenLauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OpenLauncher")
        self.geometry("1200x750")
        self.minsize(1000, 650)
        self.configure(fg_color=BG_DARK)

        # Clear old log file at startup
        log_path = Path("launcher.log")
        if log_path.exists():
            try:
                log_path.unlink()
            except:
                pass

        self.workdir_var = tk.StringVar(value=os.path.join(os.getcwd(), "minecraft_offline"))
        self.profile_manager = ProfileManager(self.workdir_var.get())
        self.settings_manager = SettingsManager(self.workdir_var.get())

        self.current_profile = None
        self.build_ui()
        self.refresh_profiles()
        self.global_username_entry.delete(0, tk.END)
        self.global_username_entry.insert(0, self.settings_manager.get_global_username())

        # Store reference to launcher core for crash callbacks
        self.launcher_core = None

    def build_ui(self):
        # Top toolbar
        top_frame = ctk.CTkFrame(self, fg_color=BG_FRAME, corner_radius=12)
        top_frame.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(top_frame, text="Work Dir:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(10, 5))
        self.dir_entry = ctk.CTkEntry(top_frame, textvariable=self.workdir_var, width=280, corner_radius=8, fg_color=BG_DARK, text_color=TEXT_LIGHT)
        self.dir_entry.pack(side="left", padx=5, fill="x", expand=True)

        ctk.CTkButton(top_frame, text="Browse", width=80, height=30, corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.browse_workdir).pack(side="left", padx=5)

        ctk.CTkLabel(top_frame, text="Global Username:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(20, 5))
        self.global_username_entry = ctk.CTkEntry(top_frame, width=150, corner_radius=8, fg_color=BG_DARK, text_color=TEXT_LIGHT)
        self.global_username_entry.pack(side="left", padx=5)

        ctk.CTkButton(top_frame, text="Save", width=50, height=30, corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.save_global_username).pack(side="left", padx=5)
        ctk.CTkButton(top_frame, text="Refresh", width=70, height=30, corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.refresh_profiles).pack(side="left", padx=5)

        # Main row
        main_row = ctk.CTkFrame(self, fg_color="transparent")
        main_row.pack(fill="both", expand=True, padx=15, pady=10)

        # LEFT PANEL: Tabbed features
        left_frame = ctk.CTkFrame(main_row, fg_color=BG_FRAME, corner_radius=16)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=0)

        self.tabview = ctk.CTkTabview(left_frame, width=450, corner_radius=12, fg_color=BG_DARK, segmented_button_fg_color=BG_FRAME, segmented_button_selected_color=PURPLE, segmented_button_unselected_color=BG_DARK)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        # Add tabs
        self.tabview.add("Mods")
        self.tabview.add("Resource Packs")
        self.tabview.add("Worlds")
        self.tabview.add("Java")

        # Build UI tabs and get references
        self.ui_refs = build_tabs(self.tabview, self.profile_manager, self.workdir_var, self.log, self.refresh_profiles, self.get_selected_profile)

        # RIGHT PANEL: Profiles
        right_frame = ctk.CTkFrame(main_row, fg_color=BG_FRAME, corner_radius=16)
        right_frame.pack(side="right", fill="both", expand=False, padx=(0, 0))
        right_frame.configure(width=280)

        ctk.CTkLabel(right_frame, text="Profiles", font=ctk.CTkFont(size=15, weight="bold"), text_color=PURPLE_LIGHT).pack(pady=(10, 5), anchor="w", padx=15)

        self.profile_listbox = tk.Listbox(right_frame, bg=BG_DARK, fg=TEXT_LIGHT, selectbackground=PURPLE, selectforeground="white", font=("Segoe UI", 11), relief="flat", borderwidth=0, highlightthickness=0, activestyle="none")
        self.profile_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.profile_listbox.bind("<Double-Button-1>", self.launch_selected)
        self.profile_listbox.bind("<<ListboxSelect>>", self.on_profile_selected)

        action_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        action_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(action_frame, text="▶ Launch", height=36, corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=self.launch_selected).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(action_frame, text="＋ Add", height=36, corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.add_profile_dialog).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(action_frame, text="✎ Edit", height=36, corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.edit_profile_dialog).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(action_frame, text="✕ Delete", height=36, corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=self.delete_profile).pack(side="left", padx=2, expand=True, fill="x")

        # Bottom: progress and log
        progress_frame = ctk.CTkFrame(self, fg_color=BG_FRAME, corner_radius=12)
        progress_frame.pack(fill="x", padx=15, pady=(0, 5))

        self.progress_bar = ctk.CTkProgressBar(progress_frame, width=400, height=14, corner_radius=7, progress_color=PURPLE_LIGHT, fg_color=BG_DARK)
        self.progress_bar.pack(side="left", padx=(15, 10), fill="x", expand=True)
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(progress_frame, text="Ready", font=ctk.CTkFont(size=12), text_color=TEXT_DIM, width=120)
        self.progress_label.pack(side="right", padx=(10, 15))

        log_frame = ctk.CTkFrame(self, fg_color=BG_FRAME, corner_radius=16)
        log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        ctk.CTkLabel(log_frame, text="Log", font=ctk.CTkFont(size=14, weight="bold"), text_color=PURPLE_LIGHT).pack(anchor="w", padx=(15, 0), pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap="word", height=8, bg=BG_DARK, fg=TEXT_LIGHT, insertbackground="white", font=("Consolas", 10), relief="flat", borderwidth=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        self.log_text.tag_configure('INFO', foreground=TEXT_LIGHT)
        self.log_text.tag_configure('WARNING', foreground='#F1C40F')
        self.log_text.tag_configure('ERROR', foreground='#E74C3C')
        self.log_text.tag_configure('SUCCESS', foreground='#2ECC71')

        # Initialise launcher core
        try:
            self.launcher_core = LauncherCore(
                self.workdir_var.get(),
                self.profile_manager,
                self.settings_manager,
                self.log,
                self.update_progress
            )
        except Exception as e:
            self.log(f"Failed to initialise LauncherCore: {e}", "ERROR")
            messagebox.showerror("Error", f"Could not initialise launcher core:\n{e}")

    # ---------- Callbacks ----------
    def get_selected_profile(self):
        selection = self.profile_listbox.curselection()
        if not selection:
            return None
        name = self.profile_listbox.get(selection[0])
        if name == "No profiles. Click 'Add'.":
            return None
        return name

    def refresh_profiles(self):
        self.profile_manager = ProfileManager(self.workdir_var.get())
        self.profile_listbox.delete(0, tk.END)
        for name in self.profile_manager.get_profile_names():
            self.profile_listbox.insert(tk.END, name)
        if self.profile_listbox.size() == 0:
            self.profile_listbox.insert(tk.END, "No profiles. Click 'Add'.")
        if self.profile_listbox.size() > 0:
            self.profile_listbox.selection_set(0)
            self.on_profile_selected(None)

    def on_profile_selected(self, event):
        name = self.get_selected_profile()
        if name:
            self.current_profile = name
            self.update_ui_for_profile(name)

    def update_ui_for_profile(self, profile_name):
        if not profile_name:
            self.ui_refs["mods_listbox"].delete(0, tk.END)
            self.ui_refs["rp_listbox"].delete(0, tk.END)
            self.ui_refs["worlds_listbox"].delete(0, tk.END)
            self.ui_refs["memory_slider"].set(2048)
            self.ui_refs["memory_label"].configure(text="2048 MB")
            self.ui_refs["jvm_args_entry"].delete(0, tk.END)
            return
        profile = self.profile_manager.get_profile(profile_name)
        if not profile:
            return

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

    # ---------- Progress callback (handles crash events) ----------
    def update_progress(self, value, text):
        if isinstance(text, tuple) and text[0] == "crash":
            # Crash event from launcher core
            _, exit_code, instance_dir, crash_file = text
            self.after(0, lambda: self.show_crash_dialog(exit_code, instance_dir, crash_file))
            return
        if value is not None:
            self.progress_bar.set(value)
        if text:
            self.progress_label.configure(text=text)

    # ---------- Crash dialog ----------
    def show_crash_dialog(self, exit_code, instance_dir, crash_file):
        preview = ""
        if crash_file and os.path.exists(crash_file):
            with open(crash_file, "r", encoding="utf-8") as f:
                content = f.read()
                preview = content[:500] + ("..." if len(content) > 500 else "")

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
        elif exit_code == 1 and ("1.16.5" in str(instance_dir) or "1.17.1" in str(instance_dir)):
            suggestion = "For 1.16.5/1.17.1, try adding JVM flags: -Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true"
        ctk.CTkLabel(dialog, text=f"💡 {suggestion}", font=ctk.CTkFont(size=12), text_color="#F1C40F", wraplength=550).pack(pady=5)

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
        self.log_text.insert(tk.END, f"[{level}] {message}\n", level)
        self.log_text.see(tk.END)
        with open("launcher.log", "a", encoding="utf-8") as f:
            f.write(f"[{level}] {message}\n")

    # ---------- Top bar actions ----------
    def save_global_username(self):
        name = self.global_username_entry.get().strip()
        self.settings_manager.set_global_username(name)
        self.log(f"Global username set to '{name}'", "SUCCESS")
        messagebox.showinfo("Saved", f"Global username updated to '{name}'")

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
        self.settings_manager = SettingsManager(folder)
        self.refresh_profiles()
        self.global_username_entry.delete(0, tk.END)
        self.global_username_entry.insert(0, self.settings_manager.get_global_username())
        try:
            self.launcher_core = LauncherCore(
                folder,
                self.profile_manager,
                self.settings_manager,
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
        dialog.geometry("460x320")
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
        loader_menu = ctk.CTkComboBox(dialog, values=["None", "Fabric", "Quilt"], variable=loader_var, width=200)
        loader_menu.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        ctk.CTkLabel(dialog, text="Loader Version (optional):").grid(row=row, column=0, padx=15, pady=10, sticky="w")
        version_e = ctk.CTkEntry(dialog, width=200, corner_radius=8, placeholder_text="Leave blank for latest")
        version_e.grid(row=row, column=1, padx=5, pady=10, sticky="w")
        row += 1

        def do_add():
            n = name_e.get().strip()
            v = ver_e.get().strip()
            loader = loader_var.get()
            loader_ver = version_e.get().strip()
            if not n or not v:
                messagebox.showerror("Error", "Name and Version are required.")
                return
            if self.profile_manager.add_profile(n, v, loader, loader_ver):
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
        dialog.geometry("480x340")
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
        loader_menu = ctk.CTkComboBox(dialog, values=["None", "Fabric", "Quilt"], variable=loader_var, width=200)
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
            # Get required Java version
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

        def do_update():
            nn = name_e.get().strip()
            vv = ver_e.get().strip()
            loader = loader_var.get()
            loader_ver = version_e.get().strip()
            jj = java_e.get().strip()
            if not nn or not vv:
                messagebox.showerror("Error", "Name and Version required.")
                return
            if loader not in {"None", "Fabric", "Quilt"}:
                loader = "None"

            if nn != name:
                if self.profile_manager.add_profile(nn, vv, loader, loader_ver, mods=profile.get("mods", []), resource_packs=profile.get("resource_packs", []), jvm_args=profile.get("jvm_args", ""), memory=profile.get("memory", "2048")):
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
                if self.profile_manager.update_profile(name, version=vv, modloader=loader, modloader_version=loader_ver, java_path=jj):
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

    # ---------- FIXED: Launch method with fallback ----------
    def launch_selected(self, event=None):
        try:
            # Ensure launcher_core is initialised
            if self.launcher_core is None:
                self.log("LauncherCore not initialised – recreating.", "WARNING")
                self.launcher_core = LauncherCore(
                    self.workdir_var.get(),
                    self.profile_manager,
                    self.settings_manager,
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
            if modloader not in {"None", "Fabric", "Quilt"}:
                modloader = "None"
                self.profile_manager.update_profile(name, modloader=modloader)
                self.refresh_profiles()

            modloader_version = profile.get("modloader_version", "")
            if not version:
                messagebox.showerror("Error", "Profile missing version.")
                return

            username = self.settings_manager.get_global_username()
            if not username or not username.strip():
                username = DEFAULT_USERNAME

            self.launcher_core.launch(version, username, name, modloader, modloader_version)
        except Exception as e:
            import traceback
            self.log(f"Launch error: {traceback.format_exc()}", "ERROR")
            messagebox.showerror("Launch Error", str(e))

if __name__ == "__main__":
    app = OpenLauncherApp()
    app.mainloop()