# OpenLauncher

OpenLauncher is a modern, open-source Minecraft launcher with a dark GUI, offline skin support, and automatic mod-loader management.

## Features

- Launch any Minecraft version (1.8 – 1.21+) with Fabric or Quilt.
- Multiple profiles – each with its own mods, resource packs, JVM args, and memory.
- Offline skin system – assign a PNG skin to any account; the launcher automatically installs CustomSkinLoader and deploys it via the LocalSkin folder. Works fully offline.
- Auto-downloads game assets, libraries, and Fabric/Quilt loaders.
- Auto-Java detection and installation (Adoptium).
- Mod, resource-pack, and world management (backup/restore).
- Cross-platform (Windows, Linux, macOS).

## Requirements

- Python 3.10+
- Internet connection (first-run downloads)
- Java 8/17/21 (auto-downloadable)

## Installation

1. Clone or download this repository.
2. Install required packages:
   pip install customtkinter requests
3. Run the launcher:
   python main.py

## Quick Start

1. Accounts tab – add an account (username). Select a skin PNG – the launcher copies it to accounts/skins/.
2. Profiles panel – click ＋ Add to create a new profile. Choose a Minecraft version, mod loader (Fabric/Quilt recommended for skins), and assign an account.
3. Launch – select the profile and click ▶ Launch. The launcher downloads everything needed and automatically installs CustomSkinLoader (if using Fabric/Quilt). Your skin appears in-game.

## Skin System (CustomSkinLoader)

- The launcher installs CustomSkinLoader automatically for Fabric/Quilt profiles.
- It copies your skin to:
  <instance>/CustomSkinLoader/LocalSkin/skins/<username>.png
- The mod loads it at runtime – no configuration needed.
- If the auto-download fails, manually place a CustomSkinLoader Fabric jar in the instance's mods/ folder.

## Configuration

- Mods – add/remove .jar files in the Mods tab.
- Resource Packs – add/remove .zip packs.
- Worlds – open the saves folder, backup/restore worlds.
- Java – adjust memory (512–8192 MB) and add custom JVM flags (e.g., -XX:+UseG1GC).

## Troubleshooting

Issue: Skin not showing
Solution: Use a Fabric/Quilt profile. Check the log for “Skin deployed to CSL LocalSkin”. If CustomSkinLoader isn't installed, download it manually from https://modrinth.com/mod/customskinloader/versions and place it in mods/.

Issue: Java missing
Solution: The launcher will prompt to auto-download. You can also set JAVA_HOME or manually select a Java executable in the profile editor.

Issue: Game crashes
Solution: Increase memory, remove incompatible mods, or check the crash log.

## Project Structure

OpenLauncher/
├── main.py              # GUI entry point
├── launcher_core.py     # Core launch logic
├── account_manager.py   # Account + skin storage
├── profile_manager.py   # Profile storage
├── downloaders.py       # Fabric/Quilt download
├── helpers.py           # Utility functions
├── ui_tabs.py           # GUI tabs
└── README.md

## Credits

- CustomSkinLoader by xfl03 (https://github.com/xfl03/CustomSkinLoader)
- FabricMC, QuiltMC, Mojang

## License

MIT – free to use and modify.
