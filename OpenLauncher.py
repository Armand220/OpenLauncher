#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re
import platform
import tempfile
import shutil
import webbrowser
import zipfile
import glob
import uuid

DEFAULT_VERSION = "1.21.1"
DEFAULT_USERNAME = "OfflinePlayer"
PROFILES_FILE = "profiles.json"
MAX_WORKERS = 20
CHUNK_SIZE = 128 * 1024
REQUEST_RETRIES = 3

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
                    return json.load(f)
            except:
                return {}
        return {}

    def save_profiles(self):
        with open(self.profiles_path, "w") as f:
            json.dump(self.profiles, f, indent=2)

    def get_profile_names(self):
        return list(self.profiles.keys())

    def get_profile(self, name):
        return self.profiles.get(name, {})

    def add_profile(self, name, version, username):
        if name in self.profiles:
            return False
        self.profiles[name] = {"version": version, "username": username}
        self.save_profiles()
        (self.workdir / "instances" / name).mkdir(parents=True, exist_ok=True)
        return True

    def delete_profile(self, name):
        if name in self.profiles:
            del self.profiles[name]
            self.save_profiles()
            return True
        return False

    def update_profile(self, name, version=None, username=None, java_path=None):
        if name not in self.profiles:
            return False
        if version:
            self.profiles[name]["version"] = version
        if username:
            self.profiles[name]["username"] = username
        if java_path:
            self.profiles[name]["java_path"] = java_path
        self.save_profiles()
        return True

class MinecraftOfflineLauncherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OpenLauncher - Minecraft Offline Launcher")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        self.workdir_var = tk.StringVar(value=os.path.join(os.getcwd(), "minecraft_offline"))
        self.profile_manager = ProfileManager(self.workdir_var.get())

        top_frame = ttk.LabelFrame(root, text="Work Directory", padding=5)
        top_frame.pack(fill="x", padx=10, pady=5)
        ttk.Entry(top_frame, textvariable=self.workdir_var, width=50).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(top_frame, text="Browse", command=self.browse_workdir).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Refresh", command=self.refresh_profiles).pack(side="left", padx=5)

        main_frame = ttk.Frame(root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        list_frame = ttk.LabelFrame(main_frame, text="Profiles", padding=5)
        list_frame.pack(side="left", fill="both", expand=True)
        self.profile_listbox = tk.Listbox(list_frame, height=10)
        self.profile_listbox.pack(fill="both", expand=True)
        self.profile_listbox.bind("<Double-Button-1>", self.launch_selected)

        action_frame = ttk.LabelFrame(main_frame, text="Actions", padding=5)
        action_frame.pack(side="right", fill="y", padx=5)
        ttk.Button(action_frame, text="Launch Selected", command=self.launch_selected).pack(pady=5, fill="x")
        ttk.Button(action_frame, text="Add New Profile", command=self.add_profile_dialog).pack(pady=5, fill="x")
        ttk.Button(action_frame, text="Edit Profile", command=self.edit_profile_dialog).pack(pady=5, fill="x")
        ttk.Button(action_frame, text="Delete Profile", command=self.delete_profile).pack(pady=5, fill="x")
        ttk.Button(action_frame, text="Open Work Dir", command=self.open_workdir).pack(pady=5, fill="x")

        log_frame = ttk.LabelFrame(root, text="Log", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap="word", height=10)
        self.log_text.pack(fill="both", expand=True)

        self.refresh_profiles()

    def log(self, message, level="INFO"):
        self.log_text.insert(tk.END, f"[{level}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def browse_workdir(self):
        folder = filedialog.askdirectory(title="Select Minecraft work directory")
        if folder:
            self.workdir_var.set(folder)
            self.profile_manager = ProfileManager(folder)
            self.refresh_profiles()

    def refresh_profiles(self):
        self.profile_manager = ProfileManager(self.workdir_var.get())
        self.profile_listbox.delete(0, tk.END)
        for name in self.profile_manager.get_profile_names():
            self.profile_listbox.insert(tk.END, name)
        if self.profile_listbox.size() == 0:
            self.profile_listbox.insert(tk.END, "No profiles. Click 'Add New Profile'.")

    def get_selected_profile(self):
        selection = self.profile_listbox.curselection()
        if not selection:
            messagebox.showinfo("No Selection", "Please select a profile.")
            return None
        name = self.profile_listbox.get(selection[0])
        if name == "No profiles. Click 'Add New Profile'.":
            return None
        return name

    def add_profile_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Profile")
        dialog.geometry("400x200")
        dialog.resizable(False, False)

        ttk.Label(dialog, text="Profile Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        name_entry = ttk.Entry(dialog, width=30)
        name_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(dialog, text="Minecraft Version:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        version_entry = ttk.Entry(dialog, width=30)
        version_entry.insert(0, DEFAULT_VERSION)
        version_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(dialog, text="Offline Username:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        username_entry = ttk.Entry(dialog, width=30)
        username_entry.insert(0, DEFAULT_USERNAME)
        username_entry.grid(row=2, column=1, padx=5, pady=5)

        def do_add():
            name = name_entry.get().strip()
            version = version_entry.get().strip()
            username = username_entry.get().strip()
            if not name or not version or not username:
                messagebox.showerror("Error", "All fields are required.")
                return
            if self.profile_manager.add_profile(name, version, username):
                self.refresh_profiles()
                dialog.destroy()
                self.log(f"Profile '{name}' added.")
            else:
                messagebox.showerror("Error", f"Profile '{name}' already exists.")

        ttk.Button(dialog, text="Add", command=do_add).grid(row=3, column=0, columnspan=2, pady=10)

    def edit_profile_dialog(self):
        name = self.get_selected_profile()
        if not name:
            return
        profile = self.profile_manager.get_profile(name)
        if not profile:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Profile: {name}")
        dialog.geometry("400x250")
        dialog.resizable(False, False)

        ttk.Label(dialog, text="Profile Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        name_entry = ttk.Entry(dialog, width=30)
        name_entry.insert(0, name)
        name_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(dialog, text="Minecraft Version:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        version_entry = ttk.Entry(dialog, width=30)
        version_entry.insert(0, profile.get("version", DEFAULT_VERSION))
        version_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(dialog, text="Offline Username:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        username_entry = ttk.Entry(dialog, width=30)
        username_entry.insert(0, profile.get("username", DEFAULT_USERNAME))
        username_entry.grid(row=2, column=1, padx=5, pady=5)

        ttk.Label(dialog, text="Java Path (optional):").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        java_entry = ttk.Entry(dialog, width=30)
        java_entry.insert(0, profile.get("java_path", ""))
        java_entry.grid(row=3, column=1, padx=5, pady=5)

        def browse_java():
            path = filedialog.askopenfilename(title="Select java executable", filetypes=[("Java", "java.exe"), ("Java", "java")])
            if path:
                java_entry.delete(0, tk.END)
                java_entry.insert(0, path)

        ttk.Button(dialog, text="Browse Java", command=browse_java).grid(row=3, column=2, padx=5, pady=5)

        def do_update():
            new_name = name_entry.get().strip()
            version = version_entry.get().strip()
            username = username_entry.get().strip()
            java_path = java_entry.get().strip()
            if not new_name or not version or not username:
                messagebox.showerror("Error", "All fields are required.")
                return
            if new_name != name:
                if self.profile_manager.delete_profile(name):
                    if self.profile_manager.add_profile(new_name, version, username):
                        if java_path:
                            self.profile_manager.update_profile(new_name, java_path=java_path)
                        self.refresh_profiles()
                        dialog.destroy()
                        self.log(f"Profile renamed to '{new_name}'.")
                        return
            else:
                if self.profile_manager.update_profile(name, version, username, java_path):
                    self.refresh_profiles()
                    dialog.destroy()
                    self.log(f"Profile '{name}' updated.")
                    return
            messagebox.showerror("Error", "Update failed.")

        ttk.Button(dialog, text="Update", command=do_update).grid(row=4, column=0, columnspan=2, pady=10)

    def delete_profile(self):
        name = self.get_selected_profile()
        if not name:
            return
        if messagebox.askyesno("Confirm Delete", f"Delete profile '{name}'?"):
            if self.profile_manager.delete_profile(name):
                self.refresh_profiles()
                self.log(f"Profile '{name}' deleted.")
            else:
                messagebox.showerror("Error", "Delete failed.")

    def open_workdir(self):
        workdir = Path(self.workdir_var.get())
        if workdir.exists():
            os.startfile(workdir)
        else:
            messagebox.showerror("Error", "Work directory does not exist.")

    def launch_selected(self, event=None):
        name = self.get_selected_profile()
        if not name:
            return
        profile = self.profile_manager.get_profile(name)
        if not profile:
            return
        version = profile.get("version")
        username = profile.get("username")
        if not version or not username:
            messagebox.showerror("Error", "Profile is missing version or username.")
            return
        self.launch_thread(version, username, name)

    def launch_thread(self, version, username, profile_name):
        workdir = Path(self.workdir_var.get())
        self.log(f"Launching profile: {version} with username {username}")
        threading.Thread(target=self.do_launch, args=(version, username, workdir, profile_name), daemon=True).start()

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
        self.log(f"Scanning for Java installations (required major: {required_major})...", "DEBUG")
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
                    self.log("⚠️ Microsoft JDK detected – may cause compatibility issues with LWJGL.", "WARNING")
                    self.log("💡 It is recommended to install Eclipse Temurin (Adoptium) JDK 17.", "WARNING")
                return path
        return None

    def prompt_for_java(self, required_major, profile_name):
        self.log("Java not found. Please select the java executable manually.")
        answer = messagebox.askyesno(
            "Java Not Found",
            f"Java {required_major} could not be found automatically.\n\n"
            "Would you like to browse for java.exe (or java on Linux/Mac) manually?\n"
            "If you don't have Java installed, download it from:\n"
            "https://adoptium.net/temurin/releases/?version={required_major}"
        )
        if not answer:
            return None
        filetypes = [("Java executable", "java.exe"), ("Java executable", "java")] if platform.system() != "Windows" else [("Java executable", "java.exe")]
        path = filedialog.askopenfilename(title="Select Java executable", filetypes=filetypes)
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
                        self.log(f"Selected Java version {major_ver} does not meet requirement (>= {required_major}).", "ERROR")
                        messagebox.showerror("Wrong Version", f"Selected Java version {major_ver} is not compatible. Need {required_major} or higher.")
                        return None
                else:
                    self.log("Could not determine Java version.", "ERROR")
                    return None
            except Exception as e:
                self.log(f"Error checking Java: {e}", "ERROR")
                return None
        return None

    def ensure_java_for_version(self, version, workdir, profile_name):
        manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        try:
            resp = self.fetch_url_with_retries(manifest_url)
            if resp is None:
                raise Exception("Failed to fetch version manifest after retries.")
            manifest = resp.json()
        except Exception as e:
            self.log(f"Failed to fetch version manifest: {e}", "ERROR")
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
                raise Exception("Failed to fetch version JSON after retries.")
            version_json = resp.json()
        except Exception as e:
            self.log(f"Failed to fetch version JSON for {version}: {e}", "ERROR")
            return None
        java_version_info = version_json.get("javaVersion", {})
        required_major = java_version_info.get("majorVersion", 8)
        self.log(f"Java required: version {required_major}")

        java_path = self.find_existing_java(required_major, profile_name)
        if java_path:
            self.log(f"Found Java at: {java_path}")
            try:
                result = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=5)
                output = result.stderr + result.stdout
                if "Microsoft" in output:
                    answer = messagebox.askyesno(
                        "Microsoft JDK Detected",
                        "You are using Microsoft's JDK, which may cause crashes with this version of Minecraft.\n\n"
                        "Would you like to download the recommended Eclipse Temurin (Adoptium) JDK 17?\n"
                        "This is the version used by official launchers and is known to work reliably.\n\n"
                        "If you choose 'No', the launcher will proceed with Microsoft JDK (may still crash)."
                    )
                    if answer:
                        webbrowser.open("https://adoptium.net/temurin/releases/?version=17")
                        self.log("Opened download page for Eclipse Temurin JDK 17. Please install and try again.", "INFO")
                        return None
            except:
                pass
            return java_path

        self.log(f"Java {required_major} not found. Please select or install.", "WARNING")
        answer = messagebox.askyesno(
            "Java Not Found",
            f"Java {required_major} could not be found.\n\n"
            "Would you like to browse for java.exe (or java on Linux/Mac) manually?\n"
            "If you don't have Java installed, download it from:\n"
            "https://adoptium.net/temurin/releases/?version={required_major}"
        )
        if answer:
            java_path = self.prompt_for_java(required_major, profile_name)
            if java_path:
                return java_path
        webbrowser.open(f"https://adoptium.net/temurin/releases/?version={required_major}")
        self.log("A browser has been opened to download Java.", "INFO")
        messagebox.showinfo("Java Required", "Please download and install Java, then launch this profile again.")
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
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if not silent and total_size > 0:
                        percent = (downloaded / total_size) * 100
                        self.log(f"Download progress: {percent:.1f}%", "INFO")
        if not silent:
            self.log(f"Downloaded: {dest_path.name}")

    def do_launch(self, version, username, workdir, profile_name):
        try:
            java_path = self.ensure_java_for_version(version, workdir, profile_name)
            if not java_path:
                self.log("Cannot proceed without Java.", "ERROR")
                messagebox.showerror("Java Missing", "Java could not be found or selected. Please install Java and try again.")
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
                raise Exception("Failed to fetch version manifest after retries.")
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
                raise Exception("Failed to fetch version JSON after retries.")
            version_json = resp.json()

            client_url = version_json["downloads"]["client"]["url"]
            client_path = versions_dir / f"{version}.jar"
            if not client_path.exists():
                self.log("Downloading client JAR...")
                self.download_file(client_url, client_path)
            if not client_path.exists():
                self.log(f"Client JAR missing: {client_path}", "ERROR")
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
                    hash_val = info["hash"]
                    prefix = hash_val[:2]
                    obj_dir = assets_dir / "objects" / prefix
                    obj_dir.mkdir(parents=True, exist_ok=True)
                    obj_path = obj_dir / hash_val
                    if not obj_path.exists():
                        url = f"https://resources.download.minecraft.net/{prefix}/{hash_val}"
                        tasks.append((url, obj_path))
                self.log(f"Need to download {len(tasks)} assets. Starting concurrent downloads...")
                session = requests.Session()
                downloaded = 0
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    future_to_url = {executor.submit(self.download_file_fast, url, dest, session): (url, dest) for url, dest in tasks}
                    for future in as_completed(future_to_url):
                        try:
                            future.result()
                            downloaded += 1
                            if downloaded % 100 == 0:
                                self.log(f"Downloaded {downloaded}/{len(tasks)} assets...")
                        except Exception as e:
                            self.log(f"Failed to download {future_to_url[future][1].name}: {e}", "WARNING")
                self.log(f"All assets processed. Downloaded {downloaded} new files.")
            else:
                self.log("No asset index found for this version.")

            system = platform.system()
            if system == "Windows":
                classifier = "natives-windows"
            elif system == "Linux":
                classifier = "natives-linux"
            elif system == "Darwin":
                classifier = "natives-macos"
            else:
                classifier = "natives-windows"

            self.log("Downloading libraries and natives...")
            libraries = version_json.get("libraries", [])
            cp_entries = [str(client_path)]
            lib_tasks = []
            native_jars = []
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
                    cp_entries.append(str(lib_path))
                if "natives" in lib:
                    natives_map = lib.get("natives", {})
                    platform_key = None
                    if system == "Windows":
                        platform_key = "windows"
                    elif system == "Linux":
                        platform_key = "linux"
                    elif system == "Darwin":
                        platform_key = "osx"
                    if platform_key and platform_key in natives_map:
                        classifier_name = natives_map[platform_key]
                        if "downloads" in lib and "classifiers" in lib["downloads"]:
                            classifiers = lib["downloads"]["classifiers"]
                            if classifier_name in classifiers:
                                classifier_info = classifiers[classifier_name]
                                path = classifier_info["path"]
                                if "jemalloc" in path.lower():
                                    continue
                                url = classifier_info["url"]
                                lib_path = libraries_dir / path
                                if not lib_path.exists():
                                    lib_path.parent.mkdir(parents=True, exist_ok=True)
                                    lib_tasks.append((url, lib_path))
                                cp_entries.append(str(lib_path))
                                native_jars.append(lib_path)
            if lib_tasks:
                self.log(f"Downloading {len(lib_tasks)} libraries (excluding jemalloc)...")
                with ThreadPoolExecutor(max_workers=5) as exec:
                    futures = [exec.submit(self.download_file_fast, url, dest, session) for url, dest in lib_tasks]
                    for f in as_completed(futures):
                        f.result()
                self.log("Libraries ready.")
            else:
                self.log("All libraries already present (excluding jemalloc).")

            if native_jars:
                self.log("Extracting native libraries...")
                for jar_path in native_jars:
                    try:
                        with zipfile.ZipFile(jar_path, 'r') as zip_ref:
                            for file in zip_ref.namelist():
                                if file.endswith('.dll') or file.endswith('.so') or file.endswith('.dylib'):
                                    with zip_ref.open(file) as src, open(natives_dir / Path(file).name, 'wb') as dst:
                                        shutil.copyfileobj(src, dst)
                    except Exception as e:
                        self.log(f"Failed to extract natives from {jar_path}: {e}", "WARNING")
                self.log("Native libraries extracted.")

            profiles_path = instance_dir / "launcher_profiles.json"
            if version == "1.8.9":
                if profiles_path.exists():
                    profiles_path.unlink()
                    self.log("Deleted launcher_profiles.json for 1.8.9 (game will use defaults).")
            else:
                if profiles_path.exists():
                    profiles_path.unlink()
                try:
                    client_token = str(uuid.uuid4())
                    user_uuid = str(uuid.uuid4())
                    profiles_json = {
                        "profiles": {
                            "offline": {
                                "name": username,
                                "lastVersionId": version,
                                "javaArgs": "-Xmx2G",
                                "gameDir": str(instance_dir)
                            }
                        },
                        "selectedProfile": "offline",
                        "clientToken": client_token,
                        "authenticationDatabase": {
                            user_uuid: {
                                "username": username,
                                "accessToken": "offline",
                                "displayName": username,
                                "userid": user_uuid
                            }
                        },
                        "selectedUser": user_uuid
                    }
                    with open(profiles_path, "w", encoding="utf-8") as f:
                        json.dump(profiles_json, f, indent=2, ensure_ascii=False)
                    self.log(f"Created launcher_profiles.json at {profiles_path}")
                except Exception as e:
                    self.log(f"Failed to create launcher_profiles.json: {e}", "WARNING")
                    if profiles_path.exists():
                        profiles_path.unlink()

            cp_str = os.pathsep.join(cp_entries)
            self.log(f"Classpath length: {len(cp_str)} chars")

            fake_client_id = "00000000-0000-0000-0000-000000000000"
            fake_xuid = "0000000000000000"
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
                "${launcher_name}": "OfflineLauncher",
                "${launcher_version}": "1.0",
                "${clientid}": fake_client_id,
                "${auth_xuid}": fake_xuid,
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

            main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")

            cmd = [java_path] + jvm_args + ["-cp", cp_str, main_class] + game_args

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
            self.log(f"Full launch command written to {bat_path} – run it manually if needed.")

            self.log("Launch command (truncated): " + " ".join(cmd[:5]) + " ...")

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
            self.log(f"Minecraft process exited with code: {return_code}")

            if return_code != 0:
                self.log(f"Process exited with non-zero code {return_code}. Check the error log above.", "ERROR")
                messagebox.showerror("Launch Error", f"Minecraft crashed with exit code {return_code}. Check the log.")
                if version in ("1.16.5", "1.17.1"):
                    self.log("\n*** If you got an EXCEPTION_ACCESS_VIOLATION, please check your graphics drivers and try updating them. ***", "WARNING")
                    self.log("*** Also ensure your GPU supports OpenGL 3.2 or higher. ***", "WARNING")
                    self.log("*** If you have an NVIDIA GPU, try updating your drivers from the NVIDIA website. ***", "WARNING")
            else:
                self.log("Minecraft exited normally.")

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
            messagebox.showerror("Launch Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = MinecraftOfflineLauncherGUI(root)
    root.mainloop()