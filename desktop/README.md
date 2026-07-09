# 🖥️ NEXUS Desktop OS Application Shell

This folder contains the **Electron** desktop wrapper for the **NEXUS AI Platform**. It packages the Next.js frontend and Python backend microservices into a single, downloadable standalone desktop application (executable `.exe` / `.dmg` installer).

---

## 🚀 How to Run in Development Mode

Ensure you have your virtual environment set up (`backend/.venv`) and node modules installed in `frontend`.

1. Open your terminal in the `desktop` directory:
   ```bash
   cd desktop
   ```
2. Install the desktop package dependencies:
   ```bash
   npm install
   ```
3. Run the standalone desktop application shell:
   ```bash
   npm start
   ```

*This will automatically launch all three backend microservices (`uvicorn`), start the frontend developer server (`npm run dev`), and open a native desktop application window.*

---

## 📦 How to Build the Downloadable Installer

To build a standalone installable file (`.exe` for Windows, `.dmg` for macOS, `.AppImage` for Linux):

1. Compile the build:
   ```bash
   npm run dist
   ```
2. The output installer files will be located in the `desktop/dist/` directory!
