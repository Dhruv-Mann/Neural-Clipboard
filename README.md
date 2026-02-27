<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Gemini_AI-2.5_Flash-4285F4?style=for-the-badge&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

<h1 align="center">Neural Clipboard</h1>

<p align="center">
  <b>An AI-powered clipboard assistant that watches what you copy and instantly classifies & summarizes it — right from your system tray.</b>
</p>

<p align="center">
  <a href="https://youtu.be/WsX91e3RrGg">
    <img src="https://img.shields.io/badge/▶_Watch_Demo-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Watch Demo on YouTube" />
  </a>
</p>

---

## Demo

<p align="center">
  <a href="https://youtu.be/WsX91e3RrGg">
    <img src="https://img.youtube.com/vi/WsX91e3RrGg/maxresdefault.jpg" alt="Neural Clipboard Demo" width="720" />
  </a>
  <br/>
  <em>Click the thumbnail to watch the full demo on YouTube.</em>
</p>

---

## What Is This?

Every time you copy text — a code snippet, a URL, an address, a to-do item, or just a random paragraph — **Neural Clipboard** silently picks it up, sends it to **Google's Gemini AI**, and pushes a native **Windows desktop notification** telling you:

1. **What kind of content it is** — `CODE`, `URL`, `ADDRESS`, `TASK`, or `GENERAL`
2. **A one-sentence summary** of what you just copied

No windows to open. No buttons to press. It just works in the background via your **system tray**.

---

## Features

| Feature | Description |
|---|---|
| **Real-time Clipboard Monitoring** | Detects new clipboard content within 500ms using a background polling thread. |
| **AI Classification & Summarization** | Every copied text is classified into one of five categories and summarized in one sentence via Gemini AI. |
| **Native Desktop Notifications** | Results are delivered as Windows toast notifications — zero UI friction. |
| **System Tray Integration** | Lives in your system tray with a colored icon. Green = active, Red = privacy mode. |
| **Privacy Mode** | One-click toggle from the tray menu. When active, clipboard monitoring is completely paused — nothing is read or sent. |
| **Queue-Based Architecture** | Producer-consumer pattern with Python's `queue.Queue` ensures clipboard reads and AI calls never block each other. |
| **Retry with Exponential Backoff** | Handles API rate limits (429) gracefully — waits and retries automatically instead of crashing. |
| **Smart Error Handling** | Detects model 404s, zero-quota errors, and unknown failures separately with clear console logging. |
| **Model Fallback Chain** | Supports multiple Gemini models in priority order. If one fails, the next is tried automatically. |
| **Configurable via `.env`** | API key and model are loaded from a `.env` file — no hardcoded secrets in source code. |
| **Clean Shutdown** | Exit from tray menu triggers graceful shutdown of all threads with join timeouts. |

---

## Architecture

```
┌──────────────┐       ┌──────────────┐       ┌──────────────────┐
│   Clipboard  │       │  Thread-Safe │       │   Gemini AI API  │
│   Watcher    │──────▶│    Queue     │──────▶│   (Consumer)     │
│  (Producer)  │       │              │       │                  │
└──────────────┘       └──────────────┘       └───────┬──────────┘
                                                      │
                                                      ▼
                                              ┌──────────────────┐
                                              │  Windows Desktop │
                                              │  Notification    │
                                              └──────────────────┘

                  ┌───────────────────┐
                  │  System Tray Icon │
                  │  (Privacy Toggle) │
                  └───────────────────┘
```

