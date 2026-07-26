import os
import subprocess
import threading
import time
import platform
import re
import glob
import shutil
import webbrowser
import zipfile
import json
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from helpers import is_valid_jar, copy_file_with_retry
from downloaders import download_fabric, download_quilt

CHUNK_SIZE = 128 * 1024
REQUEST_RETRIES = 3
MAX_WORKERS = 20

class LauncherCore:
    def __init__(self, workdir, profile_manager, settings_manager, log_func, progress_callback=None):
        self.workdir = Path(workdir)
        self.profile_manager = profile_manager
        self.settings_manager = settings_manager
        self.log = log_func
        self.progress = progress_callback

    def launch(self, version, username, profile_name, modloader, modloader_version):
        self.log(f"Launching {version} with {modloader} as '{username}'")
        threading.Thread(target=self._do_launch, args=(version, username, profile_name, modloader, modloader_version), daemon=True).start()

    def _do_launch(self, version, username, profile_name, modloader, modloader_version):
        try:
            profile = self.profile_manager.get_profile(profile_name)
            memory = int(profile.get("memory", "2048"))
            custom_jvm = profile.get("jvm_args", "")

            # Java detection
            java_path = self._ensure_java_for_version(version, profile_name)
            if not java_path:
                self.log("Cannot proceed without Java.", "ERROR")
                return

            instance_dir = self.workdir / "instances" / profile_name

            # Prepare directories
            versions_dir = instance_dir / "versions"
            assets_dir = instance_dir / "assets"
            libraries_dir = instance_dir / "libraries"
            natives_dir = instance_dir / "natives"
            for d in [versions_dir, assets_dir, libraries_dir, natives_dir]:
                d.mkdir(parents=True, exist_ok=True)

            mods_dir = instance_dir / "mods"
            mods_dir.mkdir(exist_ok=True)
            rp_dir = instance_dir / "resourcepacks"
            rp_dir.mkdir(exist_ok=True)

            # Fetch manifest
            manifest = self._fetch_manifest()
            if not manifest:
                raise Exception("Failed version manifest")

            version_info = None
            for v in manifest["versions"]:
                if v["id"] == version:
                    version_info = v
                    break
            if not version_info:
                self.log(f"Version {version} not found.", "ERROR")
                return

            version_json = self._fetch_version_json(version_info["url"])
            if not version_json:
                raise Exception("Failed version JSON")

            # Download client
            client_path = versions_dir / f"{version}.jar"
            if not client_path.exists() or not is_valid_jar(client_path):
                if client_path.exists():
                    client_path.unlink()
                self.log("Downloading client JAR...")
                self._download_file(version_json["downloads"]["client"]["url"], client_path)
            if not client_path.exists() or not is_valid_jar(client_path):
                self.log(f"Client JAR missing or corrupt: {client_path}", "ERROR")
                return

            # Download assets
            self._download_assets(version_json, assets_dir)

            # Download libraries
            vanilla_cp_entries = self._download_libraries(version_json, libraries_dir, client_path)

            # Extract natives
            self._extract_natives(libraries_dir, natives_dir)

            # Mod loader
            main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")
            modloader_cp_entries = []
            if modloader != "None":
                self.log(f"Processing mod loader: {modloader}")
                if modloader == "Fabric":
                    main_class, modloader_cp_entries = download_fabric(version, modloader_version, instance_dir, self.log)
                elif modloader == "Quilt":
                    main_class, modloader_cp_entries = download_quilt(version, modloader_version, instance_dir, self.log)
                else:
                    raise Exception(f"Unsupported mod loader: {modloader}")

            # Build classpath
            cp_entries = []
            for entry in (modloader_cp_entries + vanilla_cp_entries):
                if os.path.isfile(entry) and is_valid_jar(entry):
                    cp_entries.append(entry)
                elif os.path.isfile(entry):
                    self.log(f"Skipping corrupt jar: {entry}", "WARNING")

            classpath_file = instance_dir / "classpath.txt"
            cp_str = os.pathsep.join(cp_entries)
            with open(classpath_file, "w", encoding="utf-8") as f:
                f.write(cp_str)
            cp_arg = f"@{classpath_file.absolute()}"

            # Build command
            subs = {
                "${game_directory}": str(instance_dir),
                "${assets_root}": str(assets_dir),
                "${assets_index_name}": version_json.get("assetIndex", {}).get("id", version),
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
                jvm_args = []

            jvm_args.insert(0, f"-Xmx{memory}M")
            if custom_jvm:
                jvm_args.extend(custom_jvm.split())

            # Suppress LWJGL warnings (optional but helps)
            jvm_args.append("--enable-native-access=ALL-UNNAMED")

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

            # Save batch file
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
            else:
                self.log("Minecraft exited normally.", "SUCCESS")

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
        finally:
            if self.progress:
                self.progress(0, "Ready")

    # ---------- Helpers ----------
    def _fetch_manifest(self):
        url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        return self._fetch_json(url)

    def _fetch_version_json(self, url):
        return self._fetch_json(url)

    def _fetch_json(self, url):
        for attempt in range(REQUEST_RETRIES):
            try:
                self.log(f"Fetching {url} (attempt {attempt+1}/{REQUEST_RETRIES})...")
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except:
                if attempt == REQUEST_RETRIES - 1:
                    raise
                time.sleep(2)
        return None

    def _download_file(self, url, dest_path, silent=False):
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

    def _download_assets(self, version_json, assets_dir):
        asset_index_info = version_json.get("assetIndex", {})
        asset_index_id = asset_index_info.get("id", "")
        asset_index_url = asset_index_info.get("url")
        if not asset_index_url:
            self.log("No asset index found.")
            return
        indexes_dir = assets_dir / "indexes"
        indexes_dir.mkdir(parents=True, exist_ok=True)
        asset_index_path = indexes_dir / f"{asset_index_id}.json"
        if not asset_index_path.exists():
            self.log(f"Downloading asset index {asset_index_id}...")
            self._download_file(asset_index_url, asset_index_path)
        with open(asset_index_path, "r") as f:
            asset_index = json.load(f)
        objects = asset_index.get("objects", {})
        tasks = []
        for key, info in objects.items():
            h = info["hash"]
            prefix = h[:2]
            obj_dir = assets_dir / "objects" / prefix
            obj_dir.mkdir(parents=True, exist_ok=True)
            obj_path = obj_dir / h
            if not obj_path.exists():
                tasks.append((f"https://resources.download.minecraft.net/{prefix}/{h}", obj_path))
        if not tasks:
            self.log("All assets already present.")
            return
        self.log(f"Downloading {len(tasks)} assets...")
        session = requests.Session()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(self._download_file_fast, url, dest, session) for url, dest in tasks]
            for future in as_completed(futures):
                future.result()
        self.log("Assets ready.")

    def _download_file_fast(self, url, dest_path, session):
        response = session.get(url, stream=True)
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)

    def _download_libraries(self, version_json, libraries_dir, client_path):
        libraries = version_json.get("libraries", [])
        cp_entries = [str(client_path)]
        tasks = []
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
                    tasks.append((url, lib_path))
                cp_entries.append(str(lib_path))
        if tasks:
            self.log(f"Downloading {len(tasks)} libraries...")
            session = requests.Session()
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(self._download_file_fast, url, dest, session) for url, dest in tasks]
                for future in as_completed(futures):
                    future.result()
            self.log("Libraries ready.")
        else:
            self.log("All libraries present.")
        return cp_entries

    def _extract_natives(self, libraries_dir, natives_dir):
        self.log("Extracting native libraries...")
        for root, dirs, files in os.walk(libraries_dir):
            for file in files:
                if file.endswith(".jar"):
                    jar_path = Path(root) / file
                    if not is_valid_jar(jar_path):
                        continue
                    try:
                        with zipfile.ZipFile(jar_path, 'r') as zf:
                            for member in zf.namelist():
                                if member.endswith(('.dll', '.so', '.dylib')):
                                    with zf.open(member) as src, open(natives_dir / Path(member).name, 'wb') as dst:
                                        shutil.copyfileobj(src, dst)
                    except:
                        pass
        self.log("Natives extracted.")

    def _ensure_java_for_version(self, version, profile_name):
        # Fetch version JSON for Java version requirement
        manifest = self._fetch_manifest()
        if not manifest:
            return None
        version_info = None
        for v in manifest["versions"]:
            if v["id"] == version:
                version_info = v
                break
        if not version_info:
            self.log(f"Version {version} not found.", "ERROR")
            return None
        version_json = self._fetch_version_json(version_info["url"])
        if not version_json:
            return None
        java_version_info = version_json.get("javaVersion", {})
        required_major = java_version_info.get("majorVersion", 8)
        self.log(f"Java required: {required_major}")

        java_path = self._find_java(required_major, profile_name)
        if java_path:
            self.log(f"Found Java at: {java_path}")
            return java_path

        # Prompt user
        self.log(f"Java {required_major} not found.", "WARNING")
        import tkinter.messagebox as msg
        ans = msg.askyesno(
            "Java Not Found",
            f"Java {required_major} not found.\n\n"
            "Browse manually?\n"
            "If not installed, download from:\n"
            f"https://adoptium.net/temurin/releases/?version={required_major}"
        )
        if ans:
            from tkinter import filedialog
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
                            self.profile_manager.update_profile(profile_name, java_path=path)
                            return path
                        else:
                            self.log(f"Selected Java version {major_ver} < {required_major}.", "ERROR")
                            return None
                except:
                    return None
        webbrowser.open(f"https://adoptium.net/temurin/releases/?version={required_major}")
        self.log("Browser opened for Java download.", "INFO")
        msg.showinfo("Java Required", "Install Java, then retry.")
        return None

    def _find_java(self, required_major, profile_name=None):
        # Check per-profile override
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
        # Sort: prefer higher major, then adoptium > openjdk > others
        versioned.sort(key=lambda x: (x[0], 0 if x[1] == "adoptium" else (1 if x[1] == "openjdk" else 2)), reverse=True)

        for major, vendor, path in versioned:
            if (required_major == 8 and (major == 1 or major == 8)) or (required_major > 8 and major >= required_major):
                return path
        return None