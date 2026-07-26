import json
from pathlib import Path

PROFILES_FILE = "profiles.json"
VALID_LOADER_NAMES = {"None", "Fabric", "Quilt"}

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
                    for key in ["mods", "resource_packs", "jvm_args", "memory"]:
                        if key not in prof:
                            if key in ["mods", "resource_packs"]:
                                prof[key] = []
                            elif key == "memory":
                                prof[key] = "2048"
                            else:
                                prof[key] = ""
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

    def add_profile(self, name, version, modloader="None", modloader_version="",
                    mods=None, resource_packs=None, jvm_args="", memory="2048"):
        if name in self.profiles:
            return False
        if modloader not in VALID_LOADER_NAMES:
            modloader = "None"
        self.profiles[name] = {
            "version": version,
            "modloader": modloader,
            "modloader_version": modloader_version,
            "mods": mods or [],
            "resource_packs": resource_packs or [],
            "jvm_args": jvm_args,
            "memory": memory,
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

    def update_profile(self, name, **kwargs):
        if name not in self.profiles:
            return False
        for key, val in kwargs.items():
            if key in self.profiles[name]:
                self.profiles[name][key] = val
        self.save_profiles()
        return True