**Threading model:**
- **Thread 1 — Watcher (Producer):** Polls the clipboard every 500ms, deduplicates, and pushes new text into the queue.
- **Thread 2 — AI Processor (Consumer):** Pulls text from the queue, calls Gemini, and fires desktop notifications.
- **Main Thread:** Runs the system tray icon (pystray's event loop).

All three coordinate via `threading.Event` for shutdown and privacy signals.

---

## Tech Stack

| Technology | Purpose |
|---|---|
| **Python 3.10+** | Core language |
| **Google Gemini API** (`google-genai`) | AI classification & summarization |
| **pyperclip** | Cross-platform clipboard access |
| **pystray** | System tray icon & menu |
| **Pillow** | Generating tray icon images in memory |
| **plyer** | Native OS desktop notifications |
| **python-dotenv** | Loading API keys from `.env` |
| **threading + queue** | Concurrent producer-consumer architecture |

---

## Getting Started

### Prerequisites

- **Python 3.10+** installed
- A **Google Gemini API key** (free tier works) — get one at [aistudio.google.com](https://aistudio.google.com)
- **Windows** (notifications and tray icon are Windows-native)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/Neural-Clipboard.git
cd Neural-Clipboard

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install pyperclip pystray Pillow python-dotenv google-genai plyer

# 4. Create your .env file
echo GEMINI_API_KEY=your_api_key_here > .env
```

### Run

```bash
python neural_clipboard.py
```

A **green square** will appear in your system tray. Start copying text — you'll see notifications pop up with AI-powered analysis.

---

## Configuration

All configuration is done through the `.env` file in the project root:

```env
# Required — your Gemini API key
GEMINI_API_KEY=your_api_key_here

# Optional — override the default model (default: gemini-2.5-flash)
GEMINI_MODEL=gemini-2.5-flash
```

> **Note:** The `.env` file is git-ignored. Your API key will never be pushed to GitHub.

---

## Usage

| Action | How |
|---|---|
| **Start** | Run `python neural_clipboard.py` |
| **Copy anything** | Just Ctrl+C as usual — Neural Clipboard picks it up automatically |
| **Enable Privacy Mode** | Right-click the tray icon → **Privacy Mode** (icon turns red, monitoring pauses) |
| **Disable Privacy Mode** | Right-click the tray icon → **Privacy Mode** again (icon turns green) |
| **Exit** | Right-click the tray icon → **Exit** |

---

## Example Output

```
[AI] Model priority: ['gemini-2.5-flash']
[Watcher] New clip -> queue: def hello_world():  print(...
[AI] Analyzing...
[AI RESULT] (model=gemini-2.5-flash)
Classification: CODE
Summary: A Python function definition that prints "Hello, World!" to the console.

[Watcher] New clip -> queue: https://github.com/...
[AI] Analyzing...
[AI RESULT] (model=gemini-2.5-flash)
Classification: URL
Summary: A GitHub repository URL pointing to a user's project page.

[Watcher] New clip -> queue: Pick up groceries at 5pm...
[AI] Analyzing...
[AI RESULT] (model=gemini-2.5-flash)
Classification: TASK
Summary: A reminder to pick up groceries at 5 PM today.
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `GEMINI_API_KEY not found` | Missing `.env` file or empty key | Create `.env` with your API key |
| `404 NOT_FOUND` | Model name is invalid or sunset | Update `GEMINI_MODEL` in `.env` or remove it to use the default |
| `429 RESOURCE_EXHAUSTED` (limit: 0) | Free-tier quota fully exhausted | Generate a new API key at [aistudio.google.com](https://aistudio.google.com) or enable billing |
| `429 RESOURCE_EXHAUSTED` (temporary) | Hit per-minute rate limit | The app auto-retries with backoff — just wait |
| No notifications appearing | `plyer` notification backend issue | Make sure Windows notifications are enabled for Python in system settings |

---

## Project Structure

```
Neural Clipboard/
├── neural_clipboard.py   # Entire application — single-file architecture
├── .env                  # API key (git-ignored, you create this)
├── .gitignore            # Ignores .env, .venv, __pycache__, etc.
├── LICENSE               # MIT License
└── README.md             # You are here
```

---

## Roadmap

- [ ] Clipboard history panel with search
- [ ] Category-based auto-actions (e.g., auto-open URLs in browser)
- [ ] Support for image clipboard content (screenshots → OCR → AI)
- [ ] Cross-platform support (macOS, Linux)
- [ ] Hotkey to manually trigger analysis
- [ ] Local LLM fallback (Ollama) for offline mode

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## Author

**Dhruv Mann**

---

<p align="center">
  <b>If you found this useful, consider giving it a star!</b> ⭐
</p>
