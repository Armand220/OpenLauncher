import requests
import time
import zipfile
import json
import os
import platform
import subprocess
import shutil
from pathlib import Path
from helpers import is_valid_jar

CHUNK_SIZE = 128 * 1024

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

# ------------------ QUILT IMPLEMENTATION ------------------
def fetch_quilt_meta(api_url):
    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except:
        return None

def get_latest_quilt_loader(mc_version):
    # Quilt meta API: /v3/versions/loader/<mc_version>
    url = f"https://meta.quiltmc.org/v3/versions/loader/{mc_version}"
    data = fetch_quilt_meta(url)
    if data and len(data) > 0:
        # The response is a list of loaders; we take the first (latest)
        return data[0]["loader"]["version"]
    return None

def download_quilt(mc_version, loader_version, instance_dir, log_func):
    log_func("Downloading Quilt loader...")
    if not loader_version:
        loader_version = get_latest_quilt_loader(mc_version)
        if not loader_version:
            raise Exception("Could not determine latest Quilt loader for " + mc_version)
        log_func(f"Using latest Quilt loader: {loader_version}")

    quilt_dir = instance_dir / "quilt"
    quilt_dir.mkdir(exist_ok=True)

    # Get the profile JSON (same as Fabric)
    loader_meta_url = f"https://meta.quiltmc.org/v3/versions/loader/{mc_version}/{loader_version}/profile/json"
    resp = requests.get(loader_meta_url, timeout=10)
    resp.raise_for_status()
    meta = resp.json()

    loader_jar_path = quilt_dir / f"quilt-loader-{loader_version}.jar"
    max_attempts = 2
    for attempt in range(max_attempts):
        if loader_jar_path.exists() and is_valid_jar(loader_jar_path):
            break
        if loader_jar_path.exists():
            log_func(f"Removing corrupted loader jar (attempt {attempt+1})...", "WARNING")
            loader_jar_path.unlink()
        # Quilt loader jar URL
        loader_url = f"https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-loader/{loader_version}/quilt-loader-{loader_version}.jar"
        log_func(f"Downloading Quilt loader jar...")
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
    libs_dir = quilt_dir / "libraries"
    libs_dir.mkdir(exist_ok=True)

    # Process libraries from meta
    for lib in meta.get("libraries", []):
        if "name" in lib:
            parts = lib["name"].split(":")
            if len(parts) >= 3:
                group, name, version = parts[0], parts[1], parts[2]
                # Skip quilt-loader itself (already added)
                if group == "org.quiltmc" and name == "quilt-loader":
                    continue
                jar_path = libs_dir / f"{name}-{version}.jar"
                if jar_path.exists() and not is_valid_jar(jar_path):
                    jar_path.unlink()
                    log_func(f"Removed corrupted library: {name}", "WARNING")
                classpath_entries.append(str(jar_path))
                if not jar_path.exists():
                    # Determine repository URLs
                    repos = []
                    if "url" in lib and "url" in lib.get("url", {}):
                        repos.append(lib["url"]["url"])
                    # Default repos for Quilt and Fabric (Quilt uses Fabric's Maven for some deps)
                    if group == "net.fabricmc":
                        repos.append("https://maven.fabricmc.net/")
                    if group.startswith("org.quiltmc"):
                        repos.append("https://maven.quiltmc.org/repository/release/")
                    if group == "org.ow2.asm":
                        repos.append("https://repo1.maven.org/maven2/")
                    if group == "org.spongepowered":
                        repos.append("https://repo.spongepowered.org/maven/")
                    # Always add Maven Central as fallback
                    repos.append("https://repo1.maven.org/maven2/")
                    # Remove duplicates while preserving order
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

    # Quilt may need newer ASM for Java 25; we can add it as a safety (similar to Fabric)
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
                if is_valid_jar(asm_jar):
                    log_func("ASM 9.8 downloaded successfully.")
                else:
                    asm_jar.unlink()
                    log_func("Failed to download valid ASM 9.8", "WARNING")
            else:
                log_func(f"Failed to download ASM 9.8 (HTTP {r.status_code})", "WARNING")
        except Exception as e:
            log_func(f"Error downloading ASM 9.8: {e}", "WARNING")
    if asm_jar.exists() and is_valid_jar(asm_jar):
        classpath_entries.insert(0, str(asm_jar))
        log_func("Added ASM 9.8 to classpath (prepended).")

    main_class = "org.quiltmc.loader.impl.launch.knot.KnotClient"
    return main_class, classpath_entries


