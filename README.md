OpenLauncher - Minecraft Offline Launcher (BETA)

A free, open-source Python launcher for Minecraft that works OFFLINE - no Microsoft account required.

GitHub: https://github.com/Armand220/OpenLauncher

---

REQUIREMENTS

- Python 3.8 or higher
  Download from: https://www.python.org/downloads/

- 'requests' Python module
  Install with: pip install requests

- Java Runtime Environment (JRE) or JDK
  Versions supported: Java 8, 11, 16, 17, 21, or 25
  Download from: https://adoptium.net/

- Internet connection (only for first launch, to download game files)

- Graphics drivers supporting OpenGL 3.2 or higher
  (Required for Minecraft 1.16.5 and above)

---

INSTALLATION

1. Clone or download this repository:
   git clone https://github.com/Armand220/OpenLauncher.git
   cd OpenLauncher

2. Install Python dependencies:
   pip install requests

3. Run the launcher:
   python openlauncher.py

---

HOW TO USE

- Click "Add New Profile"
- Enter a profile name, Minecraft version (e.g., 1.21.1), and your offline username
- Select the profile and click "Launch Selected"
- First launch will download all required files (may take a few minutes)
- Subsequent launches are instant

---

SUPPORTED VERSIONS

Version          Status        Java Required        Notes

1.8.9            Partial       Java 8               Works if launcher_profiles.json is deleted
1.12.2           Working       Java 8               Fully functional
1.16.5           Unstable      Java 8 or 11         Crashes with EXCEPTION_ACCESS_VIOLATION on many systems
1.17.1           Unstable      Java 16 or 17        Same crash as 1.16.5
1.21.1           Working       Java 17 or 21        Tested and runs without issues
26.1 (snapshot)  Working       Java 25              Detects and uses Java 25 if installed

Why 1.16.5 and 1.17.1 crash: These versions use LWJGL 3.2.1, which relies heavily on your GPU's OpenGL implementation. Outdated drivers or lack of OpenGL 3.2+ support causes GLFW to crash. Updating graphics drivers usually fixes the problem.

---

STATUS: BETA

OpenLauncher is currently in BETA development.

What this means:
- Some features may be incomplete
- Not all Minecraft versions are stable yet
- You may encounter crashes or errors
- We are actively working on improvements

We will continue to:
- Add support for more versions
- Improve Java detection
- Fix compatibility issues
- Add more features

Your feedback is welcome! Open an issue on GitHub or contact the developers.

---

KNOWN ISSUES

1. 1.16.5 and 1.17.1:
   - Issue: Crash with EXCEPTION_ACCESS_VIOLATION in glfw.dll
   - Fix: Update your graphics drivers (NVIDIA/AMD/Intel)
   - Fix: Add JVM flags:
     -Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true
     -Dorg.lwjgl.opengl.Window.allowSoftwareOpenGL=true

2. 1.8.9:
   - Issue: JSON parse error with launcher_profiles.json
   - Fix: Delete launcher_profiles.json manually or let the script do it (it now does this automatically)

3. Java detection:
   - Issue: Sometimes fails to find Java in custom locations
   - Fix: Manually set Java path in the Edit Profile dialog

4. Download errors:
   - Issue: Server timeouts or slow connections
   - Fix: Retry later or use the official launcher to download files

---

CONTRIBUTING

We welcome contributions! Help us improve OpenLauncher by:

- Reporting bugs
- Suggesting features
- Submitting pull requests

Steps:
1. Fork the repository: https://github.com/Armand220/OpenLauncher
2. Create a feature branch
3. Commit your changes
4. Push and open a Pull Request

---

LICENSE

OpenLauncher is licensed under the MIT License.

You are free to use, modify, and distribute this software, as long as you include the original license.

---

DISCLAIMER

This launcher is for EDUCATIONAL PURPOSES only.
It does not bypass any purchase requirements; you must already own a legitimate copy of Minecraft to use this tool.
The launcher only works in OFFLINE mode, so you cannot join premium servers (online-mode=true).

OpenLauncher is NOT affiliated with Mojang Studios or Microsoft.

---

CONTACT & SUPPORT

GitHub: https://github.com/Armand220/OpenLauncher
Issues: https://github.com/Armand220/OpenLauncher/issues

---

Happy crafting! 🎮
