# OpenLauncher v6.0 Beta

OpenLauncher is a modern, open-source Minecraft launcher with a dark GUI, offline skin support, Forge/Fabric/Quilt mod-loader management, and no Microsoft account required.

## Features

- Launch any Minecraft version (1.8 – 1.21+) with Vanilla, Fabric, Quilt, or Forge.
- Multiple profiles – each with its own mods, resource packs, JVM args, and memory.
- Offline skin system – assign a PNG skin to any account. The launcher starts a local skin proxy server so your skin appears in-game on any mod-loader, no mod required.
- Auto-downloads game assets, libraries, and mod-loader installers.
- Auto-Java detection and installation (Adoptium).
- Mod, resource-pack, and world management (backup/restore).
- Cross-platform (Windows, Linux, macOS).

## Requirements

- Python 3.10+
- Internet connection (first-run downloads)
- Java 8 / 17 / 21 (auto-downloadable)

## Installation

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

1. **Accounts tab** – add an account (username). Optionally select a skin PNG; the launcher copies it to `accounts/skins/`.
2. **Profiles panel** – click Add to create a new profile. Choose a Minecraft version, mod-loader, memory, and assign an account.
3. **Launch** – select the profile and click Launch. The launcher downloads everything needed automatically. If a skin is set, it will appear in-game via the local proxy skin server.

## Skin System

The launcher uses a local HTTP proxy server to inject skins without any mod:

- Before Minecraft launches, a lightweight skin server starts on a random local port.
- JVM flags redirect Minecraft's session/texture API calls to this server.
- The server returns the player's local skin PNG in Mojang's profile format.
- A resource pack containing the skin is also written as a secondary fallback.
- The proxy shuts down automatically when Minecraft exits.

This works on Vanilla, Fabric, Quilt, and Forge profiles.

## Configuration

- **Mods** – add/remove `.jar` files in the Mods tab.
- **Resource Packs** – add/remove `.zip` packs.
- **Worlds** – open the saves folder, backup/restore worlds.
- **Java** – adjust memory (512–8192 MB) and add custom JVM flags (e.g. `-XX:+UseG1GC`).

## Troubleshooting

**Skin not showing**
The proxy skin server should handle this automatically. Check the console for "Skin proxy server started". If it failed, ensure no firewall is blocking localhost connections.

**Java missing**
The launcher will prompt to auto-download Adoptium Java. You can also set `JAVA_HOME` or manually select a Java executable in the profile editor.

**Game crashes**
Increase memory, remove incompatible mods, or check the crash log in the Console tab. The full launch command is also written to `launch_command.bat` inside the instance folder for manual debugging.

**Forge not installing**
Forge requires Java to run its installer processors. Ensure Java is available and the instance has enough disk space.

## Project Structure

```
OpenLauncher/
├── main.py              # GUI entry point
├── launcher_core.py     # Core launch logic and skin proxy
├── account_manager.py   # Account and skin storage
├── profile_manager.py   # Profile storage
├── downloaders.py       # Fabric/Quilt/Forge downloaders
├── helpers.py           # Utility functions
├── ui_tabs.py           # GUI tabs (Mods, Resource Packs, Worlds, Java)
└── README.md
```

## License

MIT – free to use and modify.
