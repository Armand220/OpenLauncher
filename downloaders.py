import requests
import time
import zipfile
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