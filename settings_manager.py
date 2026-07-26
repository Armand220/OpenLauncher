import json
from pathlib import Path

SETTINGS_FILE = "settings.json"

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