# ==================== FORGE IMPLEMENTATION ====================

FORGE_MAVEN     = "https://maven.minecraftforge.net/"
MC_LIBRARIES    = "https://libraries.minecraft.net/"
MAVEN_CENTRAL   = "https://repo1.maven.org/maven2/"

def _maven_path(coord):
    """group:artifact:version[:classifier][@ext] -> relative Maven path."""
    ext = "jar"
    if "@" in coord:
        coord, ext = coord.rsplit("@", 1)
    parts = coord.split(":")
    group    = parts[0].replace(".", "/")
    artifact = parts[1]
    version  = parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    fname = f"{artifact}-{version}"
    if classifier:
        fname += f"-{classifier}"
    fname += f".{ext}"
    return f"{group}/{artifact}/{version}/{fname}"


def _get_recommended_forge_version(mc_version, log_func):
    try:
        resp = requests.get(
            "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
            timeout=10
        )
        resp.raise_for_status()
        promos = resp.json().get("promos", {})
        for suffix in ("recommended", "latest"):
            ver = promos.get(f"{mc_version}-{suffix}")
            if ver:
                return f"{mc_version}-{ver}"
    except Exception as e:
        log_func(f"Could not fetch Forge promotions: {e}", "WARNING")
    return None


def _fetch_forge_lib(coord, libs_dir, log_func):
    """Download a library by Maven coordinates, trying Forge/MC/Central in order."""
    path = _maven_path(coord)
    dest = libs_dir / path
    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    for base in [FORGE_MAVEN, MC_LIBRARIES, MAVEN_CENTRAL]:
        url = base + path
        try:
            r = requests.get(url, stream=True, timeout=30)
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                if dest.stat().st_size > 0:
                    return str(dest)
                dest.unlink()
        except Exception:
            pass
    log_func(f"Could not download: {coord}", "WARNING")
    return str(dest)


def _lib_allowed(lib):
    """Return False if the library's OS rules exclude the current platform."""
    rules = lib.get("rules", [])
    if not rules:
        return True
    cur_os = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}.get(
        platform.system(), "linux")
    allowed = False
    for rule in rules:
        action  = rule.get("action", "allow")
        os_name = rule.get("os", {}).get("name", "")
        if not os_name or os_name == cur_os:
            allowed = (action == "allow")
    return allowed


def _download_lib_entry(lib, libs_dir, log_func):
    """Download one library dict entry; return local path or None."""
    coord = lib.get("name", "")
    if not coord or not _lib_allowed(lib):
        return None
    artifact = lib.get("downloads", {}).get("artifact", {})
    if artifact and artifact.get("path"):
        dest = libs_dir / artifact["path"]
        if not dest.exists() or dest.stat().st_size == 0:
            dest.parent.mkdir(parents=True, exist_ok=True)
            url = artifact.get("url", "")
            if url:
                try:
                    r = requests.get(url, stream=True, timeout=30)
                    if r.ok:
                        with open(dest, "wb") as f:
                            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                                if chunk:
                                    f.write(chunk)
                except Exception as e:
                    log_func(f"Lib download failed ({coord}): {e}", "WARNING")
        return str(dest) if dest.exists() else None
    else:
        path = _fetch_forge_lib(coord, libs_dir, log_func)
        return path if Path(path).exists() else None


def _build_lib_map(libs_dir, install_profile):
    """coord -> local path for all install_profile libraries."""
    lib_map = {}
    for lib in install_profile.get("libraries", []):
        coord = lib.get("name", "")
        if not coord:
            continue
        artifact = lib.get("downloads", {}).get("artifact", {})
        if artifact and artifact.get("path"):
            lib_map[coord] = str(libs_dir / artifact["path"])
        else:
            lib_map[coord] = str(libs_dir / _maven_path(coord))
    return lib_map


