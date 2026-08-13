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
from downloaders import download_fabric, download_quilt, download_forge
from io import BytesIO

CHUNK_SIZE = 128 * 1024
REQUEST_RETRIES = 3
MAX_WORKERS = 20


def get_subprocess_kwargs(hide_window=True):
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        if hide_window:
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            return {
                "startupinfo": startupinfo,
                "creationflags": subprocess.CREATE_NO_WINDOW,
            }
        else:
            # For GUI processes (Minecraft): do not hide, show normally
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 1  # SW_SHOW
            return {"startupinfo": startupinfo}
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
        self._mc_process = None

    def launch(self, version, username, profile_name, modloader, modloader_version):
        self.log(f"Launching {version} with {modloader} as '{username}'")
        threading.Thread(target=self._do_launch, args=(version, username, profile_name, modloader, modloader_version), daemon=True).start()

    def stop(self):
        if self._mc_process:
            try:
                self._mc_process.terminate()
                self.log("Terminate signal sent to Minecraft.", "WARNING")
            except Exception as e:
                self.log(f"Could not terminate Minecraft: {e}", "ERROR")

    def repair_instance(self, version, profile_name):
        self.log(f"Starting repair for '{profile_name}' ({version})...", "INFO")
        threading.Thread(target=self._do_repair, args=(version, profile_name), daemon=True).start()

    def _do_repair(self, version, profile_name):
        try:
            instance_dir = self.workdir / "instances" / profile_name
            versions_dir = instance_dir / "versions"
            libraries_dir = instance_dir / "libraries"
            natives_dir = instance_dir / "natives"
            for d in [versions_dir, libraries_dir, natives_dir]:
                d.mkdir(parents=True, exist_ok=True)

            manifest = self._fetch_manifest()
            if not manifest:
                self.log("Repair failed: could not fetch manifest.", "ERROR")
                return
            version_info = next((v for v in manifest["versions"] if v["id"] == version), None)
            if not version_info:
                self.log(f"Repair failed: version {version} not found.", "ERROR")
                return
            version_json = self._fetch_version_json(version_info["url"])
            if not version_json:
                self.log("Repair failed: could not fetch version JSON.", "ERROR")
                return

            client_path = versions_dir / f"{version}.jar"
            if client_path.exists():
                client_path.unlink()
            self.log("Re-downloading client JAR...", "INFO")
            self._download_file(version_json["downloads"]["client"]["url"], client_path, silent=True)

            self.log("Re-downloading libraries...", "INFO")
            self._download_libraries(version_json, libraries_dir, client_path)
            self._extract_natives(libraries_dir, natives_dir)

            self.log(f"Repair complete for '{profile_name}'.", "SUCCESS")
        except Exception as e:
            self.log(f"Repair failed: {e}", "ERROR")
        finally:
            if self.progress:
                self.progress(0, "Ready")

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

    def _get_pack_format(self, mc_version):
        """Return the resource-pack format number for a Minecraft version string."""
        try:
            parts = mc_version.split(".")
            major = int(parts[1]) if len(parts) > 1 else 0
            minor = int(parts[2]) if len(parts) > 2 else 0
        except Exception:
            return 8
        if major <= 8:   return 1
        if major <= 10:  return 2
        if major <= 12:  return 3
        if major <= 14:  return 4
        if major == 15 or (major == 16 and minor <= 1): return 5
        if major == 16:  return 6
        if major == 17:  return 7
        if major == 18:  return 8
        if major == 19 and minor <= 2: return 9
        if major == 19 and minor == 3: return 11
        if major == 19:  return 12
        if major == 20 and minor <= 1: return 13
        if major == 20 and minor == 2: return 15
        if major == 20 and minor <= 4: return 18
        if major == 20:  return 22
        if major == 21 and minor <= 1: return 32
        if major == 21 and minor <= 3: return 34
        return 36

    def _inject_skin_resourcepack(self, instance_dir, skin_path, mc_version):
        """Write a resource pack containing the user's skin and activate it in options.txt.
        Returns True on success."""
        rp_dir = instance_dir / "resourcepacks"
        rp_dir.mkdir(exist_ok=True)
        rp_path = rp_dir / "OpenLauncher_Skin.zip"
        pack_format = self._get_pack_format(mc_version)

        try:
            with open(skin_path, "rb") as f:
                skin_data = f.read()

            with zipfile.ZipFile(rp_path, "w", compression=zipfile.ZIP_STORED) as z:
                mcmeta = {"pack": {"pack_format": pack_format, "description": "Custom skin"}}
                z.writestr("pack.mcmeta", json.dumps(mcmeta))
                # 1.9+ wide (Steve) and slim (Alex) model paths
                z.writestr("assets/minecraft/textures/entity/player/wide/steve.png", skin_data)
                z.writestr("assets/minecraft/textures/entity/player/wide/alex.png", skin_data)
                z.writestr("assets/minecraft/textures/entity/player/slim/steve.png", skin_data)
                z.writestr("assets/minecraft/textures/entity/player/slim/alex.png", skin_data)
                # 1.8 and below legacy paths
                z.writestr("assets/minecraft/textures/entity/steve.png", skin_data)
                z.writestr("assets/minecraft/textures/entity/alex.png", skin_data)
                z.writestr("assets/minecraft/textures/entity/char.png", skin_data)

            self._enable_resourcepack_in_options(instance_dir / "options.txt",
                                                 "file/OpenLauncher_Skin.zip")
            self.log("Skin resource pack created and activated.", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"Skin resource pack failed: {e}", "WARNING")
            return False

    def _enable_resourcepack_in_options(self, options_path, pack_name):
        """Add pack_name to resourcePacks and incompatibleResourcePacks in options.txt."""
        lines = []
        indices = {}  # key -> line index
        packs = {}    # key -> list

        keys = ("resourcePacks", "incompatibleResourcePacks")

        if options_path.exists():
            with open(options_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                for key in keys:
                    if line.startswith(key + ":"):
                        indices[key] = i
                        try:
                            packs[key] = json.loads(line[len(key) + 1:].strip())
                        except Exception:
                            packs[key] = []

        for key in keys:
            lst = packs.get(key, [])
            if pack_name not in lst:
                lst.append(pack_name)
            new_line = f"{key}:{json.dumps(lst)}\n"
            if key in indices:
                lines[indices[key]] = new_line
            else:
                lines.append(new_line)

        with open(options_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def _deploy_csl_local_skin(self, instance_dir, username, skin_path):
        csl_dir = instance_dir / "CustomSkinLoader"
        local_skin_dir = csl_dir / "LocalSkin" / "skins"
        local_skin_dir.mkdir(parents=True, exist_ok=True)

        # Write CSL config to use LocalSkin as the skin source
        config_path = csl_dir / "CustomSkinLoader.json"
        csl_config = {
            "enable": True,
            "loadlist": [
                {"name": "LocalSkin", "type": "LocalSkin"}
            ]
        }
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(csl_config, f, indent=2)
        except Exception as e:
            self.log(f"Failed to write CSL config: {e}", "WARNING")

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
            try:
                import ctypes as _ctypes
                class _MEMSTATUS(_ctypes.Structure):
                    _fields_ = [("dwLength", _ctypes.c_ulong),
                                ("dwMemoryLoad", _ctypes.c_ulong),
                                ("ullTotalPhys", _ctypes.c_ulonglong),
                                ("ullAvailPhys", _ctypes.c_ulonglong),
                                ("ullTotalPageFile", _ctypes.c_ulonglong),
                                ("ullAvailPageFile", _ctypes.c_ulonglong),
                                ("ullTotalVirtual", _ctypes.c_ulonglong),
                                ("ullAvailVirtual", _ctypes.c_ulonglong),
                                ("ullAvailExtendedVirtual", _ctypes.c_ulonglong)]
                _ms = _MEMSTATUS()
                _ms.dwLength = _ctypes.sizeof(_MEMSTATUS)
                _ctypes.windll.kernel32.GlobalMemoryStatusEx(_ctypes.byref(_ms))
                _available_mb = _ms.ullAvailPhys // (1024 * 1024)
            except Exception:
                _available_mb = None
            if _available_mb is not None:
                _cap_mb = int(_available_mb * 0.75)
                if memory > _cap_mb:
                    self.log(f"Requested {memory} MB but only {_available_mb} MB available. Capping at {_cap_mb} MB.", "WARNING")
                    memory = max(_cap_mb, 512)
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
            forge_version_json = None
            if modloader != "None":
                self.log(f"Processing mod loader: {modloader}")
                if modloader == "Fabric":
                    main_class, modloader_cp_entries_abs = download_fabric(version, modloader_version, instance_dir, self.log)
                elif modloader == "Quilt":
                    main_class, modloader_cp_entries_abs = download_quilt(version, modloader_version, instance_dir, self.log)
                elif modloader == "Forge":
                    main_class, modloader_cp_entries_abs, forge_version_json = download_forge(version, modloader_version, instance_dir, self.log, java_path)
                else:
                    raise Exception(f"Unsupported mod loader: {modloader}")

            # For 1.8.x, pre-create a valid launcher_profiles.json to prevent JSON parse crashes
            if version.startswith("1.8"):
                lp_path = instance_dir / "launcher_profiles.json"
                if not lp_path.exists():
                    try:
                        with open(lp_path, "w", encoding="utf-8") as f:
                            json.dump({"profiles": {}, "selectedProfile": "(Default)", "clientToken": "0"}, f)
                        self.log("Created launcher_profiles.json for 1.8.x", "INFO")
                    except Exception as e:
                        self.log(f"Could not create launcher_profiles.json: {e}", "WARNING")
                else:
                    try:
                        with open(lp_path, "r", encoding="utf-8") as f:
                            json.load(f)
                    except Exception:
                        self.log("launcher_profiles.json is corrupt, recreating...", "WARNING")
                        try:
                            with open(lp_path, "w", encoding="utf-8") as f:
                                json.dump({"profiles": {}, "selectedProfile": "(Default)", "clientToken": "0"}, f)
                        except Exception as e2:
                            self.log(f"Could not recreate launcher_profiles.json: {e2}", "WARNING")


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

            # Detect Java major version early so it can gate both the classpath
            # argument style and the JVM flags below.
            _java_major = 8
            _java_is_32bit = False
            try:
                import subprocess as _sp
                _r = _sp.run([java_path, "-version"], capture_output=True, text=True, timeout=5)
                _out = _r.stderr + _r.stdout
                import re as _re
                _m = _re.search(r'version "(\d+)[\._]', _out)
                if _m:
                    _java_major = int(_m.group(1))
                    if _java_major == 1:
                        _java_major = 8
                _java_is_32bit = "32-Bit" in _out or "(x86)" in java_path
            except Exception:
                pass
            self.log(f"Detected Java major version: {_java_major}", "DEBUG")
            if _java_is_32bit:
                self.log("32-bit Java detected. Capping memory at 512 MB to avoid VM initialisation failure.", "WARNING")
                memory = min(memory, 512)

            classpath_file = instance_dir / "classpath.txt"
            cp_str = os.pathsep.join(cp_entries)
            with open(classpath_file, "w", encoding="utf-8") as f:
                f.write(cp_str)
            self.log(f"Classpath written to {classpath_file}", "INFO")
            # @argfile is Java 9+ only; Java 8 must receive the classpath directly
            if _java_major >= 9:
                cp_arg = f"@{classpath_file.absolute()}"
            else:
                cp_arg = cp_str

            import uuid as _uuid_mod
            _offline_uuid = str(_uuid_mod.uuid3(
                _uuid_mod.UUID(int=0x6ba7b8109dad11d180b400c04fd430c8),
                "OfflinePlayer:" + username
            ))

            subs = {
                "${game_directory}": str(instance_dir),
                "${assets_root}": str(assets_dir),
                "${assets_index_name}": version_json.get("assetIndex", {}).get("id", version),
                "${version_name}": version,
                "${auth_player_name}": username,
                "${auth_uuid}": _offline_uuid,
                "${auth_access_token}": "offline",
                "${user_type}": "legacy",
                "${natives_directory}": str(natives_dir),
                "${launcher_name}": "OpenLauncher",
                "${launcher_version}": "1.0",
                "${clientid}": "00000000-0000-0000-0000-000000000000",
                "${auth_xuid}": "0000000000000000",
                "${version_type}": "release",
                "${user_properties}": "{}"
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

            # Java 9+ flags only
            if _java_major >= 9:
                jvm_args.append("--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED")
            if _java_major >= 17:
                jvm_args.append("--enable-native-access=ALL-UNNAMED")

            jvm_args.append("-Dorg.lwjgl.system.jemalloc.disable=true")
            jvm_args.append("-Dorg.lwjgl.util.DisableLWJGLThreadLocal=true")
            jvm_args.append("-Drealms.enabled=false")
            jvm_args.append("-XX:-PrintWarnings")
            jvm_args.append("-XX:+UnlockDiagnosticVMOptions")
            jvm_args.append("-XX:-DisplayVMOutputToStderr")
            jvm_args.append(f"-Djava.library.path={natives_dir}")
            jvm_args.append(f"-Dorg.lwjgl.librarypath={natives_dir}")
            jvm_args.append("-Djava.awt.headless=false")
            # Force LWJGL 2 to create the window on the primary display
            jvm_args.append("-Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=false")
            jvm_args.append("-Dorg.lwjgl.input.Mouse.allowNegativeMouseCoords=true")

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
                # Split on spaces first, then substitute so paths with spaces are kept intact.
                for token in version_json["minecraftArguments"].split():
                    for key, val in subs.items():
                        token = token.replace(key, val)
                    game_args.append(token)

            # Append Forge-specific game and JVM args from its version.json
            if forge_version_json:
                fargs = forge_version_json.get("arguments", {})
                for arg in fargs.get("game", []):
                    if isinstance(arg, str):
                        for key, val in subs.items():
                            arg = arg.replace(key, val)
                        game_args.append(arg)
                for arg in fargs.get("jvm", []):
                    if isinstance(arg, str):
                        for key, val in subs.items():
                            arg = arg.replace(key, val)
                        jvm_args.append(arg)

            # Ensure a window size is set; LWJGL 2 may not show the window without it
            if "--width" not in game_args:
                game_args += ["--width", "854", "--height", "480"]

            # ---------- SKIN INJECTION ----------
            account_name = profile.get("account")
            if account_name:
                skin_path = self.account_manager.get_skin(account_name)
                if skin_path and os.path.isfile(skin_path):
                    if modloader in ("Fabric", "Quilt"):
                        self._ensure_csl_installed(instance_dir, version, modloader)
                        self._deploy_csl_local_skin(instance_dir, username, skin_path)
                    # Resource pack fallback for Vanilla and Forge
                    self._inject_skin_resourcepack(instance_dir, skin_path, version)
                else:
                    self.log(f"No skin set for account '{account_name}'.", "DEBUG")
            # ---------------------------------------------------

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

            _launch_start = time.time()
            self.log("Launching Minecraft...")
            kwargs = get_subprocess_kwargs(hide_window=False)
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
            self._mc_process = process

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
                    # Never suppress exception lines regardless of content
                    is_exception = (line.startswith("Exception in") or
                                    line.startswith("Caused by:") or
                                    line.strip().startswith("at "))
                    if not is_exception and any(pattern in line for pattern in skip_patterns):
                        continue
                    self.log(f"[STDERR] {line.rstrip()}", "ERROR")
                    stderr_full.append(line)

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            exit_code = process.wait()
            self._mc_process = None
            _elapsed = int(time.time() - _launch_start)
            try:
                _prof = self.profile_manager.get_profile(profile_name)
                _prev = int(_prof.get("play_time_seconds", 0))
                self.profile_manager.update_profile(profile_name, play_time_seconds=_prev + _elapsed)
            except Exception:
                pass
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
            # Rewrite the JAR, replacing splashes.txt and stripping the code-signing
            # files (META-INF/*.SF / *.RSA / *.DSA). Without the .SF file Java's
            # JarVerifier does not attempt SHA-256 verification, so the modified
            # entry no longer triggers a SecurityException.
            with zipfile.ZipFile(jar_path, 'r') as src_zf, \
                 zipfile.ZipFile(temp_jar, 'w', compression=zipfile.ZIP_DEFLATED) as dst_zf:
                for item in src_zf.infolist():
                    name = item.filename
                    # Drop code-signing files
                    if name.upper().startswith("META-INF/") and name.upper().endswith((".SF", ".RSA", ".DSA")):
                        continue
                    # Replace splash with our version
                    if name == splash_path:
                        dst_zf.writestr(item, new_content.encode("utf-8"))
                    else:
                        dst_zf.writestr(item, src_zf.read(name))
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

        system = platform.system().lower()
        # Map platform to the natives classifier key used in version JSONs
        if system == "windows":
            native_key = "natives-windows"
        elif system == "darwin":
            native_key = "natives-osx"
        else:
            native_key = "natives-linux"

        for lib in libraries:
            downloads = lib.get("downloads", {})

            # Main artifact
            if "artifact" in downloads:
                path = downloads["artifact"]["path"]
                if "jemalloc" in path.lower():
                    continue
                url = downloads["artifact"]["url"]
                lib_path = libraries_dir / path
                if not lib_path.exists():
                    lib_path.parent.mkdir(parents=True, exist_ok=True)
                    tasks.append((url, lib_path))
                cp_entries_abs.append(str(lib_path))

            # Native classifier jar (contains the .dll / .so / .dylib files)
            classifiers = downloads.get("classifiers", {})
            native_classifier = classifiers.get(native_key)
            # Also try architecture-specific variant (e.g. natives-windows-64)
            if native_classifier is None:
                arch = platform.machine()
                bits = "64" if ("64" in arch or arch == "AMD64") else "32"
                native_classifier = classifiers.get(f"{native_key}-{bits}")
            if native_classifier:
                nat_path = native_classifier["path"]
                nat_url = native_classifier["url"]
                nat_lib_path = libraries_dir / nat_path
                if not nat_lib_path.exists():
                    nat_lib_path.parent.mkdir(parents=True, exist_ok=True)
                    tasks.append((nat_url, nat_lib_path))

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

        api_url = (
            f"https://api.adoptium.net/v3/assets/feature_releases/{required_major}/ga"
            f"?architecture={arch_name}&heap_size=normal&image_type=jre"
            f"&jvm_impl=hotspot&os={os_name}&page=0&page_size=1"
            f"&project=jdk&sort_method=DEFAULT&sort_order=DESC&vendor=eclipse"
        )
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
                    download_url = pkg.get("package", {}).get("link")
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