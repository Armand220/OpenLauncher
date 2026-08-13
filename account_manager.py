import json
from pathlib import Path

ACCOUNTS_FILE = "accounts.json"

class AccountManager:
    def __init__(self, workdir):
        self.workdir = Path(workdir)
        self.accounts_path = self.workdir / ACCOUNTS_FILE
        self.accounts = self.load_accounts()

    def load_accounts(self):
        if self.accounts_path.exists():
            try:
                with open(self.accounts_path, "r") as f:
                    data = json.load(f)
                modified = False
                for acc in data:
                    if "name" not in acc:
                        acc["name"] = "Unknown"
                        modified = True
                    # Ensure skin key exists (even if empty)
                    if "skin" not in acc:
                        acc["skin"] = ""
                        modified = True
                if modified:
                    self.save_accounts()
                return data
            except:
                return []
        return []

    def save_accounts(self):
        with open(self.accounts_path, "w") as f:
            json.dump(self.accounts, f, indent=2)

    def get_accounts(self):
        return self.accounts

    def get_account_names(self):
        return [acc["name"] for acc in self.accounts]

    def add_account(self, name):
        if any(acc["name"].lower() == name.lower() for acc in self.accounts):
            return False
        self.accounts.append({"name": name, "skin": ""})
        self.save_accounts()
        return True

    def remove_account(self, name):
        original_len = len(self.accounts)
        self.accounts = [acc for acc in self.accounts if acc["name"] != name]
        if len(self.accounts) < original_len:
            self.save_accounts()
            return True
        return False

    def rename_account(self, old_name, new_name):
        for acc in self.accounts:
            if acc["name"] == old_name:
                acc["name"] = new_name
                self.save_accounts()
                return True
        return False

    def get_skin(self, name):
        """Return the absolute skin file path for the given account, or empty string."""
        for acc in self.accounts:
            if acc["name"] == name:
                stored = acc.get("skin", "")
                if not stored:
                    return ""
                stored_path = Path(stored)
                # If the stored value is already an absolute path that exists, use it.
                if stored_path.is_absolute() and stored_path.exists():
                    return str(stored_path)
                # Otherwise treat it as a filename relative to workdir/accounts/skins/
                relative = self.workdir / "accounts" / "skins" / stored_path.name
                if relative.exists():
                    return str(relative)
                return ""
        return ""

    def set_skin(self, name, skin_path):
        """Store the skin filename (not full path) for the account. Pass None or '' to remove."""
        for acc in self.accounts:
            if acc["name"] == name:
                if skin_path:
                    # Store only the filename so the path is portable across machines.
                    acc["skin"] = Path(skin_path).name
                else:
                    acc.pop("skin", None)
                self.save_accounts()
                return True
        return False