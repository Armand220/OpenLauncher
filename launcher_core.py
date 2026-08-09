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
from io import BytesIO

CHUNK_SIZE = 128 * 1024
REQUEST_RETRIES = 3
MAX_WORKERS = 20

def get_subprocess_kwargs():
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {
            "startupinfo": startupinfo,
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }
    return {}

class LauncherCore:
    def __init__(self, workdir, profile_manager, account_manager, log_func, progress_callback=None):
        self.workdir = Path(workdir)
        self.profile_manager = profile_manager
        self.account_manager = account_manager
        self.log = log_func
        self.progress = progress_callback
        self.java_download_dir = self.workdir / "java"
        self.java_download_dir.mkdir(parents=True, exist_ok=True)

    def launch(self, version, username, profile_name, modloader, modloader_version):
        self.log(f"Launching {version} with {modloader} as '{username}'")
        threading.Thread(target=self._do_launch, args=(version, username, profile_name, modloader, modloader_version), daemon=True).start()

    def _get_csl_jar_for_version(self, mc_version, loader):
        """
        Query the Modrinth API to find the best compatible CustomSkinLoader JAR
        for the given Minecraft version and loader (Fabric or Quilt).
        Returns (filename, download_url) or (None, None) if nothing found.
        """
        import urllib.parse
        loader_name = loader.lower()  # "fabric" or "quilt"
        url = (
            "https://api.modrinth.com/v2/project/idMHQ4n2/version"
            f"?loaders=%5B%22{loader_name}%22%5D"
            f"&game_versions=%5B%22{urllib.parse.quote(mc_version)}%22%5D"
        )
        try:
            resp = requests.get(url, timeout=10,
                                headers={"User-Agent": "OpenLauncher/1.0"})
            resp.raise_for_status()
            versions = resp.json()
        except Exception as e:
            self.log(f"Modrinth API error querying CSL: {e}", "WARNING")
            return None, None

        if not versions:
            # Fall back: try without strict game_version filter — take the
            # latest release that lists our MC version in its game_versions.
            try:
                resp2 = requests.get(
                    f"https://api.modrinth.com/v2/project/idMHQ4n2/version"
                    f"?loaders=%5B%22{loader_name}%22%5D",
                    timeout=10, headers={"User-Agent": "OpenLauncher/1.0"})
                resp2.raise_for_status()
                all_versions = resp2.json()
                versions = [v for v in all_versions
                            if mc_version in v.get("game_versions", [])]
            except Exception as e:
                self.log(f"Modrinth fallback query failed: {e}", "WARNING")
                return None, None

        if not versions:
            return None, None

        # Pick the first (newest) release; fall back to any version type.
        chosen = next((v for v in versions if v.get("version_type") == "release"), versions[0])
        for f in chosen.get("files", []):
            if f.get("primary", False) or f.get("filename", "").endswith(".jar"):
                return f["filename"], f["url"]
        return None, None

    def _ensure_csl_installed(self, instance_dir, mc_version, modloader):
        """
        Auto-install CustomSkinLoader into the instance mods folder if it isn't
        already present.  Skips silently for vanilla (no mod loader).
        """
        if modloader == "None":
            return  # CSL requires Fabric or Quilt

        mods_dir = instance_dir / "mods"
        mods_dir.mkdir(exist_ok=True)

        # Already installed? (any CSL jar present)
        existing = list(mods_dir.glob("CustomSkinLoader*.jar")) +                    list(mods_dir.glob("customskinloader*.jar"))
        if existing:
            self.log(f"CustomSkinLoader already installed: {existing[0].name}", "INFO")
            return

        self.log(f"Auto-installing CustomSkinLoader for {modloader} {mc_version}…")
        filename, url = self._get_csl_jar_for_version(mc_version, modloader)
        if not filename or not url:
            self.log(
                f"Could not find a CustomSkinLoader release for "
                f"{modloader} {mc_version} on Modrinth.", "WARNING")
            return

        dest = mods_dir / filename
        try:
            r = requests.get(url, stream=True, timeout=60,
                             headers={"User-Agent": "OpenLauncher/1.0"})
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=128 * 1024):
                    if chunk:
                        f.write(chunk)
            if is_valid_jar(dest):
                self.log(f"CustomSkinLoader installed: {filename}", "SUCCESS")
                # Register in profile mods list so the UI shows it
                profile = self.profile_manager.get_profile(
                    instance_dir.name)  # profile_name == instance dir name
                if profile is not None:
                    mods = profile.get("mods", [])
                    if str(dest) not in mods:
                        mods.append(str(dest))
                        self.profile_manager.update_profile(
                            instance_dir.name, mods=mods)
            else:
                dest.unlink(missing_ok=True)
                self.log("Downloaded CSL jar is corrupt, removed.", "WARNING")
        except Exception as e:
            self.log(f"Failed to download CustomSkinLoader: {e}", "ERROR")
            if dest.exists():
                dest.unlink(missing_ok=True)

    def _deploy_csl_local_skin(self, instance_dir, username, skin_path):
        """
        Copy the skin PNG into CustomSkinLoader's LocalSkin folder.
        CSL reads from: <game_dir>/CustomSkinLoader/LocalSkin/skins/<USERNAME>.png
        Works fully offline with no config changes needed.
        """
        local_skin_dir = instance_dir / "CustomSkinLoader" / "LocalSkin" / "skins"
        local_skin_dir.mkdir(parents=True, exist_ok=True)
        dest = local_skin_dir / f"{username}.png"
        try:
            shutil.copy2(skin_path, dest)
            self.log(f"Skin deployed to CSL LocalSkin: {dest}", "SUCCESS")
        except Exception as e:
            self.log(f"Failed to deploy skin to CSL LocalSkin: {e}", "ERROR")


    def _do_launch(self, version, username, profile_name, modloader, modloader_version):
        stdout_log = []
        stderr_log = []
        exit_code = 0

        try:
            profile = self.profile_manager.get_profile(profile_name)
            memory = int(profile.get("memory", "2048"))
            custom_jvm = profile.get("jvm_args", "")

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

            # --- Inject custom splash ---
            self._inject_splash_into_jar(client_path)

            # Download assets
            self._download_assets(version_json, assets_dir)
            vanilla_cp_entries_abs = self._download_libraries(version_json, libraries_dir, client_path)
            self._extract_natives(libraries_dir, natives_dir)

            main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")
            modloader_cp_entries_abs = []
            if modloader != "None":
                self.log(f"Processing mod loader: {modloader}")
                if modloader == "Fabric":
                    main_class, modloader_cp_entries_abs = download_fabric(version, modloader_version, instance_dir, self.log)
                elif modloader == "Quilt":
                    main_class, modloader_cp_entries_abs = download_quilt(version, modloader_version, instance_dir, self.log)
                else:
                    raise Exception(f"Unsupported mod loader: {modloader}")

            # --- Auto-install CustomSkinLoader ---
            if modloader != "None":
                self._ensure_csl_installed(instance_dir, version, modloader)

            # --- Classpath ---
            cp_entries_abs = []
            for entry in (modloader_cp_entries_abs + vanilla_cp_entries_abs):
                if os.path.isfile(entry) and is_valid_jar(entry):
                    cp_entries_abs.append(entry)
                elif os.path.isfile(entry):
                    self.log(f"Skipping corrupt jar: {entry}", "WARNING")

            cp_entries = []
            for entry in cp_entries_abs:
                try:
                    rel = Path(entry).relative_to(instance_dir)
                    cp_entries.append(str(rel))
                except ValueError:
                    cp_entries.append(entry)

            classpath_file = instance_dir / "classpath.txt"
            cp_str = os.pathsep.join(cp_entries)
            with open(classpath_file, "w", encoding="utf-8") as f:
                f.write(cp_str)
            self.log(f"Classpath written to {classpath_file}", "INFO")
            cp_arg = f"@{classpath_file.absolute()}"

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

            # Build JVM args
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

            # Extra flags
            jvm_args.append("--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED")
            jvm_args.append("--enable-native-access=ALL-UNNAMED")
            jvm_args.append("-Dorg.lwjgl.system.jemalloc.disable=true")
            jvm_args.append("-Dorg.lwjgl.util.DisableLWJGLThreadLocal=true")
            jvm_args.append("-Drealms.enabled=false")
            jvm_args.append("-XX:-PrintWarnings")
            jvm_args.append("-XX:+UnlockDiagnosticVMOptions")
            jvm_args.append("-XX:-DisplayVMOutputToStderr")
            jvm_args.append(f"-Djava.library.path={natives_dir}")
            jvm_args.append(f"-Dorg.lwjgl.librarypath={natives_dir}")

            if version in ("1.16.5", "1.17.1"):
                jvm_args.append("-Dorg.lwjgl.util.Debug=true")
                jvm_args.append("-Dorg.lwjgl.util.DebugLoader=true")
                jvm_args.append("-Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true")
                jvm_args.append("-Dorg.lwjgl.opengl.Window.allowSoftwareOpenGL=true")

            # Build game args
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

            # ---------- SKIN INJECTION (CSL LocalSkin method) ----------
            account_name = profile.get("account")
            if account_name:
                skin_path = self.account_manager.get_skin(account_name)
                if skin_path and os.path.isfile(skin_path):
                    self._deploy_csl_local_skin(instance_dir, username, skin_path)
                else:
                    self.log(f"No valid skin for account '{account_name}'.", "DEBUG")
            # ---------------------------------------------------------------

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

            self.log("Launching Minecraft...")
            kwargs = get_subprocess_kwargs()
            process = subprocess.Popen(
                cmd,
                cwd=str(instance_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                **kwargs
            )

            # Capture output
            stdout_full = []
            stderr_full = []

            def read_stdout():
                for line in process.stdout:
                    self.log(f"[STDOUT] {line.rstrip()}", "INFO")
                    stdout_full.append(line)

            def read_stderr():
                skip_patterns = ["WARNING", "Unsafe", "LWJGL", "JNI", "deprecated", "objectFieldOffset", "Unsupported JNI version"]
                for line in process.stderr:
                    if any(pattern in line for pattern in skip_patterns):
                        continue
                    self.log(f"[STDERR] {line.rstrip()}", "ERROR")
                    stderr_full.append(line)

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            exit_code = process.wait()
            stdout_log = ''.join(stdout_full)
            stderr_log = ''.join(stderr_full)

            self.log(f"Minecraft exited with code: {exit_code}")
            if exit_code != 0:
                self.log(f"Non-zero exit code {exit_code}.", "ERROR")
                crash_file = self._save_crash_log(instance_dir, stdout_log, stderr_log, exit_code)
                if self.progress:
                    self._show_crash_dialog(exit_code, instance_dir, crash_file)
            else:
                self.log("Minecraft exited normally.", "SUCCESS")

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
        finally:
            if self.progress:
                self.progress(0, "Ready")

    # ---------- Crash log saving ----------
    def _save_crash_log(self, instance_dir, stdout_log, stderr_log, exit_code):
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = instance_dir / f"crash_{timestamp}.log"
        with open(crash_file, "w", encoding="utf-8") as f:
            f.write(f"Minecraft crashed with exit code: {exit_code}\n")
            f.write("=" * 60 + "\n")
            f.write("STDOUT:\n")
            f.write(stdout_log)
            f.write("\n" + "=" * 60 + "\n")
            f.write("STDERR:\n")
            f.write(stderr_log)
        return crash_file

    def _show_crash_dialog(self, exit_code, instance_dir, crash_file):
        if self.progress:
            self.progress(0, ("crash", exit_code, instance_dir, crash_file))

    # ---------- Splash injection ----------
    def _inject_splash_into_jar(self, jar_path):
        splash_path = "assets/minecraft/texts/splashes.txt"
        new_content = "OpenLauncher On Top!\n"

        try:
            with zipfile.ZipFile(jar_path, 'r') as zf:
                if splash_path in zf.namelist():
                    existing = zf.read(splash_path).decode('utf-8')
                    if existing.strip() == new_content.strip():
                        self.log("Splash already modified.", "INFO")
                        return
        except:
            pass

        try:
            with open(jar_path, 'a') as f:
                pass
        except PermissionError:
            self.log("Client JAR is locked (probably in use). Skipping splash injection.", "WARNING")
            return
        except Exception as e:
            self.log(f"Could not check JAR writability: {e}", "WARNING")
            return

        self.log("Modifying client JAR to change splash text...", "INFO")
        temp_jar = jar_path.with_suffix(".tmp.jar")
        try:
            shutil.copy2(jar_path, temp_jar)
            with zipfile.ZipFile(temp_jar, 'a') as zf:
                zf.writestr(splash_path, new_content)
            shutil.move(temp_jar, jar_path)
            self.log("Client JAR modified successfully.", "SUCCESS")
        except PermissionError:
            self.log("Client JAR became locked during modification. Skipping.", "WARNING")
            if temp_jar.exists():
                temp_jar.unlink()
        except Exception as e:
            self.log(f"Failed to modify JAR: {e}", "ERROR")
            if temp_jar.exists():
                shutil.move(temp_jar, jar_path)

    # ---------- Asset download with retry ----------
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

        self.log(f"Downloading {len(tasks)} assets with retry...")
        session = requests.Session()
        failed = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_task = {
                executor.submit(self._download_file_with_retry, url, dest, session): (url, dest)
                for url, dest in tasks
            }
            for future in as_completed(future_to_task):
                url, dest = future_to_task[future]
                try:
                    future.result()
                except Exception as e:
                    self.log(f"Failed to download {dest.name}: {e}", "WARNING")
                    failed.append((url, dest))

        if failed:
            self.log(f"{len(failed)} assets failed after retries. They may be missing.", "WARNING")

        self.log("Asset download phase complete.")

    def _download_file_with_retry(self, url, dest_path, session, max_retries=3):
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = 2 ** (attempt - 1)
                    time.sleep(delay)
                self._download_file_fast(url, dest_path, session)
                return
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise e
                else:
                    self.log(f"Retry {attempt+1}/{max_retries} for {dest_path.name}", "WARNING")
        raise Exception("Download failed after retries.")

    # ---------- Helpers ----------
    def _fetch_manifest(self):
        return self._fetch_json("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")

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

    def _download_file_fast(self, url, dest_path, session):
        response = session.get(url, stream=True)
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)

    def _download_libraries(self, version_json, libraries_dir, client_path):
        libraries = version_json.get("libraries", [])
        cp_entries_abs = [str(client_path)]
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
                cp_entries_abs.append(str(lib_path))
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
        return cp_entries_abs

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

    # ---------- Auto-Java download ----------
    def _download_java(self, required_major):
        self.log(f"Attempting to download Java {required_major}...", "INFO")
        system = platform.system()
        arch = platform.machine()
        if system == "Windows":
            os_name = "windows"
            ext = "zip"
            if arch == "AMD64" or arch == "x86_64":
                arch_name = "x64"
            else:
                arch_name = "x86"
        elif system == "Linux":
            os_name = "linux"
            ext = "tar.gz"
            if arch == "x86_64" or arch == "amd64":
                arch_name = "x64"
            elif "aarch64" in arch:
                arch_name = "aarch64"
            else:
                arch_name = "x86"
        elif system == "Darwin":
            os_name = "mac"
            ext = "tar.gz"
            if arch == "x86_64":
                arch_name = "x64"
            else:
                arch_name = "aarch64"
        else:
            self.log(f"Unsupported OS: {system}", "ERROR")
            return None

        api_url = f"https://api.adoptium.net/v3/assets/version/{required_major}/{os_name}/{arch_name}/jre/hotspot/normal"
        self.log(f"Querying Java download: {api_url}", "INFO")
        try:
            resp = requests.get(api_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                self.log("No Java binaries found.", "ERROR")
                return None
            binary = data[0]
            download_url = None
            for pkg in binary.get("binaries", []):
                if pkg.get("image_type") == "jre":
                    for link in pkg.get("package", {}).get("link", []):
                        if link.get("rel") == "direct":
                            download_url = link.get("href")
                            break
                    if download_url:
                        break
            if not download_url:
                self.log("No direct download URL found.", "ERROR")
                return None

            self.log(f"Downloading Java from {download_url}...", "INFO")
            dest_folder = self.java_download_dir / f"jdk-{required_major}"
            if dest_folder.exists() and (dest_folder / "bin").exists():
                self.log(f"Java {required_major} already downloaded.", "INFO")
                return str(dest_folder / "bin")

            import tempfile
            fd, temp_file = tempfile.mkstemp(suffix=f".{ext}")
            os.close(fd)
            try:
                response = requests.get(download_url, stream=True)
                response.raise_for_status()
                total = int(response.headers.get('content-length', 0))
                done = 0
                with open(temp_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            done += len(chunk)
                            if total > 0:
                                pct = (done / total) * 100
                                if int(pct) % 10 == 0:
                                    self.log(f"Java download: {int(pct)}%", "INFO")
                self.log("Java downloaded, extracting...", "INFO")
                if ext == "zip":
                    with zipfile.ZipFile(temp_file, 'r') as zf:
                        zf.extractall(self.java_download_dir)
                else:
                    import tarfile
                    with tarfile.open(temp_file, 'r:gz') as tf:
                        tf.extractall(self.java_download_dir)
                extracted_dirs = [d for d in self.java_download_dir.iterdir() if d.is_dir()]
                for d in extracted_dirs:
                    if (d / "bin").exists():
                        final_dir = self.java_download_dir / f"jdk-{required_major}"
                        if final_dir.exists():
                            shutil.rmtree(final_dir)
                        shutil.move(str(d), str(final_dir))
                        self.log(f"Java extracted to {final_dir}", "SUCCESS")
                        return str(final_dir / "bin")
                self.log("Could not locate extracted Java bin directory.", "ERROR")
                return None
            finally:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
        except Exception as e:
            self.log(f"Java download failed: {e}", "ERROR")
            return None

    # ---------- Java detection with auto-download ----------
    def _ensure_java_for_version(self, version, profile_name):
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

        self.log(f"Java {required_major} not found. Attempting to download...", "WARNING")
        import tkinter.messagebox as msg
        ans = msg.askyesno(
            "Java Missing",
            f"Java {required_major} is required but not found.\n\n"
            "Would you like to download and install it automatically?\n"
            "(This will download about 50-80 MB from Adoptium.)"
        )
        if ans:
            bin_path = self._download_java(required_major)
            if bin_path:
                self.log(f"Java installed at {bin_path}.", "SUCCESS")
                self.profile_manager.update_profile(profile_name, java_path=bin_path)
                return bin_path
            else:
                self.log("Java download failed.", "ERROR")
                msg.showerror("Download Failed", "Could not download Java. Please install it manually.")
        else:
            self.log("User declined auto-download. Prompting for manual selection.", "INFO")
            ans2 = msg.askyesno(
                "Java Not Found",
                f"Java {required_major} not found.\n\n"
                "Browse manually?\n"
                "If not installed, download from:\n"
                f"https://adoptium.net/temurin/releases/?version={required_major}"
            )
            if ans2:
                from tkinter import filedialog
                ft = [("Java executable", "java.exe"), ("Java", "java")] if platform.system() != "Windows" else [("Java executable", "java.exe")]
                path = filedialog.askopenfilename(title="Select Java", filetypes=ft)
                if path and os.path.isfile(path):
                    try:
                        kwargs = get_subprocess_kwargs()
                        result = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5, **kwargs)
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
        if profile_name:
            profile = self.profile_manager.get_profile(profile_name)
            if profile and profile.get("java_path"):
                java_path = profile["java_path"]
                if os.path.isfile(java_path):
                    kwargs = get_subprocess_kwargs()
                    try:
                        result = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=5, **kwargs)
                        output = result.stderr + result.stdout
                        match = re.search(r'version "(\d+)\.', output) or re.search(r'version "(\d+)-', output)
                        if match:
                            major_ver = int(match.group(1))
                            if (required_major == 8 and (major_ver == 1 or major_ver == 8)) or (required_major > 8 and major_ver >= required_major):
                                return java_path
                    except:
                        pass

        auto_java_bin = self.java_download_dir / f"jdk-{required_major}" / "bin"
        if auto_java_bin.exists():
            exe = auto_java_bin / ("java.exe" if platform.system() == "Windows" else "java")
            if exe.exists():
                self.log(f"Found auto-downloaded Java at {exe}", "DEBUG")
                return str(exe)

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
        kwargs = get_subprocess_kwargs()
        for java_path in candidates:
            try:
                result = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=5, **kwargs)
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
        versioned.sort(key=lambda x: (x[0], 0 if x[1] == "adoptium" else (1 if x[1] == "openjdk" else 2)), reverse=True)

        for major, vendor, path in versioned:
            if (required_major == 8 and (major == 1 or major == 8)) or (required_major > 8 and major >= required_major):
                return path
        return None