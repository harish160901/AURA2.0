# ✦ AURA 2.0 — Multimodal Aesthetic Intelligence HUD

![Aura 2.0 HUD](https://img.shields.io/badge/AURA-2.0-00f2fe?style=for-the-badge&logo=google&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-macOS-lightgrey?style=for-the-badge&logo=apple&logoColor=white)
![AI Model](https://img.shields.io/badge/Model-Gemini%20Multimodal%20Live-7000ff?style=for-the-badge&logo=google-gemini&logoColor=white)
![Transport](https://img.shields.io/badge/Transport-LiveKit%20WebRTC-00E599?style=for-the-badge&logo=webrtc&logoColor=white)

**AURA 2.0** is an ultra-fast, real-time multimodal voice and vision assistant designed for macOS. Powered by **Google Gemini Realtime Live API** and **LiveKit WebRTC**, Aura features an aesthetic cyberpunk HUD with live camera vision, hands-free wake word detection, drag-and-drop file analysis, and deep native macOS system automation.

---

## ⚡ Key Features

- 🎙️ **Real-Time Voice Streaming**: Ultra-low latency bi-directional voice communication powered by Gemini Realtime with automatic Voice Activity Detection (VAD).
- 📷 **Live Camera Vision**: Real-time video frame sampling allowing Aura to see, reason about, and describe what is shown in front of the camera.
- 💻 **Native macOS Automation**: Direct tool execution to control the system:
  - **Launch & Quit Apps**: Safari, Maps, Finder, Notes, Terminal, WhatsApp, Calculator, Calendar, Chrome, VS Code, etc.
  - **Folder Exploration**: Open or list contents of Desktop, Documents, Downloads, Home, or Applications in Finder.
  - **System Telemetry**: Adjust master volume (0–100%) and inspect battery charge & status.
- 🗣️ **Wake Word & Always Listening**: Hands-free *"Hey Aura"*, *"Hi Aura"*, or *"Aura"* activation with a 30-second listening countdown, or switch to continuous always-on listening.
- 📎 **File & Image Attachments**: Drag-and-drop or attach files and images with instant preview chips for analysis.
- 🔊 **Boosted 3.5x Sound**: Built-in WebAudio pipeline providing +350% gain amplification with automatic audio-context unlocking.
- 🌌 **Futuristic Cyberpunk HUD**: Google Gemini-style prompt dock, 3D interactive holographic cyber core with rotating telemetry rings, live subtitle ticker, and searchable conversation history.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│                   AURA 2.0 Web HUD                     │
│    (HTML5 + Tailwind CSS + Web Speech API + WebRTC)    │
└───────────────▲────────────────────────▲───────────────┘
                │                        │
       HTTP / REST API              LiveKit WebRTC
 (Tokens, Uploads, macOS Cmds)   (Audio, Video, Data)
                │                        │
┌───────────────▼──────────────┐ ┌───────▼───────────────┐
│          server.py           │ │          agent.py     │
│   - Dual-Stack HTTP Server   │ │   - LiveKit Worker    │
│   - LiveKit Token & Dispatch │ │   - Gemini Live API   │
│   - File Uploads & Storage   │ │   - Mac Tool Execution│
│   - Native macOS Automation  │ │   - Vision Sampler    │
└──────────────────────────────┘ └───────────────────────┘
```

---

## 📋 Prerequisites

- **Operating System**: macOS (tested on macOS Ventura, Sonoma, Sequoia)
- **Python**: Python 3.10 or higher
- **LiveKit Cloud Project**: Credentials from [cloud.livekit.io](https://cloud.livekit.io)
- **Google Gemini API Key**: API key with Multimodal Live API access from [Google AI Studio](https://aistudio.google.com/)

---

## 🚀 Quick Start

### 1. Clone & Set Up Environment

```bash
git clone https://github.com/your-username/AURA2.0.git
cd AURA2.0

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Credentials

Create a `.env.local` file in the project root:

```env
# LiveKit Cloud Credentials
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

# Google Gemini Realtime Live API Key
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Start the System

Open two terminal windows (or run in background):

**Terminal 1 — Web Server:**
```bash
./venv/bin/python server.py
```

**Terminal 2 — Multimodal Agent Worker:**
```bash
./venv/bin/python agent.py dev
```

### 4. Open the HUD

Open your browser and navigate to:
```
http://localhost:3000
```

---

## ⌨️ Controls & Shortcuts

| Action | Shortcut / Trigger |
|---|---|
| **Toggle Microphone** | Click `MIC` button, or press `Spacebar` / `M` |
| **Wake Word Activation** | Say *"Hey Aura"*, *"Hi Aura"*, or *"Aura"* |
| **Always-On Listening** | Toggle `ALWAYS LISTENING` badge in the header |
| **Toggle Camera Vision** | Click the camera icon in the bottom dock |
| **Send Text Message** | Type in the dock and press `Enter` or click `↑` |
| **Attach Files / Photos** | Click paperclip icon or drag & drop files onto the page |
| **Switch View** | Toggle between `✦ Aesthetic Core` and `💬 Live Transcript` |
| **Conversation History** | Click `📜 History` to slide out saved logs |

---

## 🗣️ Supported Voice & Mac Commands

You can speak or type commands naturally:

- **Open Apps**: *"Open Safari"*, *"Launch Notes"*, *"Start Terminal"*, *"Open WhatsApp"*
- **Close Apps**: *"Close Maps"*, *"Quit Safari"*, *"Exit Calculator"*
- **Open Folders**: *"Open Desktop"*, *"Go to Downloads"*, *"Show Documents"*
- **List Folders**: *"What's in my Downloads folder?"*, *"List Desktop"*
- **System Controls**: *"Set volume to 50"*, *"Check battery status"*
- **General Queries**: Any multimodal or conversational question answered with ultra-low latency.

---

## 📦 Project Structure

```
AURA2.0/
├── agent.py               # LiveKit agent worker & Gemini Realtime model integration
├── server.py              # Dual-stack HTTP server, token generator, & system endpoints
├── index.html             # High-aesthetic cybernetic frontend HUD
├── livekit-client.umd.min.js # Local offline-capable LiveKit WebRTC client bundle
├── requirements.txt       # Python dependencies
├── uploads/               # Attachment storage directory
└── .env.local             # Local environment variables & credentials (git-ignored)
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
