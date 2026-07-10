import os
import sys
import json
import subprocess
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import customtkinter as ctk
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re
import platform
import shutil
import webbrowser
import zipfile
import glob
import uuid

LOADER_REGISTRY = {
    "None": {
        "display": "None (Vanilla)",
        "downloader": None,
        "main_class_override": None,
    },
    "Fabric": {
        "display": "Fabric",
        "downloader": "download_fabric",
        "main_class_override": "net.fabricmc.loader.impl.launch.knot.KnotClient",
    },
    "Quilt": {
        "display": "Quilt",
        "downloader": "download_quilt",
        "main_class_override": "org.quiltmc.loader.impl.launch.knot.KnotClient",
    },
}

VALID_LOADER_NAMES = set(LOADER_REGISTRY.keys())
LOADER_CHOICES = list(LOADER_REGISTRY.keys())

DEFAULT_VERSION = "1.21.1"
DEFAULT_USERNAME = "OfflinePlayer"
PROFILES_FILE = "profiles.json"
SETTINGS_FILE = "settings.json"
MAX_WORKERS = 20
CHUNK_SIZE = 128 * 1024
REQUEST_RETRIES = 3

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

PURPLE = "#9B59B6"
PURPLE_DARK = "#6C3483"
PURPLE_LIGHT = "#A569BD"
BG_DARK = "#1E1E1E"
BG_FRAME = "#2D2D2D"
TEXT_LIGHT = "#E0E0E0"
TEXT_DIM = "#A0A0A0"

