---------------------------------------------------------------------
OpenLauncher – Minecraft Offline Launcher
---------------------------------------------------------------------

A free, open‑source Python launcher for Minecraft that works entirely offline –
no Microsoft account required.

GitHub: https://github.com/Armand220/OpenLauncher


---------------------------------------------------------------------
Features
---------------------------------------------------------------------

  • Offline mode – launch Minecraft without a Microsoft account.
  • Profile management – create, edit, and delete separate profiles.
  • Mod loader support – Fabric, Quilt, and vanilla.
  • Mod manager – add/remove mod JARs per profile.
  • Resource pack manager – add/remove resource pack ZIPs per profile.
  • World manager – list, backup, and restore worlds.
  • Java settings – per‑profile memory and custom JVM arguments.
  • Auto Java detection – finds Java 8, 11, 16, 17, 21, 25.
  • Portable – can be bundled into a single .exe with PyInstaller.


---------------------------------------------------------------------
Requirements
---------------------------------------------------------------------

  • Python 3.8 or higher – download from python.org.
  • Python modules: requests, customtkinter, pillow.
    Install with: pip install requests customtkinter pillow
  • Java Runtime (JRE) or JDK (versions 8, 11, 16, 17, 21, or 25).
    Download from Adoptium.
  • Internet connection (only needed on first launch).
  • Graphics drivers with OpenGL 3.2+ (for 1.16.5+).


---------------------------------------------------------------------
Installation
---------------------------------------------------------------------

From Source:
  git clone https://github.com/Armand220/OpenLauncher.git
  cd OpenLauncher
  pip install -r requirements.txt   # or install manually
  python main.py

Standalone .exe:
  Download the latest release from GitHub, or build it yourself:
  pip install pyinstaller
  python -m PyInstaller --onefile --windowed --name OpenLauncher main.py


---------------------------------------------------------------------
How to Use
---------------------------------------------------------------------

  1. Click "Add Profile".
  2. Enter a name, Minecraft version, and choose a mod loader.
  3. Select the profile and click "Launch".
  4. The first launch downloads all required files (may take a few minutes).
  5. Subsequent launches are instant.


---------------------------------------------------------------------
Supported Mod Loaders
---------------------------------------------------------------------

  Vanilla (None)  – Working – No mods, pure Minecraft.
  Fabric          – Working – Latest versions and snapshots.
  Quilt           – Working – Latest versions and snapshots.

Note: Forge is not supported. Use a dedicated Forge launcher.


---------------------------------------------------------------------
Supported Minecraft Versions
---------------------------------------------------------------------

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


---------------------------------------------------------------------
Status: Beta
---------------------------------------------------------------------

  OpenLauncher is in active development. Some features may be incomplete, and
  not all versions are stable. We are working on improvements.

  Planned improvements:
    • Better Java detection and fallback
    • More mod loader support (if demand arises)
    • Better error messages and user guidance


---------------------------------------------------------------------
Known Issues
---------------------------------------------------------------------

  1. 1.16.5 and 1.17.1 crashes – see explanation above.
  2. 1.8.9 JSON parse errors – the launcher tries to delete the corrupt file.
     If it fails, delete launcher_profiles.json manually from your .minecraft folder.
  3. Java not found – if the launcher can't find Java, set the path manually in Edit Profile.
  4. Slow downloads – Mojang's CDN can be slow; retry later.


---------------------------------------------------------------------
False Positives (Anti-Virus Detections)
---------------------------------------------------------------------

  Some antivirus engines may flag the packaged .exe as a trojan – this is a
  FALSE POSITIVE caused by PyInstaller's bootloader. The code is open source
  and contains no malware.

  Solutions:
    • Run the Python script directly (python main.py) to avoid the .exe.
    • Add an exception in your antivirus software.
    • Build the .exe yourself from source.


---------------------------------------------------------------------
Building from Source (for Developers)
---------------------------------------------------------------------

  To build a single .exe:

    pip install pyinstaller
    python -m PyInstaller --onefile --windowed --name OpenLauncher main.py

  The .exe will be in the 'dist' folder.

  To reduce false positives, try Nuitka (free) instead of PyInstaller:
    pip install nuitka
    python -m nuitka --onefile --windows-disable-console main.py


---------------------------------------------------------------------
Contributing
---------------------------------------------------------------------

  We welcome contributions! Report bugs, suggest features, or submit pull requests.

  Steps:
    1. Fork the repository.
    2. Create a feature branch.
    3. Commit your changes.
    4. Push and open a Pull Request.


---------------------------------------------------------------------
License
---------------------------------------------------------------------

  This project is licensed under the MIT License – you are free to use, modify,
  and distribute it, provided you include the original license.


---------------------------------------------------------------------
Disclaimer
---------------------------------------------------------------------

  This launcher is intended for educational purposes only.
  It does not bypass purchase requirements; you must already own a legitimate
  copy of Minecraft. It works exclusively in offline mode – you cannot join
  premium (online‑mode=true) servers.

  OpenLauncher is not affiliated with Mojang Studios or Microsoft.


---------------------------------------------------------------------
Contact & Support
---------------------------------------------------------------------

  GitHub: https://github.com/Armand220/OpenLauncher
  Issues: https://github.com/Armand220/OpenLauncher/issues


---------------------------------------------------------------------
Happy crafting!
---------------------------------------------------------------------