def _run_forge_processors(install_profile, mc_version, instance_dir,
                           libs_dir, installer_path, java_path, log_func):
    """Run the Forge install processors (new-format Forge, 1.13+)."""
    lib_map = _build_lib_map(libs_dir, install_profile)

    # Ensure vanilla client is reachable at the nested path Forge expects
    mc_jar_flat   = instance_dir / "versions" / f"{mc_version}.jar"
    mc_jar_nested = instance_dir / "versions" / mc_version / f"{mc_version}.jar"
    if mc_jar_flat.exists() and not mc_jar_nested.exists():
        mc_jar_nested.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(mc_jar_flat), str(mc_jar_nested))
    mc_jar = mc_jar_nested if mc_jar_nested.exists() else mc_jar_flat

    # Resolve data substitution map
    data_map = {
        "{MINECRAFT_JAR}": str(mc_jar),
        "{INSTALLER}": str(installer_path),
        "{ROOT}": str(instance_dir),
        "{MINECRAFT_VERSION}": mc_version,
        "{LIBRARIES_DIR}": str(libs_dir),
        "{SIDE}": "client",
    }
    for key, val in install_profile.get("data", {}).items():
        client_val = val.get("client", "") if isinstance(val, dict) else str(val)
        if client_val.startswith("[") and client_val.endswith("]"):
            coord = client_val[1:-1]
            data_map[f"{{{key}}}"] = lib_map.get(coord,
                str(libs_dir / _maven_path(coord)))
        elif client_val.startswith("/"):
            out = instance_dir / "forge" / key
            try:
                with zipfile.ZipFile(installer_path, "r") as zf:
                    inner = client_val.lstrip("/")
                    if inner in zf.namelist():
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(zf.read(inner))
                        data_map[f"{{{key}}}"] = str(out)
            except Exception:
                pass
        else:
            data_map[f"{{{key}}}"] = client_val

    processors = install_profile.get("processors", [])
    for i, proc in enumerate(processors):
        sides = proc.get("sides", [])
        if sides and "client" not in sides:
            continue

        jar_coord = proc.get("jar", "")
        jar_path  = lib_map.get(jar_coord, str(libs_dir / _maven_path(jar_coord)))
        if not Path(jar_path).exists():
            log_func(f"Processor {i+1} jar missing: {jar_coord}", "WARNING")
            continue

        # Read main class from JAR manifest
        proc_main = None
        try:
            with zipfile.ZipFile(jar_path, "r") as zf:
                if "META-INF/MANIFEST.MF" in zf.namelist():
                    for line in zf.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace").splitlines():
                        if line.strip().startswith("Main-Class:"):
                            proc_main = line.split(":", 1)[1].strip()
                            break
        except Exception:
            pass
        if not proc_main:
            log_func(f"Processor {i+1}: no main class, skipping.", "WARNING")
            continue

        # Build classpath
        proc_cp = [jar_path]
        for cp_coord in proc.get("classpath", []):
            cp_path = lib_map.get(cp_coord, str(libs_dir / _maven_path(cp_coord)))
            if Path(cp_path).exists():
                proc_cp.append(cp_path)

        # Resolve args
        proc_args = []
        for arg in proc.get("args", []):
            resolved = arg
            for k, v in data_map.items():
                resolved = resolved.replace(k, v)
            if resolved.startswith("[") and resolved.endswith("]"):
                coord = resolved[1:-1]
                resolved = lib_map.get(coord, str(libs_dir / _maven_path(coord)))
            proc_args.append(resolved)

        cmd = [java_path, "-cp", os.pathsep.join(proc_cp), proc_main] + proc_args
        log_func(f"Processor {i+1}/{len(processors)}: {proc_main.split('.')[-1]}...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                     timeout=180, cwd=str(instance_dir))
            if result.returncode != 0:
                log_func(f"Processor {i+1} exit {result.returncode}: "
                         f"{(result.stderr or '')[:200]}", "WARNING")
        except subprocess.TimeoutExpired:
            log_func(f"Processor {i+1} timed out.", "WARNING")
        except Exception as e:
            log_func(f"Processor {i+1} error: {e}", "WARNING")


def download_forge(mc_version, forge_version_input, instance_dir, log_func, java_path="java"):
    """
    Download and install Forge, returning (main_class, classpath_entries).
    Handles both old-format (pre-1.13, universal JAR) and new-format (1.13+, processors).
    """
    forge_dir = instance_dir / "forge"
    forge_dir.mkdir(exist_ok=True)
    libs_dir = instance_dir / "libraries"
    libs_dir.mkdir(exist_ok=True)

    # Resolve version string
    if forge_version_input:
        forge_full = f"{mc_version}-{forge_version_input}"
    else:
        log_func("Looking up recommended Forge version...")
        forge_full = _get_recommended_forge_version(mc_version, log_func)
        if not forge_full:
            raise Exception(
                f"No recommended Forge version found for Minecraft {mc_version}. "
                "Specify a Forge version manually in the profile.")
        log_func(f"Using Forge {forge_full}")

    # Skip re-installing if already done and patched client exists
    marker = forge_dir / f".installed_{forge_full}"
    forge_client_jar = libs_dir / _maven_path(f"net.minecraftforge:forge:{forge_full}:client")
    if marker.exists() and forge_client_jar.exists():
        log_func(f"Forge {forge_full} already installed, loading...", "INFO")
        version_json_path = forge_dir / "version.json"
        if version_json_path.exists():
            with open(version_json_path) as f:
                version_json = json.load(f)
            main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")
            cp_entries = []
            for lib in version_json.get("libraries", []):
                p = _download_lib_entry(lib, libs_dir, log_func)
                if p:
                    cp_entries.append(p)
            return main_class, cp_entries, version_json
    if marker.exists():
        log_func("Forge installation incomplete (patched client missing), re-running processors...", "WARNING")
        marker.unlink()

    # Download installer JAR
    installer_path = forge_dir / f"forge-{forge_full}-installer.jar"
    if not installer_path.exists():
        url = (f"{FORGE_MAVEN}net/minecraftforge/forge/{forge_full}/"
               f"forge-{forge_full}-installer.jar")
        log_func(f"Downloading Forge installer ({forge_full})...")
        r = requests.get(url, stream=True, timeout=120)
        if not r.ok:
            raise Exception(f"Forge installer download failed: HTTP {r.status_code}\nURL: {url}")
        with open(installer_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
        log_func("Forge installer downloaded.", "SUCCESS")

    # Extract install_profile.json and version.json from installer
    with zipfile.ZipFile(installer_path, "r") as zf:
        names = zf.namelist()
        install_profile = json.loads(zf.read("install_profile.json")) if "install_profile.json" in names else {}
        version_json    = json.loads(zf.read("version.json"))          if "version.json" in names else None

        # Extract any bundled Maven libs (inside maven/ directory of installer)
        for n in names:
            if n.startswith("maven/") and not n.endswith("/"):
                rel  = n[len("maven/"):]
                dest = libs_dir / rel
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(n))

    # Old-format installer (pre-1.13): versionInfo embedded in install_profile
    if version_json is None:
        version_json = install_profile.get("versionInfo", {})
        # Extract the bundled universal JAR
        install_meta = install_profile.get("install", {})
        uni_file = install_meta.get("filePath", "")
        uni_coord = install_meta.get("path", "")
        if uni_file and uni_coord:
            uni_dest = libs_dir / _maven_path(uni_coord)
            if not uni_dest.exists():
                uni_dest.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(installer_path, "r") as zf:
                    if uni_file in zf.namelist():
                        uni_dest.write_bytes(zf.read(uni_file))
                        log_func(f"Extracted Forge universal JAR: {uni_dest.name}", "SUCCESS")

    if not version_json:
        raise Exception("Could not read Forge version JSON from installer.")

    # Save version.json for future re-use
    with open(forge_dir / "version.json", "w") as f:
        json.dump(version_json, f, indent=2)

    main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")

    # Download processor dependencies (new format only)
    if install_profile.get("processors"):
        log_func("Downloading Forge processor libraries...", "INFO")
        for lib in install_profile.get("libraries", []):
            _download_lib_entry(lib, libs_dir, log_func)

    # Download runtime libraries (from version.json)
    log_func("Downloading Forge runtime libraries...")
    cp_entries = []
    for lib in version_json.get("libraries", []):
        p = _download_lib_entry(lib, libs_dir, log_func)
        if p:
            cp_entries.append(p)

    # Run processors (new-format 1.13+)
    if install_profile.get("processors"):
        log_func("Running Forge install processors (this may take a minute)...", "INFO")
        _run_forge_processors(install_profile, mc_version, instance_dir,
                               libs_dir, installer_path, java_path, log_func)
        # Re-collect classpath entries after processors; processor-generated JARs
        # (e.g. forge-*-client.jar) didn't exist before and were skipped earlier.
        cp_entries = []
        for lib in version_json.get("libraries", []):
            p = _download_lib_entry(lib, libs_dir, log_func)
            if p:
                cp_entries.append(p)

    # Mark installation complete
    marker.touch()
    log_func(f"Forge {forge_full} installed successfully.", "SUCCESS")
    return main_class, cp_entries, version_json