class SplashScreen(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.overrideredirect(True)
        self.configure(fg_color=BG_DARK)

        width, height = 520, 320
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        self.container = ctk.CTkFrame(self, corner_radius=20, fg_color=BG_FRAME)
        self.container.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            self.container, text="OpenLauncher",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=PURPLE_LIGHT
        ).pack(pady=(40, 5))

        ctk.CTkLabel(
            self.container, text="Minecraft Offline Launcher",
            font=ctk.CTkFont(size=14), text_color=TEXT_DIM
        ).pack()

        self.progress = ctk.CTkProgressBar(
            self.container, width=350, height=12, corner_radius=6,
            progress_color=PURPLE_LIGHT, fg_color=BG_DARK
        )
        self.progress.pack(pady=(40, 20))
        self.progress.set(0)

        self.status = ctk.CTkLabel(
            self.container, text="Loading modules...",
            font=ctk.CTkFont(size=12), text_color=TEXT_DIM
        )
        self.status.pack()

        self.step = 0
        self.animate()

    def animate(self):
        self.step += 2
        if self.step <= 100:
            self.progress.set(self.step / 100)
            msgs = ["Loading modules...", "Initializing GUI...",
                    "Preparing profiles...", "Almost ready..."]
            idx = min(self.step // 25, 3)
            self.status.configure(text=msgs[idx])
            self.after(20, self.animate)
        else:
            self.destroy()
            self.master.deiconify()
            self.master.lift()

class SettingsManager:
    def __init__(self, workdir):
        self.workdir = Path(workdir)
        self.settings_path = self.workdir / SETTINGS_FILE
        self.settings = self.load_settings()

    def load_settings(self):
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_settings(self):
        with open(self.settings_path, "w") as f:
            json.dump(self.settings, f, indent=2)

    def get_global_username(self):
        return self.settings.get("global_username", "")

    def set_global_username(self, username):
        self.settings["global_username"] = username.strip()
        self.save_settings()

class ProfileManager:
    def __init__(self, workdir):
        self.workdir = Path(workdir)
        self.profiles_path = self.workdir / PROFILES_FILE
        self.profiles = self.load_profiles()
        (self.workdir / "instances").mkdir(parents=True, exist_ok=True)

    def load_profiles(self):
        if self.profiles_path.exists():
            try:
                with open(self.profiles_path, "r") as f:
                    data = json.load(f)
                modified = False
                for name, prof in data.items():
                    loader = prof.get("modloader", "None")
                    if loader not in VALID_LOADER_NAMES:
                        prof["modloader"] = "None"
                        modified = True
                if modified:
                    with open(self.profiles_path, "w") as f:
                        json.dump(data, f, indent=2)
                return data
            except:
                return {}
        return {}

    def save_profiles(self):
        for name, prof in self.profiles.items():
            if prof.get("modloader") not in VALID_LOADER_NAMES:
                prof["modloader"] = "None"
        with open(self.profiles_path, "w") as f:
            json.dump(self.profiles, f, indent=2)

    def get_profile_names(self):
        return list(self.profiles.keys())

    def get_profile(self, name):
        return self.profiles.get(name, {})

    def add_profile(self, name, version, modloader="None", modloader_version=""):
        if name in self.profiles:
            return False
        if modloader not in VALID_LOADER_NAMES:
            modloader = "None"
        self.profiles[name] = {
            "version": version,
            "modloader": modloader,
            "modloader_version": modloader_version
        }
        self.save_profiles()
        (self.workdir / "instances" / name).mkdir(parents=True, exist_ok=True)
        return True

    def delete_profile(self, name):
        if name in self.profiles:
            del self.profiles[name]
            self.save_profiles()
            return True
        return False

    def update_profile(self, name, version=None, modloader=None, modloader_version=None, java_path=None):
        if name not in self.profiles:
            return False
        if version:
            self.profiles[name]["version"] = version
        if modloader is not None:
            if modloader not in VALID_LOADER_NAMES:
                modloader = "None"
            self.profiles[name]["modloader"] = modloader
        if modloader_version is not None:
            self.profiles[name]["modloader_version"] = modloader_version
        if java_path:
            self.profiles[name]["java_path"] = java_path
        self.save_profiles()
        return True

def is_valid_jar(filepath):
    if not os.path.isfile(filepath):
        return False
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            if zf.testzip() is not None:
                return False
        return True
    except (zipfile.BadZipFile, OSError, EOFError, zipfile.LargeZipFile):
        return False

def fetch_fabric_meta(api_url):
    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except:
        return None

def get_latest_fabric_loader(mc_version):
    url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
    data = fetch_fabric_meta(url)
    if data and len(data) > 0:
        return data[0]["loader"]["version"]
    return None

def download_fabric(mc_version, loader_version, instance_dir, log_func):
    log_func("Downloading Fabric loader...")
    if not loader_version:
        loader_version = get_latest_fabric_loader(mc_version)
        if not loader_version:
            raise Exception("Could not determine latest Fabric loader for " + mc_version)
        log_func(f"Using latest Fabric loader: {loader_version}")

    fabric_dir = instance_dir / "fabric"
    fabric_dir.mkdir(exist_ok=True)

    loader_meta_url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{loader_version}/profile/json"
    resp = requests.get(loader_meta_url, timeout=10)
    resp.raise_for_status()
    meta = resp.json()

    loader_jar_path = fabric_dir / f"fabric-loader-{loader_version}.jar"
    max_attempts = 2
    for attempt in range(max_attempts):
        if loader_jar_path.exists() and is_valid_jar(loader_jar_path):
            break
        if loader_jar_path.exists():
            log_func(f"Removing corrupted loader jar (attempt {attempt+1})...", "WARNING")
            loader_jar_path.unlink()
        loader_url = None
        for lib in meta.get("libraries", []):
            if "name" in lib and lib["name"].startswith("net.fabricmc:fabric-loader"):
                if "url" in lib and "url" in lib.get("url", {}):
                    loader_url = lib["url"]["url"]
                    break
        if not loader_url:
            loader_url = f"https://maven.fabricmc.net/net/fabricmc/fabric-loader/{loader_version}/fabric-loader-{loader_version}.jar"
        log_func(f"Downloading Fabric loader jar...")
        try:
            r = requests.get(loader_url, stream=True, timeout=30)
            r.raise_for_status()
            with open(loader_jar_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
            if not is_valid_jar(loader_jar_path):
                raise Exception("Downloaded jar is invalid")
            break
        except Exception as e:
            log_func(f"Failed to download/verify loader jar: {e}", "ERROR")
            if attempt == max_attempts - 1:
                raise
            time.sleep(2)

    classpath_entries = [str(loader_jar_path)]
    libs_dir = fabric_dir / "libraries"
    libs_dir.mkdir(exist_ok=True)
    for lib in meta.get("libraries", []):
        if "name" in lib:
            parts = lib["name"].split(":")
            if len(parts) >= 3:
                group, name, version = parts[0], parts[1], parts[2]
                if group == "net.fabricmc" and name == "fabric-loader":
                    continue
                jar_path = libs_dir / f"{name}-{version}.jar"
                if jar_path.exists() and not is_valid_jar(jar_path):
                    jar_path.unlink()
                    log_func(f"Removed corrupted library: {name}", "WARNING")
                classpath_entries.append(str(jar_path))
                if not jar_path.exists():
                    url = None
                    if "url" in lib and "url" in lib.get("url", {}):
                        url = lib["url"]["url"] + "/".join(group.split(".")) + "/" + name + "/" + version + "/" + name + "-" + version + ".jar"
                    else:
                        url = f"https://maven.fabricmc.net/{group.replace('.', '/')}/{name}/{version}/{name}-{version}.jar"
                    log_func(f"Downloading library: {name}")
                    try:
                        r = requests.get(url, stream=True, timeout=30)
                        if r.status_code == 200:
                            with open(jar_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                                    if chunk:
                                        f.write(chunk)
                            if not is_valid_jar(jar_path):
                                jar_path.unlink()
                                log_func(f"Downloaded library {name} is corrupt, deleted", "WARNING")
                        else:
                            log_func(f"Failed to download {name} (HTTP {r.status_code})", "WARNING")
                    except Exception as e:
                        log_func(f"Error downloading {name}: {e}", "WARNING")

    main_class = "net.fabricmc.loader.impl.launch.knot.KnotClient"
    return main_class, classpath_entries

def download_quilt(mc_version, quilt_version, instance_dir, log_func):
    log_func("Downloading Quilt...")
    if not quilt_version:
        url = f"https://meta.quiltmc.org/v3/versions/loader/{mc_version}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if len(data) == 0:
            raise Exception(f"No Quilt loader found for {mc_version}")
        quilt_version = data[0]["loader"]["version"]
        log_func(f"Using latest Quilt: {quilt_version}")

    quilt_dir = instance_dir / "quilt"
    quilt_dir.mkdir(exist_ok=True)

    meta_url = f"https://meta.quiltmc.org/v3/versions/loader/{mc_version}/{quilt_version}/profile/json"
    resp = requests.get(meta_url, timeout=10)
    resp.raise_for_status()
    meta = resp.json()

    loader_jar = quilt_dir / f"quilt-loader-{quilt_version}.jar"
    max_attempts = 2
    for attempt in range(max_attempts):
        if loader_jar.exists() and is_valid_jar(loader_jar):
            break
        if loader_jar.exists():
            log_func(f"Removing corrupted loader jar (attempt {attempt+1})...", "WARNING")
            loader_jar.unlink()
        url = f"https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-loader/{quilt_version}/quilt-loader-{quilt_version}.jar"
        log_func(f"Downloading Quilt loader...")
        try:
            r = requests.get(url, stream=True, timeout=30)
            r.raise_for_status()
            with open(loader_jar, "wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
            if not is_valid_jar(loader_jar):
                raise Exception("Downloaded jar is invalid")
            break
        except Exception as e:
            log_func(f"Failed to download/verify loader jar: {e}", "ERROR")
            if attempt == max_attempts - 1:
                raise
            time.sleep(2)

    classpath_entries = [str(loader_jar)]
    libs_dir = quilt_dir / "libraries"
    libs_dir.mkdir(exist_ok=True)

    for lib in meta.get("libraries", []):
        if "name" in lib:
            parts = lib["name"].split(":")
            if len(parts) >= 3:
                group, name, version = parts[0], parts[1], parts[2]
                if group == "org.quiltmc" and name == "quilt-loader":
                    continue
                jar_path = libs_dir / f"{name}-{version}.jar"
                if jar_path.exists() and not is_valid_jar(jar_path):
                    jar_path.unlink()
                    log_func(f"Removed corrupted library: {name}", "WARNING")
                classpath_entries.append(str(jar_path))
                if not jar_path.exists():
                    repos = []
                    if "url" in lib and "url" in lib.get("url", {}):
                        repos.append(lib["url"]["url"])
                    if group == "net.fabricmc":
                        repos.append("https://maven.fabricmc.net/")
                    if group.startswith("org.quiltmc"):
                        repos.append("https://maven.quiltmc.org/repository/release/")
                    if group == "org.ow2.asm":
                        repos.append("https://repo1.maven.org/maven2/")
                    if group == "org.spongepowered":
                        repos.append("https://repo.spongepowered.org/maven/")
                    repos.append("https://repo1.maven.org/maven2/")
                    seen = set()
                    repos = [r for r in repos if not (r in seen or seen.add(r))]
                    path = f"{group.replace('.', '/')}/{name}/{version}/{name}-{version}.jar"
                    downloaded = False
                    for repo in repos:
                        url = repo + path
                        log_func(f"Downloading library: {name} (attempting {url})")
                        try:
                            r = requests.get(url, stream=True, timeout=30)
                            if r.status_code == 200:
                                with open(jar_path, "wb") as f:
                                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                                        if chunk:
                                            f.write(chunk)
                                if is_valid_jar(jar_path):
                                    downloaded = True
                                    break
                                else:
                                    jar_path.unlink()
                                    log_func(f"Downloaded library {name} is corrupt, trying next URL", "WARNING")
                            else:
                                log_func(f"HTTP {r.status_code} for {url}", "WARNING")
                        except Exception as e:
                            log_func(f"Error downloading {name} from {url}: {e}", "WARNING")
                    if not downloaded:
                        log_func(f"Failed to download library {name} from all sources", "WARNING")

    asm_jar = libs_dir / "asm-9.8.jar"
    if not asm_jar.exists() or not is_valid_jar(asm_jar):
        if asm_jar.exists():
            asm_jar.unlink()
        asm_url = "https://repo1.maven.org/maven2/org/ow2/asm/asm/9.8/asm-9.8.jar"
        log_func("Downloading newer ASM (9.8) for Java 25 support...")
        try:
            r = requests.get(asm_url, stream=True, timeout=30)
            if r.status_code == 200:
                with open(asm_jar, "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                if not is_valid_jar(asm_jar):
                    asm_jar.unlink()
                    log_func("Failed to download valid ASM 9.8", "WARNING")
                else:
                    log_func("ASM 9.8 downloaded successfully.")
            else:
                log_func(f"Failed to download ASM 9.8 (HTTP {r.status_code})", "WARNING")
        except Exception as e:
            log_func(f"Error downloading ASM 9.8: {e}", "WARNING")
    if asm_jar.exists() and is_valid_jar(asm_jar):
        classpath_entries.insert(0, str(asm_jar))
        log_func("Added ASM 9.8 to classpath (prepended).")

    main_class = "org.quiltmc.loader.impl.launch.knot.KnotClient"
    return main_class, classpath_entries

class MinecraftOfflineLauncherGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OpenLauncher")
        self.geometry("960x720")
        self.minsize(850, 650)
        self.configure(fg_color=BG_DARK)
        self.withdraw()

        self.progress_var = tk.DoubleVar()

        self.workdir_var = tk.StringVar(
            value=os.path.join(os.getcwd(), "minecraft_offline")
        )
        self.profile_manager = ProfileManager(self.workdir_var.get())
        self.settings_manager = SettingsManager(self.workdir_var.get())

        self.build_ui()
        self.refresh_profiles()

        self.global_username_entry.delete(0, tk.END)
        self.global_username_entry.insert(0, self.settings_manager.get_global_username())

    def build_ui(self):
        top_frame = ctk.CTkFrame(self, fg_color=BG_FRAME, corner_radius=12)
        top_frame.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(top_frame, text="Work Dir:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(10, 5))
        self.dir_entry = ctk.CTkEntry(top_frame, textvariable=self.workdir_var,
                                      width=300, corner_radius=8,
                                      fg_color=BG_DARK, text_color=TEXT_LIGHT)
        self.dir_entry.pack(side="left", padx=5, fill="x", expand=True)

        ctk.CTkButton(top_frame, text="Browse", width=80, height=30,
                      corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=self.browse_workdir).pack(side="left", padx=5)

        ctk.CTkLabel(top_frame, text="Global Username:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(20, 5))
        self.global_username_entry = ctk.CTkEntry(top_frame, width=160, corner_radius=8,
                                                  fg_color=BG_DARK, text_color=TEXT_LIGHT)
        self.global_username_entry.pack(side="left", padx=5)

        ctk.CTkButton(top_frame, text="Save", width=60, height=30,
                      corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=self.save_global_username).pack(side="left", padx=5)

        ctk.CTkButton(top_frame, text="Refresh", width=80, height=30,
                      corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=self.refresh_profiles).pack(side="left", padx=5)

        main_row = ctk.CTkFrame(self, fg_color="transparent")
        main_row.pack(fill="both", expand=True, padx=15, pady=10)

        list_frame = ctk.CTkFrame(main_row, fg_color=BG_FRAME, corner_radius=16)
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ctk.CTkLabel(list_frame, text="Profiles", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=PURPLE_LIGHT).pack(pady=(10, 5))

        self.profile_listbox = tk.Listbox(
            list_frame, bg=BG_DARK, fg=TEXT_LIGHT,
            selectbackground=PURPLE, selectforeground="white",
            font=("Segoe UI", 11), relief="flat", borderwidth=0,
            highlightthickness=0, activestyle="none"
        )
        self.profile_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.profile_listbox.bind("<Double-Button-1>", self.launch_selected)

        action_frame = ctk.CTkFrame(main_row, fg_color=BG_FRAME, corner_radius=16)
        action_frame.pack(side="right", fill="y", padx=(10, 0), pady=0)

        ctk.CTkLabel(action_frame, text="Actions", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=PURPLE_LIGHT).pack(pady=(15, 10))

        ctk.CTkButton(
            action_frame, text="▶  Launch", height=42, width=140,
            corner_radius=10, fg_color=PURPLE, hover_color=PURPLE_DARK,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.launch_selected
        ).pack(pady=6)

        ctk.CTkButton(action_frame, text="＋ Add", height=36, width=140,
                      corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=self.add_profile_dialog).pack(pady=6)

        ctk.CTkButton(action_frame, text="✎ Edit", height=36, width=140,
                      corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=self.edit_profile_dialog).pack(pady=6)

        ctk.CTkButton(action_frame, text="✕ Delete", height=36, width=140,
                      corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=self.delete_profile).pack(pady=6)

        ctk.CTkButton(action_frame, text="📂 Open Dir", height=36, width=140,
                      corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=self.open_workdir).pack(pady=6)

        progress_frame = ctk.CTkFrame(self, fg_color=BG_FRAME, corner_radius=12)
        progress_frame.pack(fill="x", padx=15, pady=(0, 5))

        self.progress_bar = ctk.CTkProgressBar(progress_frame, width=400, height=14,
                                               corner_radius=7,
                                               progress_color=PURPLE_LIGHT,
                                               fg_color=BG_DARK)
        self.progress_bar.pack(side="left", padx=(15, 10), fill="x", expand=True)
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(progress_frame, text="Ready",
                                           font=ctk.CTkFont(size=12),
                                           text_color=TEXT_DIM, width=120)
        self.progress_label.pack(side="right", padx=(10, 15))

        log_frame = ctk.CTkFrame(self, fg_color=BG_FRAME, corner_radius=16)
        log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        ctk.CTkLabel(log_frame, text="Log", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=PURPLE_LIGHT).pack(anchor="w", padx=(15, 0), pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap="word", height=10,
            bg=BG_DARK, fg=TEXT_LIGHT, insertbackground="white",
            font=("Consolas", 10), relief="flat", borderwidth=0
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text.tag_configure('INFO', foreground=TEXT_LIGHT)
        self.log_text.tag_configure('WARNING', foreground='#F1C40F')
        self.log_text.tag_configure('ERROR', foreground='#E74C3C')
        self.log_text.tag_configure('SUCCESS', foreground='#2ECC71')

    def save_global_username(self):
        name = self.global_username_entry.get().strip()
        self.settings_manager.set_global_username(name)
        self.log(f"Global username set to '{name}'", "SUCCESS")
        messagebox.showinfo("Saved", f"Global username updated to '{name}'")

    def log(self, message, level="INFO"):
        self.log_text.insert(tk.END, f"[{level}] {message}\n", level)
        self.log_text.see(tk.END)
        self.update_idletasks()

    def browse_workdir(self):
        folder = filedialog.askdirectory(title="Select Minecraft work directory")
        if folder:
            self.workdir_var.set(folder)
            self.profile_manager = ProfileManager(folder)
            self.settings_manager = SettingsManager(folder)
            self.refresh_profiles()
            self.global_username_entry.delete(0, tk.END)
            self.global_username_entry.insert(0, self.settings_manager.get_global_username())

    def refresh_profiles(self):
        self.profile_manager = ProfileManager(self.workdir_var.get())
        self.profile_listbox.delete(0, tk.END)
        for name in self.profile_manager.get_profile_names():
            self.profile_listbox.insert(tk.END, name)
        if self.profile_listbox.size() == 0:
            self.profile_listbox.insert(tk.END, "No profiles. Click 'Add'.")

    def get_selected_profile(self):
        selection = self.profile_listbox.curselection()
        if not selection:
            messagebox.showinfo("No Selection", "Please select a profile.")
            return None
        name = self.profile_listbox.get(selection[0])
        if name == "No profiles. Click 'Add'.":
            return None
        return name

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
        loader_menu = ctk.CTkComboBox(dialog, values=LOADER_CHOICES, variable=loader_var, width=200)
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
            if loader not in VALID_LOADER_NAMES:
                loader = "None"
            if self.profile_manager.add_profile(n, v, loader, loader_ver):
                self.refresh_profiles()
                dialog.destroy()
                self.log(f"Profile '{n}' added with loader {loader}.", "SUCCESS")
            else:
                messagebox.showerror("Error", f"Profile '{n}' already exists.")

        ctk.CTkButton(dialog, text="Add", command=do_add,
                      fg_color=PURPLE, hover_color=PURPLE_DARK,
                      corner_radius=8).grid(row=row, column=0, columnspan=2, pady=15)

    def edit_profile_dialog(self):
        name = self.get_selected_profile()
        if not name:
            return
        profile = self.profile_manager.get_profile(name)
        if not profile:
            return

        current_loader = profile.get("modloader", "None")
        if current_loader not in VALID_LOADER_NAMES:
            current_loader = "None"
            self.profile_manager.update_profile(name, modloader=current_loader)
            self.refresh_profiles()
            profile = self.profile_manager.get_profile(name)

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
        loader_menu = ctk.CTkComboBox(dialog, values=LOADER_CHOICES, variable=loader_var, width=200)
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
            if p:
                java_e.delete(0, tk.END)
                java_e.insert(0, p)

        ctk.CTkButton(dialog, text="Browse", width=70, height=28,
                      corner_radius=8, fg_color=PURPLE, hover_color=PURPLE_DARK,
                      command=browse_java).grid(row=row, column=2, padx=5, pady=10)
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
            if loader not in VALID_LOADER_NAMES:
                loader = "None"
            if nn != name:
                if self.profile_manager.delete_profile(name):
                    if self.profile_manager.add_profile(nn, vv, loader, loader_ver):
                        if jj:
                            self.profile_manager.update_profile(nn, java_path=jj)
                        self.refresh_profiles()
                        dialog.destroy()
                        self.log(f"Profile renamed to '{nn}'.", "SUCCESS")
                        return
            else:
                if self.profile_manager.update_profile(name, vv, loader, loader_ver, jj):
                    self.refresh_profiles()
                    dialog.destroy()
                    self.log(f"Profile '{name}' updated.", "SUCCESS")
                    return
            messagebox.showerror("Error", "Update failed.")

        ctk.CTkButton(dialog, text="Update", command=do_update,
                      fg_color=PURPLE, hover_color=PURPLE_DARK,
                      corner_radius=8).grid(row=row, column=0, columnspan=3, pady=15)

    def delete_profile(self):
        name = self.get_selected_profile()
        if not name:
            return
        if messagebox.askyesno("Confirm", f"Delete profile '{name}'?"):
            if self.profile_manager.delete_profile(name):
                self.refresh_profiles()
                self.log(f"Profile '{name}' deleted.", "SUCCESS")
            else:
                messagebox.showerror("Error", "Delete failed.")

    def open_workdir(self):
        wd = Path(self.workdir_var.get())
        if wd.exists():
            os.startfile(wd)
        else:
            messagebox.showerror("Error", "Directory does not exist.")

    def launch_selected(self, event=None):
        name = self.get_selected_profile()
        if not name:
            return
        profile = self.profile_manager.get_profile(name)
        if not profile:
            return

        version = profile.get("version")
        modloader = profile.get("modloader", "None")
        if modloader not in VALID_LOADER_NAMES:
            modloader = "None"
            self.profile_manager.update_profile(name, modloader=modloader)
            self.refresh_profiles()

        modloader_version = profile.get("modloader_version", "")
        if not version:
            messagebox.showerror("Error", "Profile missing version.")
            return

        global_username = self.settings_manager.get_global_username()
        profile_username = profile.get("username")
        if global_username and global_username.strip():
            username = global_username.strip()
        elif profile_username and profile_username.strip():
            username = profile_username.strip()
        else:
            username = DEFAULT_USERNAME

        self.launch_thread(version, username, name, modloader, modloader_version)

    def launch_thread(self, version, username, profile_name, modloader, modloader_version):
        workdir = Path(self.workdir_var.get())
        self.log(f"Launching {version} with {modloader} as '{username}'")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.progress_label.configure(text="Launching...")
        threading.Thread(target=self.do_launch, args=(version, username, workdir, profile_name, modloader, modloader_version), daemon=True).start()

    def do_launch(self, version, username, workdir, profile_name, modloader, modloader_version):
        try:
            java_path = self.ensure_java_for_version(version, workdir, profile_name)
            if not java_path:
                self.log("Cannot proceed without Java.", "ERROR")
                messagebox.showerror("Java Missing", "Java not found or selected.")
                return

            instance_dir = workdir / "instances" / profile_name
            versions_dir = instance_dir / "versions"
            assets_dir = instance_dir / "assets"
            libraries_dir = instance_dir / "libraries"
            natives_dir = instance_dir / "natives"
            for d in [versions_dir, assets_dir, libraries_dir, natives_dir]:
                d.mkdir(parents=True, exist_ok=True)

            self.log("Fetching version manifest...")
            manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
            resp = self.fetch_url_with_retries(manifest_url)
            if resp is None:
                raise Exception("Failed version manifest")
            manifest = resp.json()
            version_info = None
            for v in manifest["versions"]:
                if v["id"] == version:
                    version_info = v
                    break
            if not version_info:
                self.log(f"Version {version} not found.", "ERROR")
                return
            version_url = version_info["url"]
            resp = self.fetch_url_with_retries(version_url)
            if resp is None:
                raise Exception("Failed version JSON")
            version_json = resp.json()

            client_url = version_json["downloads"]["client"]["url"]
            client_path = versions_dir / f"{version}.jar"
            if not client_path.exists() or not is_valid_jar(client_path):
                if client_path.exists():
                    client_path.unlink()
                self.log("Downloading client JAR...")
                self.download_file(client_url, client_path)
            if not client_path.exists() or not is_valid_jar(client_path):
                self.log(f"Client JAR missing or corrupt: {client_path}", "ERROR")
                return
            self.log(f"Client JAR: {client_path}")

            asset_index_info = version_json.get("assetIndex", {})
            asset_index_id = asset_index_info.get("id", version)
            asset_index_url = asset_index_info.get("url")
            if asset_index_url:
                indexes_dir = assets_dir / "indexes"
                indexes_dir.mkdir(parents=True, exist_ok=True)
                asset_index_path = indexes_dir / f"{asset_index_id}.json"
                if not asset_index_path.exists():
                    self.log(f"Downloading asset index {asset_index_id}...")
                    self.download_file(asset_index_url, asset_index_path)
                with open(asset_index_path, "r") as f:
                    asset_index = json.load(f)
                objects = asset_index.get("objects", {})
                total = len(objects)
                self.log(f"Processing {total} assets with {MAX_WORKERS} concurrent downloads...")
                tasks = []
                for key, info in objects.items():
                    h = info["hash"]
                    prefix = h[:2]
                    obj_dir = assets_dir / "objects" / prefix
                    obj_dir.mkdir(parents=True, exist_ok=True)
                    obj_path = obj_dir / h
                    if not obj_path.exists():
                        tasks.append((f"https://resources.download.minecraft.net/{prefix}/{h}", obj_path))
                self.log(f"Need to download {len(tasks)} assets. Starting...")
                session = requests.Session()
                done = 0
                total_tasks = len(tasks)
                self.progress_bar.configure(mode="determinate")
                self.progress_bar.set(0)
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    future_to_url = {executor.submit(self.download_file_fast, url, dest, session): (url, dest) for url, dest in tasks}
                    for future in as_completed(future_to_url):
                        try:
                            future.result()
                            done += 1
                            if total_tasks > 0:
                                pct = done / total_tasks
                                self.progress_bar.set(pct)
                                self.progress_label.configure(text=f"Assets {int(pct*100)}%")
                            if done % 50 == 0:
                                self.log(f"Downloaded {done}/{total_tasks} assets...")
                        except Exception as e:
                            self.log(f"Failed asset: {e}", "WARNING")
                self.log(f"All assets processed. Downloaded {done} new files.")
            else:
                self.log("No asset index found.")

            system = platform.system()
            self.log("Downloading vanilla libraries...")
            libraries = version_json.get("libraries", [])
            vanilla_cp_entries = [str(client_path)]
            lib_tasks = []
            for lib in libraries:
                if "downloads" in lib and "artifact" in lib["downloads"]:
                    path = lib["downloads"]["artifact"]["path"]
                    if "jemalloc" in path.lower():
                        continue
                    artifact = lib["downloads"]["artifact"]
                    url = artifact["url"]
                    lib_path = libraries_dir / path
                    if not lib_path.exists():
                        lib_path.parent.mkdir(parents=True, exist_ok=True)
                        lib_tasks.append((url, lib_path))
                    vanilla_cp_entries.append(str(lib_path))
            if lib_tasks:
                self.log(f"Downloading {len(lib_tasks)} vanilla libraries...")
                with ThreadPoolExecutor(max_workers=5) as exec:
                    futures = [exec.submit(self.download_file_fast, url, dest, session) for url, dest in lib_tasks]
                    for f in as_completed(futures):
                        f.result()
                self.log("Vanilla libraries ready.")
            else:
                self.log("All vanilla libraries present.")

            self.log("Extracting native libraries...")
            for root, dirs, files in os.walk(libraries_dir):
                for file in files:
                    if file.endswith(".jar"):
                        jar_path = Path(root) / file
                        if not is_valid_jar(jar_path):
                            self.log(f"Corrupt library jar, skipping natives: {jar_path}", "WARNING")
                            continue
                        try:
                            with zipfile.ZipFile(jar_path, 'r') as zf:
                                for member in zf.namelist():
                                    if member.endswith(('.dll', '.so', '.dylib')):
                                        with zf.open(member) as src, open(natives_dir / Path(member).name, 'wb') as dst:
                                            shutil.copyfileobj(src, dst)
                        except Exception as e:
                            self.log(f"Could not extract natives from {jar_path}: {e}", "WARNING")
            self.log("Natives extracted.")

            main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")
            modloader_cp_entries = []

            if modloader != "None":
                self.log(f"Processing mod loader: {modloader}")
                loader_info = LOADER_REGISTRY.get(modloader, {})
                downloader_name = loader_info.get("downloader")
                main_class_override = loader_info.get("main_class_override")

                if downloader_name == "download_fabric":
                    main_class, modloader_cp_entries = download_fabric(version, modloader_version, instance_dir, self.log)
                elif downloader_name == "download_quilt":
                    main_class, modloader_cp_entries = download_quilt(version, modloader_version, instance_dir, self.log)
                else:
                    raise Exception(f"Unsupported or unknown mod loader: {modloader}")

                if main_class_override:
                    main_class = main_class_override

                self.log(f"Mod loader {modloader} ready. Main class: {main_class}")

            cp_entries = []
            for entry in (modloader_cp_entries + vanilla_cp_entries):
                if os.path.isfile(entry) and is_valid_jar(entry):
                    cp_entries.append(entry)
                elif os.path.isfile(entry):
                    self.log(f"Skipping corrupt jar: {entry}", "WARNING")

            self.log(f"Total classpath entries: {len(cp_entries)}")
            for idx, entry in enumerate(cp_entries[:10]):
                self.log(f"  {idx}: {entry}")
            if len(cp_entries) > 10:
                self.log(f"  ... and {len(cp_entries)-10} more")

            classpath_file = instance_dir / "classpath.txt"
            cp_str = os.pathsep.join(cp_entries)
            with open(classpath_file, "w", encoding="utf-8") as f:
                f.write(cp_str)
            self.log(f"Classpath written to {classpath_file} (length: {len(cp_str)} chars)")
            cp_arg = f"@{classpath_file.absolute()}"

            subs = {
                "${game_directory}": str(instance_dir),
                "${assets_root}": str(assets_dir),
                "${assets_index_name}": asset_index_id,
                "${version_name}": version,
                "${auth_player_name}": username,
                "${auth_uuid}": "00000000-0000-0000-0000-000000000000",
                "${auth_access_token}": "offline",
                "${user_type}": "legacy",
                "${natives_directory}": str(natives_dir),
                "${launcher_name}": "OpenLauncher",
                "${launcher_version}": "1.0",
                "${clientid}": "00000000-0000-0000-0000-000000000000",
                "${auth_xuid}": "0000000000000000",
                "${version_type}": "release"
            }

            jvm_args = []
            if "arguments" in version_json and "jvm" in version_json["arguments"]:
                for arg in version_json["arguments"]["jvm"]:
                    if isinstance(arg, str):
                        for key, val in subs.items():
                            arg = arg.replace(key, val)
                        jvm_args.append(arg)
                    elif isinstance(arg, dict) and arg.get("rules"):
                        pass
            else:
                jvm_args = ["-Xmx2G"]

            jvm_args.append("-Dorg.lwjgl.system.jemalloc.disable=true")
            jvm_args.append(f"-Djava.library.path={natives_dir}")
            jvm_args.append(f"-Dorg.lwjgl.librarypath={natives_dir}")

            if version in ("1.16.5", "1.17.1"):
                jvm_args.append("-Dorg.lwjgl.util.Debug=true")
                jvm_args.append("-Dorg.lwjgl.util.DebugLoader=true")
                jvm_args.append("-Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true")
                jvm_args.append("-Dorg.lwjgl.opengl.Window.allowSoftwareOpenGL=true")

            game_args = []
            if "arguments" in version_json and "game" in version_json["arguments"]:
                for arg in version_json["arguments"]["game"]:
                    if isinstance(arg, str):
                        for key, val in subs.items():
                            arg = arg.replace(key, val)
                        game_args.append(arg)
                    elif isinstance(arg, dict) and arg.get("rules"):
                        pass
            elif "minecraftArguments" in version_json:
                arg_str = version_json["minecraftArguments"]
                for key, val in subs.items():
                    arg_str = arg_str.replace(key, val)
                game_args = arg_str.split()

            cmd = [java_path] + jvm_args + ["-cp", cp_arg, main_class] + game_args

            bat_path = instance_dir / "launch_command.bat"
            with open(bat_path, "w") as f:
                f.write("@echo off\n")
                cmd_quoted = []
                for arg in cmd:
                    if ' ' in arg or '"' in arg:
                        cmd_quoted.append(f'"{arg}"')
                    else:
                        cmd_quoted.append(arg)
                f.write(" ".join(cmd_quoted) + "\n")
                f.write("pause\n")
            self.log(f"Launch command written to {bat_path}")

            self.log("Launching Minecraft...")
            process = subprocess.Popen(
                cmd,
                cwd=str(instance_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            def read_stdout():
                for line in process.stdout:
                    self.log(f"[STDOUT] {line.rstrip()}", "INFO")
            def read_stderr():
                for line in process.stderr:
                    self.log(f"[STDERR] {line.rstrip()}", "ERROR")

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            return_code = process.wait()
            self.log(f"Minecraft exited with code: {return_code}")

            if return_code != 0:
                self.log(f"Non-zero exit code {return_code}.", "ERROR")
                messagebox.showerror("Launch Error", f"Minecraft crashed with code {return_code}. Check log.")
                if version in ("1.16.5", "1.17.1"):
                    self.log("Check graphics drivers and OpenGL support.", "WARNING")
            else:
                self.log("Minecraft exited normally.", "SUCCESS")

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
            messagebox.showerror("Launch Error", str(e))
        finally:
            self.progress_bar.stop()
            self.progress_bar.set(0)
            self.progress_bar.configure(mode="determinate")
            self.progress_label.configure(text="Ready")

    def fetch_url_with_retries(self, url, max_retries=REQUEST_RETRIES):
        for attempt in range(max_retries):
            try:
                self.log(f"Fetching {url} (attempt {attempt+1}/{max_retries})...")
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                self.log(f"Request failed: {e}", "WARNING")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)
        return None

    def find_existing_java(self, required_major, profile_name=None):
        if profile_name:
            profile = self.profile_manager.get_profile(profile_name)
            if profile and profile.get("java_path"):
                java_path = profile["java_path"]
                if os.path.isfile(java_path):
                    try:
                        result = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=5)
                        output = result.stderr + result.stdout
                        match = re.search(r'version "(\d+)\.', output) or re.search(r'version "(\d+)-', output)
                        if match:
                            major_ver = int(match.group(1))
                            if (required_major == 8 and (major_ver == 1 or major_ver == 8)) or (required_major > 8 and major_ver >= required_major):
                                return java_path
                    except:
                        pass

        candidates = []
        system = platform.system()
        self.log(f"Scanning for Java (required major: {required_major})...", "DEBUG")
        if system == "Windows":
            for base in [os.environ.get("ProgramFiles", "C:/Program Files"),
                         os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")]:
                for vendor in ["Java", "Eclipse Adoptium", "Eclipse Foundation", "Amazon Corretto", "Microsoft", "GraalVM"]:
                    path = os.path.join(base, vendor)
                    if os.path.exists(path):
                        for root, dirs, files in os.walk(path):
                            for file in files:
                                if file.lower() == "java.exe":
                                    candidates.append(os.path.join(root, file))
            for base in [os.environ.get("ProgramFiles", "C:/Program Files"),
                         os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")]:
                jre8 = os.path.join(base, "Java", "jre1.8.0_*", "bin", "java.exe")
                for p in glob.glob(jre8):
                    candidates.append(p)
                jdk8 = os.path.join(base, "Java", "jdk1.8.0_*", "bin", "java.exe")
                for p in glob.glob(jdk8):
                    candidates.append(p)
                jre8_explicit = os.path.join(base, "Java", "jre8", "bin", "java.exe")
                if os.path.isfile(jre8_explicit):
                    candidates.append(jre8_explicit)
            java_home = os.environ.get("JAVA_HOME")
            if java_home:
                exe = os.path.join(java_home, "bin", "java.exe")
                if os.path.isfile(exe):
                    candidates.append(exe)
            for d in os.environ.get("PATH", "").split(os.pathsep):
                exe = os.path.join(d, "java.exe")
                if os.path.isfile(exe):
                    candidates.append(exe)
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                for vendor in ["Programs/Eclipse Adoptium", "Programs/Java"]:
                    path = os.path.join(local_appdata, vendor)
                    if os.path.exists(path):
                        for root, dirs, files in os.walk(path):
                            for file in files:
                                if file.lower() == "java.exe":
                                    candidates.append(os.path.join(root, file))
        elif system == "Linux":
            for base in ["/usr/lib/jvm", "/usr/lib64/jvm", "/usr/local/lib/jvm"]:
                if os.path.exists(base):
                    for root, dirs, files in os.walk(base):
                        for file in files:
                            if file == "java":
                                candidates.append(os.path.join(root, file))
            java_home = os.environ.get("JAVA_HOME")
            if java_home:
                exe = os.path.join(java_home, "bin", "java")
                if os.path.isfile(exe):
                    candidates.append(exe)
            for d in os.environ.get("PATH", "").split(os.pathsep):
                exe = os.path.join(d, "java")
                if os.path.isfile(exe):
                    candidates.append(exe)
        elif system == "Darwin":
            base = "/Library/Java/JavaVirtualMachines"
            if os.path.exists(base):
                for vm in os.listdir(base):
                    exe = os.path.join(base, vm, "Contents/Home/bin/java")
                    if os.path.isfile(exe):
                        candidates.append(exe)
            java_home = os.environ.get("JAVA_HOME")
            if java_home:
                exe = os.path.join(java_home, "bin", "java")
                if os.path.isfile(exe):
                    candidates.append(exe)
            for d in os.environ.get("PATH", "").split(os.pathsep):
                exe = os.path.join(d, "java")
                if os.path.isfile(exe):
                    candidates.append(exe)

        candidates = list(dict.fromkeys(candidates))
        self.log(f"Found {len(candidates)} candidate Java executables.", "DEBUG")
        versioned = []
        for java_path in candidates:
            try:
                result = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=5)
                output = result.stderr + result.stdout
                match = re.search(r'version "(\d+)\.', output) or re.search(r'version "(\d+)-', output)
                if match:
                    major_ver = int(match.group(1))
                    vendor = "unknown"
                    if "Eclipse Adoptium" in output or "Temurin" in output:
                        vendor = "adoptium"
                    elif "Microsoft" in output:
                        vendor = "microsoft"
                    elif "Oracle" in output:
                        vendor = "oracle"
                    else:
                        vendor = "openjdk"
                    versioned.append((major_ver, vendor, java_path))
                else:
                    self.log(f"Could not parse version from: {java_path}", "DEBUG")
            except Exception as e:
                self.log(f"Error checking {java_path}: {e}", "DEBUG")

        self.log(f"Parsed Java versions: {[(m, v, Path(p).name) for m, v, p in versioned]}", "DEBUG")
        versioned.sort(key=lambda x: (x[0], 0 if x[1] == "adoptium" else (1 if x[1] == "openjdk" else 2)))

        for major, vendor, path in versioned:
            if (required_major == 8 and (major == 1 or major == 8)) or (required_major > 8 and major >= required_major):
                if vendor == "microsoft":
                    self.log("⚠️ Microsoft JDK may cause LWJGL issues.", "WARNING")
                    self.log("💡 Recommended: Eclipse Temurin JDK 17.", "WARNING")
                return path
        return None

    def prompt_for_java(self, required_major, profile_name):
        self.log("Java not found. Please select manually.")
        answer = messagebox.askyesno(
            "Java Not Found",
            f"Java {required_major} not found automatically.\n\n"
            "Browse for java.exe (or java on Linux/Mac)?\n"
            "If not installed, download from:\n"
            f"https://adoptium.net/temurin/releases/?version={required_major}"
        )
        if not answer:
            return None
        ft = [("Java executable", "java.exe"), ("Java", "java")] if platform.system() != "Windows" else [("Java executable", "java.exe")]
        path = filedialog.askopenfilename(title="Select Java", filetypes=ft)
        if path and os.path.isfile(path):
            try:
                result = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
                output = result.stderr + result.stdout
                match = re.search(r'version "(\d+)\.', output) or re.search(r'version "(\d+)-', output)
                if match:
                    major_ver = int(match.group(1))
                    if (required_major == 8 and (major_ver == 1 or major_ver == 8)) or (required_major > 8 and major_ver >= required_major):
                        if profile_name:
                            self.profile_manager.update_profile(profile_name, java_path=path)
                            self.refresh_profiles()
                        return path
                    else:
                        self.log(f"Selected Java version {major_ver} < {required_major}.", "ERROR")
                        return None
                else:
                    self.log("Could not determine Java version.", "ERROR")
                    return None
            except:
                return None
        return None

    def ensure_java_for_version(self, version, workdir, profile_name):
        manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        try:
            resp = self.fetch_url_with_retries(manifest_url)
            if resp is None:
                raise Exception("Failed version manifest")
            manifest = resp.json()
        except Exception as e:
            self.log(f"Failed manifest: {e}", "ERROR")
            return None
        version_info = None
        for v in manifest["versions"]:
            if v["id"] == version:
                version_info = v
                break
        if not version_info:
            self.log(f"Version {version} not found.", "ERROR")
            return None
        version_url = version_info["url"]
        try:
            resp = self.fetch_url_with_retries(version_url)
            if resp is None:
                raise Exception("Failed version JSON")
            version_json = resp.json()
        except Exception as e:
            self.log(f"Failed version JSON: {e}", "ERROR")
            return None
        java_version_info = version_json.get("javaVersion", {})
        required_major = java_version_info.get("majorVersion", 8)
        self.log(f"Java required: {required_major}")

        java_path = self.find_existing_java(required_major, profile_name)
        if java_path:
            self.log(f"Found Java at: {java_path}")
            try:
                result = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=5)
                output = result.stderr + result.stdout
                if "Microsoft" in output:
                    ans = messagebox.askyesno(
                        "Microsoft JDK",
                        "Microsoft JDK may crash with this version.\n"
                        "Download Eclipse Temurin JDK 17 instead?\n"
                        "(Select No to proceed anyway)"
                    )
                    if ans:
                        webbrowser.open("https://adoptium.net/temurin/releases/?version=17")
                        self.log("Download page opened.", "INFO")
                        return None
            except:
                pass
            return java_path

        self.log(f"Java {required_major} not found.", "WARNING")
        ans = messagebox.askyesno(
            "Java Not Found",
            f"Java {required_major} not found.\n\n"
            "Browse manually?\n"
            "If not installed, download from:\n"
            f"https://adoptium.net/temurin/releases/?version={required_major}"
        )
        if ans:
            jp = self.prompt_for_java(required_major, profile_name)
            if jp:
                return jp
        webbrowser.open(f"https://adoptium.net/temurin/releases/?version={required_major}")
        self.log("Browser opened for Java download.", "INFO")
        messagebox.showinfo("Java Required", "Install Java, then retry.")
        return None

    def download_file_fast(self, url, dest_path, session):
        response = session.get(url, stream=True)
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)

    def download_file(self, url, dest_path, silent=False):
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total = int(response.headers.get('content-length', 0))
        done = 0
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if not silent and total > 0:
                        pct = (done / total) * 100
                        self.log(f"Download progress: {pct:.1f}%", "INFO")
        if not silent:
            self.log(f"Downloaded: {dest_path.name}")

if __name__ == "__main__":
    app = MinecraftOfflineLauncherGUI()
    splash = SplashScreen(app)
    app.mainloop()
