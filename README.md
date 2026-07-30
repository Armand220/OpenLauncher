-------------------------------------------------------------------------------
OpenLauncher v4.0 Beta
-------------------------------------------------------------------------------

A free, open‑source offline Minecraft launcher. No Microsoft account required.
Works entirely offline after the first download.

GitHub: https://github.com/Armand220/OpenLauncher

-------------------------------------------------------------------------------
Features
-------------------------------------------------------------------------------

  - Offline mode – launch Minecraft without a Microsoft account.
  - Profile management – create, edit, delete separate profiles.
  - Mod loader support – Fabric, Quilt, and vanilla.
  - Mod manager – add/remove mod JARs per profile.
  - Resource pack manager – add/remove resource pack ZIPs per profile.
  - World manager – list, backup, restore worlds.
  - Java settings – per‑profile memory (512 MB – 8 GB) and custom JVM args.
  - Auto Java detection – finds Java 8, 11, 16, 17, 21, 25.
  - Auto‑Java download – if missing, the launcher can download it from Adoptium.
  - Portable – the entire `minecraft_offline` folder can be moved between PCs.
  - Crash reporting – detailed dialog with copy log and open folder options.
  - Splash easter egg – title screen says “OpenLauncher On Top!”.
  - Work directory change warning – prevents accidental loss of instances.

-------------------------------------------------------------------------------
Requirements
-------------------------------------------------------------------------------

  - Python 3.8 or higher – download from python.org.
  - Python modules: requests, customtkinter, pillow.
    Install with:
      pip install requests customtkinter pillow
  - Java Runtime (JRE) or JDK – versions 8, 11, 16, 17, 21, 25.
    The launcher can auto‑download Java if missing.
  - Internet connection – only needed on first launch (to download game files).
  - Graphics drivers supporting OpenGL 3.2+ (for 1.16.5+).

-------------------------------------------------------------------------------
Installation
-------------------------------------------------------------------------------

From Source (for developers):
  git clone https://github.com/Armand220/OpenLauncher.git
  cd OpenLauncher
  pip install -r requirements.txt   # or install manually
  python main.py

Standalone Executable (Windows):
  Download the latest OpenLauncher.exe from the Releases page on GitHub.
  Run it – no Python or extra dependencies required.

-------------------------------------------------------------------------------
How to Use
-------------------------------------------------------------------------------

  1. Launch the application (main.py or OpenLauncher.exe).
  2. Add a Profile:
       - Give it a name (e.g., “Survival 1.21.1”).
       - Choose a Minecraft version (e.g., 1.21.1, 1.21.11, or snapshot 26.1).
       - Pick a mod loader: None (vanilla), Fabric, or Quilt.
       - Optionally set a loader version (leave blank for the latest).
  3. Select the profile from the list on the right.
  4. Configure mods, resource packs, worlds, or Java memory via the tabs.
  5. Click Launch – the first launch will download all necessary files.
  6. Subsequent launches are instant.

-------------------------------------------------------------------------------
Supported Mod Loaders
-------------------------------------------------------------------------------

  Vanilla (None)  – Working – No mods, pure Minecraft.
  Fabric          – Working – Latest versions and snapshots.
  Quilt           – Working – Latest versions and snapshots.

Note: Forge is not supported. Use a dedicated Forge launcher for modpacks.

-------------------------------------------------------------------------------
Supported Minecraft Versions
-------------------------------------------------------------------------------

  Version    Status    Java Required   Notes
  1.8.9      Partial   Java 8          May need manual deletion of launcher_profiles.json
  1.12.2     Working   Java 8          Fully functional
  1.16.5     Unstable  Java 8/11       Crashes on many systems (GLFW/OpenGL issue)
  1.17.1     Unstable  Java 16/17      Same crash as 1.16.5
  1.21.1     Working   Java 17/21      Tested and stable
  1.21.11    Working   Java 21         Works with Fabric/Quilt
  26.1       Working   Java 25         Auto‑detects Java 25 if installed

Why 1.16.5 and 1.17.1 crash:
  These versions use LWJGL 3.2.1 which heavily depends on GPU OpenGL support.
  Update your graphics drivers. As a workaround, add these JVM flags:
    -Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true
    -Dorg.lwjgl.opengl.Window.allowSoftwareOpenGL=true

-------------------------------------------------------------------------------
Known Issues
-------------------------------------------------------------------------------

  1. 1.16.5 and 1.17.1 crashes – see explanation above.
  2. 1.8.9 JSON parse errors – the launcher tries to delete the corrupt file.
     If it fails, delete launcher_profiles.json manually from your .minecraft.
  3. Java not found – if auto‑download fails, set the path manually in Edit Profile.
  4. Slow downloads – Mojang's CDN can be slow; retry later.

-------------------------------------------------------------------------------
Building from Source (for Developers)
-------------------------------------------------------------------------------

  All Python files must be in the same folder:
    main.py, helpers.py, settings_manager.py, profile_manager.py,
    downloaders.py, launcher_core.py, ui_tabs.py

  To build a single .exe:
    pip install pyinstaller
    python -m PyInstaller --onefile --windowed --name OpenLauncher main.py

  The .exe will be in the 'dist' folder.

  Note: Some anti‑virus engines may flag the .exe – this is a FALSE POSITIVE
  caused by PyInstaller's bootloader. The source code is fully open and contains
  no malware.

-------------------------------------------------------------------------------
Contributing
-------------------------------------------------------------------------------

  We welcome contributions! Report bugs, suggest features, or submit pull requests.
  Steps:
    1. Fork the repository.
    2. Create a feature branch.
    3. Commit your changes.
    4. Push and open a Pull Request.

-------------------------------------------------------------------------------
License
-------------------------------------------------------------------------------

  This project is licensed under the MIT License – you are free to use, modify,
  and distribute it, provided you include the original license.

-------------------------------------------------------------------------------
Disclaimer
-------------------------------------------------------------------------------

  This launcher is intended for educational purposes only.
  It does not bypass purchase requirements; you must already own a legitimate
  copy of Minecraft. It works exclusively in offline mode – you cannot join
  premium (online‑mode=true) servers.

  OpenLauncher is not affiliated with Mojang Studios or Microsoft.

-------------------------------------------------------------------------------
Contact & Support
-------------------------------------------------------------------------------

  GitHub: https://github.com/Armand220/OpenLauncher
  Issues: https://github.com/Armand220/OpenLauncher/issues

-------------------------------------------------------------------------------
Happy crafting! 🎮
-------------------------------------------------------------------------------
