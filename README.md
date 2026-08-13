# OpenLauncher v6.0 Beta

OpenLauncher is a modern, open-source Minecraft launcher with a dark GUI, offline skin support, Forge/Fabric/Quilt mod-loader management, and no Microsoft account required.

## Features

- Launch any Minecraft version (1.8 – 1.21+) with Vanilla, Fabric, Quilt, or Forge.
- Multiple profiles, each with its own mods, resource packs, JVM args, and memory.
- Offline skin system – assign a PNG skin to any account; it is injected in-game without any mod.
- Auto-downloads game assets, libraries, and mod-loader installers.
- Auto-Java detection and installation (Adoptium). Handles 32-bit Java limits automatically.
- Mod, resource-pack, and world management (backup/restore).
- Portable – all game files are stored next to the launcher, no fixed install path.

## Requirements

- Python 3.10+ (source) or the standalone `OpenLauncher.exe` (no Python needed)
- Internet connection (first-run downloads)
- Java 8 / 17 / 21 (auto-downloadable if missing)

## Installation (source)

1. Clone or download this repository.
2. Install required packages:
   ```
   pip install customtkinter requests
   ```
3. Run the launcher:
   ```
   python main.py
   ```

## Quick Start

1. **Accounts tab** – add an account (username). Optionally select a skin PNG; it is copied into `minecraft_offline/accounts/skins/`.
2. **Profiles panel** – click Add to create a new profile. Choose a Minecraft version, mod-loader, memory, and assign an account.
3. **Launch** – select the profile and click Launch. Everything downloads automatically on first run.

## Skin System

Skins are injected at launch without requiring a mod:

- The skin PNG is packed into a resource pack (`OpenLauncher_Skin.zip`) and activated in `options.txt`.
- For Fabric and Quilt profiles, CustomSkinLoader is also installed and configured to read from a local folder, giving better compatibility with player model rendering.
- Skin files are stored by filename only, so the launcher folder is fully portable across machines.

## Configuration

- **Mods** – add/remove `.jar` files in the Mods tab.
- **Resource Packs** – add/remove `.zip` packs.
- **Worlds** – open the saves folder, backup/restore worlds.
- **Java** – adjust memory (512–8192 MB) and add custom JVM flags.

## Troubleshooting

**Skin not showing**
Check that a skin PNG is assigned to the account in the Accounts tab. The Console tab will show `Skin resource pack created and activated` on a successful injection.

**Out of memory / VM initialisation failed**
The launcher automatically caps memory to 75% of available RAM. If you are on 32-bit Java the cap is 512 MB. Lower the memory in the profile editor or install 64-bit Java 8 from [Adoptium](https://adoptium.net).

**Singleplayer worlds not loading**
This can happen if the game folder path contains spaces and an old Minecraft version is used. Update to the latest launcher build; the argument parsing fix is included from v6.0 Beta onward.

**Java missing**
The launcher will prompt to auto-download Adoptium Java. You can also browse to a Java executable manually in the prompt.

**Game crashes**
Check the Console tab for the full output. A `launch_command.bat` is written inside the instance folder for manual debugging.

**Forge not installing**
Forge requires Java to run its installer processors. Ensure Java is available and the instance has enough disk space.

## Project Structure

```
OpenLauncher/
├── main.py              # GUI entry point
├── launcher_core.py     # Core launch logic and skin injection
├── account_manager.py   # Account and skin storage
├── profile_manager.py   # Profile storage
├── downloaders.py       # Fabric/Quilt/Forge downloaders
├── helpers.py           # Utility functions
├── ui_tabs.py           # GUI tabs (Mods, Resource Packs, Worlds, Java)
└── minecraft_offline/   # Created at runtime; all game data lives here
```

## License

MIT – free to use and modify.
