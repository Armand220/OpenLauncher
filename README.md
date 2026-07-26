================================================================================
                     OpenLauncher - Minecraft Offline Launcher
================================================================================

A free, open-source Python launcher for Minecraft that works entirely offline -
no Microsoft account required.

GitHub: https://github.com/Armand220/OpenLauncher

================================================================================
REQUIREMENTS
================================================================================

- Python 3.8 or higher (download from https://www.python.org/downloads/)
- Python modules: requests, customtkinter, pillow
  Install with: pip install requests customtkinter pillow
- Java Runtime (JRE) or JDK (versions 8, 11, 16, 17, 21, or 25 supported)
  Download from https://adoptium.net/
- Internet connection (only needed on first launch to download game files)
- Graphics drivers supporting OpenGL 3.2 or higher (required for 1.16.5+)

================================================================================
INSTALLATION
================================================================================

1. Clone or download this repository:
   git clone https://github.com/Armand220/OpenLauncher.git
   cd OpenLauncher

2. Install Python dependencies:
   pip install requests customtkinter pillow

3. Run the launcher:
   python main.py

================================================================================
HOW TO USE
================================================================================

1. Click "Add Profile"
2. Enter a profile name, Minecraft version (e.g., 1.21.1), and your offline username
3. Choose a mod loader: either Fabric, Quilt, or None (vanilla)
4. Select the profile and click "Launch"
5. The first launch will download all required files (may take a few minutes)
6. Subsequent launches are instant

================================================================================
SUPPORTED MOD LOADERS
================================================================================

- Vanilla (None)  -  Working  -  No mod loader, pure Minecraft
- Fabric          -  Working  -  Latest versions, snapshot support
- Quilt           -  Working  -  Latest versions, snapshot support

Note: Forge is no longer supported. Please use a dedicated Forge launcher for modpacks requiring Forge.

================================================================================
SUPPORTED MINECRAFT VERSIONS
================================================================================

Version          Status       Java Required    Notes
---------------------------------------------------------------
1.8.9            Partial      Java 8           May require deleting launcher_profiles.json manually
1.12.2           Working      Java 8           Fully functional
1.16.5           Unstable     Java 8/11        Crashes with EXCEPTION_ACCESS_VIOLATION on many systems
1.17.1           Unstable     Java 16/17       Same crash as 1.16.5
1.21.1           Working      Java 17/21       Tested and runs without issues
1.21.11          Working      Java 21          Works with Fabric/Quilt
26.1 (snapshot)  Working      Java 25          Auto-detects and uses Java 25 if installed

Why 1.16.5 and 1.17.1 crash:
These versions use LWJGL 3.2.1 which relies heavily on GPU OpenGL support.
Outdated drivers or lack of OpenGL 3.2+ cause GLFW to crash.
Updating graphics drivers usually fixes the problem.

================================================================================
STATUS: BETA
================================================================================

OpenLauncher is currently in BETA development. This means:
- Some features may be incomplete
- Not all Minecraft versions are stable yet
- You may encounter crashes or errors
- We are actively working on improvements

Planned improvements:
- Better Java detection and fallback
- Support for more mod loaders (if community demand arises)
- Improved error messages and user guidance

Your feedback is welcome! Open an issue on GitHub or contact the developers.

================================================================================
KNOWN ISSUES
================================================================================

1. 1.16.5 and 1.17.1 crashes
   Cause: GLFW initialisation fails due to missing OpenGL features.
   Fix: Update your graphics drivers (NVIDIA/AMD/Intel).
   Workaround: Add these JVM flags:
     -Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true
     -Dorg.lwjgl.opengl.Window.allowSoftwareOpenGL=true

2. 1.8.9 JSON parse errors
   Cause: Corrupt or unsupported launcher_profiles.json.
   Fix: The launcher attempts to delete it automatically; if that fails, delete it manually from your .minecraft directory.

3. Java not found
   Cause: The launcher's automatic search may miss custom installations.
   Fix: Manually set the Java path in the Edit Profile dialog.

4. Slow download speeds
   Cause: Mojang's CDN can be slow at peak times.
   Fix: Retry later; the launcher will resume partially downloaded files.

================================================================================
FALSE POSITIVES (ANTI-VIRUS DETECTIONS)
================================================================================

Some anti-virus engines may flag the packaged .exe (if you built one) as a trojan
or virus. This is a FALSE POSITIVE caused by PyInstaller's self-extracting
bootloader. The source code is fully open and contains no malware.

Solutions:
- Use the Python script directly (run python main.py) to avoid the .exe entirely.
- Add an exception for the .exe in your anti-virus software.
- Build the .exe yourself from source (instructions below).

================================================================================
BUILDING FROM SOURCE (FOR DEVELOPERS)
================================================================================

To build a single .exe from the Python source:

1. Install PyInstaller:
   pip install pyinstaller

2. From the project folder, run:
   python -m PyInstaller --onefile --windowed --name OpenLauncher main.py

3. The .exe will be in the 'dist' folder.

If you want to reduce false positives, you can try:
- Using Nuitka (pip install nuitka) instead of PyInstaller:
  python -m nuitka --onefile --windows-disable-console main.py
- Adding version information with --version-file.

================================================================================
CONTRIBUTING
================================================================================

We welcome contributions! You can help by:
- Reporting bugs
- Suggesting features
- Submitting pull requests

Steps to contribute:
1. Fork the repository: https://github.com/Armand220/OpenLauncher
2. Create a feature branch
3. Commit your changes
4. Push and open a Pull Request

================================================================================
LICENSE
================================================================================

This project is licensed under the MIT License.
You are free to use, modify, and distribute this software, provided you include the original license.

================================================================================
DISCLAIMER
================================================================================

This launcher is intended for educational purposes only.
It does not bypass any purchase requirements; you must already own a legitimate copy of Minecraft to use this tool.
The launcher works exclusively in offline mode – you cannot join premium (online-mode=true) servers.

OpenLauncher is not affiliated with Mojang Studios or Microsoft.

================================================================================
CONTACT & SUPPORT
================================================================================

GitHub: https://github.com/Armand220/OpenLauncher
Issues: https://github.com/Armand220/OpenLauncher/issues

================================================================================
Happy crafting!
================================================================================
