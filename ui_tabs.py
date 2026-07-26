import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import customtkinter as ctk
from pathlib import Path
import shutil
import time
import os
import zipfile
from helpers import copy_file_with_retry

PURPLE = "#9B59B6"
PURPLE_DARK = "#6C3483"
PURPLE_LIGHT = "#A569BD"
BG_DARK = "#1E1E1E"
BG_FRAME = "#2D2D2D"
TEXT_LIGHT = "#E0E0E0"
TEXT_DIM = "#A0A0A0"

def build_tabs(tabview, profile_manager, workdir_var, log_func, refresh_callback, get_selected_profile):
    """Build all tabs and return references to UI elements that need dynamic updates."""
    ui_refs = {}

    # ----- MODS TAB -----
    mods_tab = tabview.tab("Mods")
    ctk.CTkLabel(mods_tab, text="Mod Manager", font=ctk.CTkFont(size=16, weight="bold"), text_color=PURPLE_LIGHT).pack(anchor="w", padx=10, pady=(10,5))
    mods_listbox = tk.Listbox(mods_tab, bg=BG_DARK, fg=TEXT_LIGHT, selectbackground=PURPLE, selectforeground="white", font=("Segoe UI", 11), relief="flat", borderwidth=0, highlightthickness=0, activestyle="none")
    mods_listbox.pack(fill="both", expand=True, padx=10, pady=5)

    def add_mod():
        profile_name = get_selected_profile()
        if not profile_name:
            messagebox.showinfo("No Profile", "Select a profile first.")
            return
        file_path = filedialog.askopenfilename(
            title="Select Mod JAR",
            filetypes=[("JAR files", "*.jar"), ("All files", "*.*")]
        )
        if not file_path:
            return
        instance_dir = Path(workdir_var.get()) / "instances" / profile_name / "mods"
        instance_dir.mkdir(parents=True, exist_ok=True)
        dest = instance_dir / os.path.basename(file_path)
        try:
            shutil.copy2(file_path, dest)
            profile = profile_manager.get_profile(profile_name)
            mods = profile.get("mods", [])
            mods.append(str(dest))
            profile_manager.update_profile(profile_name, mods=mods)
            refresh_callback()
            log_func(f"Added mod: {os.path.basename(file_path)}", "SUCCESS")
        except Exception as e:
            log_func(f"Failed to add mod: {e}", "ERROR")

    def remove_mod():
        profile_name = get_selected_profile()
        if not profile_name:
            return
        selection = mods_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        profile = profile_manager.get_profile(profile_name)
        mods = profile.get("mods", [])
        if idx < len(mods):
            removed = mods.pop(idx)
            profile_manager.update_profile(profile_name, mods=mods)
            refresh_callback()
            log_func(f"Removed mod: {os.path.basename(removed)}", "INFO")

    mod_btn_frame = ctk.CTkFrame(mods_tab, fg_color="transparent")
    mod_btn_frame.pack(fill="x", padx=10, pady=5)
    ctk.CTkButton(mod_btn_frame, text="Add Mod (JAR)", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=add_mod).pack(side="left", padx=2, expand=True, fill="x")
    ctk.CTkButton(mod_btn_frame, text="Remove Mod", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=remove_mod).pack(side="right", padx=2, expand=True, fill="x")
    ui_refs["mods_listbox"] = mods_listbox

    # ----- RESOURCE PACKS TAB -----
    rp_tab = tabview.tab("Resource Packs")
    ctk.CTkLabel(rp_tab, text="Resource Pack Selector", font=ctk.CTkFont(size=16, weight="bold"), text_color=PURPLE_LIGHT).pack(anchor="w", padx=10, pady=(10,5))
    rp_listbox = tk.Listbox(rp_tab, bg=BG_DARK, fg=TEXT_LIGHT, selectbackground=PURPLE, selectforeground="white", font=("Segoe UI", 11), relief="flat", borderwidth=0, highlightthickness=0, activestyle="none")
    rp_listbox.pack(fill="both", expand=True, padx=10, pady=5)

    def add_rp():
        profile_name = get_selected_profile()
        if not profile_name:
            return
        file_path = filedialog.askopenfilename(
            title="Select Resource Pack ZIP",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
        )
        if not file_path:
            return
        instance_dir = Path(workdir_var.get()) / "instances" / profile_name / "resourcepacks"
        instance_dir.mkdir(parents=True, exist_ok=True)
        dest = instance_dir / os.path.basename(file_path)
        try:
            shutil.copy2(file_path, dest)
            profile = profile_manager.get_profile(profile_name)
            rps = profile.get("resource_packs", [])
            rps.append(str(dest))
            profile_manager.update_profile(profile_name, resource_packs=rps)
            refresh_callback()
            log_func(f"Added resource pack: {os.path.basename(file_path)}", "SUCCESS")
        except Exception as e:
            log_func(f"Failed to add resource pack: {e}", "ERROR")

    def remove_rp():
        profile_name = get_selected_profile()
        if not profile_name:
            return
        selection = rp_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        profile = profile_manager.get_profile(profile_name)
        rps = profile.get("resource_packs", [])
        if idx < len(rps):
            removed = rps.pop(idx)
            profile_manager.update_profile(profile_name, resource_packs=rps)
            refresh_callback()
            log_func(f"Removed resource pack: {os.path.basename(removed)}", "INFO")

    rp_btn_frame = ctk.CTkFrame(rp_tab, fg_color="transparent")
    rp_btn_frame.pack(fill="x", padx=10, pady=5)
    ctk.CTkButton(rp_btn_frame, text="Add Resource Pack (ZIP)", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=add_rp).pack(side="left", padx=2, expand=True, fill="x")
    ctk.CTkButton(rp_btn_frame, text="Remove Pack", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=remove_rp).pack(side="right", padx=2, expand=True, fill="x")
    ui_refs["rp_listbox"] = rp_listbox

    # ----- WORLDS TAB -----
    worlds_tab = tabview.tab("Worlds")
    ctk.CTkLabel(worlds_tab, text="World Manager", font=ctk.CTkFont(size=16, weight="bold"), text_color=PURPLE_LIGHT).pack(anchor="w", padx=10, pady=(10,5))
    worlds_listbox = tk.Listbox(worlds_tab, bg=BG_DARK, fg=TEXT_LIGHT, selectbackground=PURPLE, selectforeground="white", font=("Segoe UI", 11), relief="flat", borderwidth=0, highlightthickness=0, activestyle="none")
    worlds_listbox.pack(fill="both", expand=True, padx=10, pady=5)

    def open_worlds_folder():
        profile_name = get_selected_profile()
        if not profile_name:
            return
        instance_dir = Path(workdir_var.get()) / "instances" / profile_name
        worlds_dir = instance_dir / "saves"
        worlds_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(worlds_dir)

    def backup_world():
        profile_name = get_selected_profile()
        if not profile_name:
            return
        selection = worlds_listbox.curselection()
        if not selection:
            messagebox.showinfo("Info", "Select a world to backup.")
            return
        world_name = worlds_listbox.get(selection[0])
        instance_dir = Path(workdir_var.get()) / "instances" / profile_name
        worlds_dir = instance_dir / "saves"
        world_path = worlds_dir / world_name
        if not world_path.exists():
            log_func(f"World folder not found: {world_name}", "ERROR")
            return
        backup_dir = instance_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_name = f"{world_name}_{time.strftime('%Y%m%d_%H%M%S')}.zip"
        backup_path = backup_dir / backup_name
        try:
            shutil.make_archive(str(backup_path.with_suffix('')), 'zip', world_path)
            log_func(f"Backup created: {backup_name}", "SUCCESS")
        except Exception as e:
            log_func(f"Backup failed: {e}", "ERROR")

    def restore_world():
        profile_name = get_selected_profile()
        if not profile_name:
            return
        backup_dir = Path(workdir_var.get()) / "instances" / profile_name / "backups"
        if not backup_dir.exists():
            messagebox.showinfo("No Backups", "No backups found.")
            return
        file_path = filedialog.askopenfilename(
            title="Select Backup ZIP",
            initialdir=backup_dir,
            filetypes=[("ZIP files", "*.zip")]
        )
        if not file_path:
            return
        instance_dir = Path(workdir_var.get()) / "instances" / profile_name
        worlds_dir = instance_dir / "saves"
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(worlds_dir)
            log_func(f"Restored world from {os.path.basename(file_path)}", "SUCCESS")
            refresh_callback()
        except Exception as e:
            log_func(f"Restore failed: {e}", "ERROR")

    world_btn_frame = ctk.CTkFrame(worlds_tab, fg_color="transparent")
    world_btn_frame.pack(fill="x", padx=10, pady=5)
    ctk.CTkButton(world_btn_frame, text="Open Worlds Folder", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=open_worlds_folder).pack(side="left", padx=2, expand=True, fill="x")
    ctk.CTkButton(world_btn_frame, text="Backup World", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=backup_world).pack(side="left", padx=2, expand=True, fill="x")
    ctk.CTkButton(world_btn_frame, text="Restore World", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=restore_world).pack(side="left", padx=2, expand=True, fill="x")
    ui_refs["worlds_listbox"] = worlds_listbox

    # ----- JAVA TAB -----
    java_tab = tabview.tab("Java")
    ctk.CTkLabel(java_tab, text="Java Settings", font=ctk.CTkFont(size=16, weight="bold"), text_color=PURPLE_LIGHT).pack(anchor="w", padx=10, pady=(10,5))

    ctk.CTkLabel(java_tab, text="Memory (MB):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=10, pady=(5,0))
    memory_slider = ctk.CTkSlider(java_tab, from_=512, to=8192, number_of_steps=15)
    memory_slider.set(2048)
    memory_slider.pack(fill="x", padx=10, pady=5)
    memory_label = ctk.CTkLabel(java_tab, text="2048 MB", font=ctk.CTkFont(size=12), text_color=TEXT_DIM)
    memory_label.pack(anchor="w", padx=10, pady=(0,5))

    def update_memory_label(value):
        mem = int(value)
        memory_label.configure(text=f"{mem} MB")
    memory_slider.configure(command=update_memory_label)

    ctk.CTkLabel(java_tab, text="Custom JVM Arguments:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=10, pady=(10,0))
    jvm_args_entry = ctk.CTkEntry(java_tab, width=400, corner_radius=8, fg_color=BG_DARK, text_color=TEXT_LIGHT)
    jvm_args_entry.pack(fill="x", padx=10, pady=5)
    jvm_args_entry.insert(0, "")

    def apply_java_settings():
        profile_name = get_selected_profile()
        if not profile_name:
            return
        memory = int(memory_slider.get())
        jvm_args = jvm_args_entry.get().strip()
        profile_manager.update_profile(profile_name, memory=str(memory), jvm_args=jvm_args)
        log_func(f"Java settings applied to '{profile_name}' (Memory: {memory}MB)", "SUCCESS")

    ctk.CTkButton(java_tab, text="Apply Java Settings", corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK, command=apply_java_settings).pack(pady=10, padx=10, fill="x")

    ui_refs["memory_slider"] = memory_slider
    ui_refs["memory_label"] = memory_label
    ui_refs["jvm_args_entry"] = jvm_args_entry

    return ui_refs