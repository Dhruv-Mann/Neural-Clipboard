"""
Neural Clipboard – Final Phase
Queue-based architecture with Gemini AI integration and Desktop Notifications.
"""
# This library module helps in interacting with the operating system.
import os

# This provides thread-safe FIFO(First In First Out) queues. Used here to safely
# pass clipboard data between threads without race conditions.

# A race condition in a threading program is an undesirable situation that occurs when
# multiple threads concurrently access and modify the same shared resource (like a variable, object, or file)
# and the final outcome of the program depends on the unpredictable order or timing of their execution.
# This leads to inconsistent and unexpected results, making the program's behavior unreliable.
import queue

# This enables running multiple threads concurrently — e.g., one thread monitors the clipboard
# while another processes items, all without blocking each other.
import threading

# Third-party library that provides cross-platform copy/paste clipboard access 
import pyperclip

# Creates a system tray icon (the little icons in your taskbar).
# Lets the app run in the background with a right-click menu to interact with it.
import pystray

# From Pillow (image processing library).
# Image is used here to create/load the icon image that pystray displays in the system tray.
# Basically we did this so that a image of 64x64 pixels is directly created in computer's ram
# instead of manually uploading a file from the computer's storage.
from PIL import Image

# Loads environment variables from a .env file into os.environ.
# This is how the app securely reads API keys without hardcoding them.
from dotenv import load_dotenv

# Google's Generative AI SDK — provides access to Gemini models for 
# AI-powered text generation/processing. This is the brain of the app.
from google import genai

# Cross-platform library for desktop notifications (toast popups).
# Used to notify you when something happens (e.g., clipboard processed, AI response ready).
from plyer import notification

# ── 1. Load Environment Variables ─────────────────────────────────────
load_dotenv() 

# ── 2. Shared Thread-Safe Signals ────────────────────────────────────
shutdown_event = threading.Event()
privacy_event  = threading.Event()
ai_queue = queue.Queue()

_tray_icon = None
COLOR_GREEN = (0, 180, 0)
COLOR_RED   = (200, 0, 0)

def create_icon_image(color=COLOR_GREEN, size=64):
    """Generate a solid-color square icon in memory."""
    return Image.new("RGB", (size, size), color=color)

# ── 3. Background Clipboard Watcher (Producer) ──────────────────────
def watcher_loop():
    last_text = ""
    while not shutdown_event.is_set():
        try:
            current_text = pyperclip.paste()
        except pyperclip.PyperclipException:
            current_text = ""

        if current_text and current_text != last_text:
            if privacy_event.is_set():
                print("[Watcher] Privacy active: ignored")
            else:
                print(f"[Watcher] New clip -> queue: {current_text[:30]}...")
                ai_queue.put(current_text)
            last_text = current_text

        shutdown_event.wait(timeout=0.5)
    print("[Watcher] Stopped.")

# ── 4. AI Processor (Consumer) ──────────────────────────────────────
# Model priority list – override with GEMINI_MODEL in .env
DEFAULT_MODELS = ["gemini-2.5-flash"]
MAX_RETRIES    = 3
BASE_DELAY     = 5  # seconds

def _try_generate(client, model, prompt):
    """Attempt a single generate_content call. Returns (result_text, None) on
    success or (None, error_string) on failure."""
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip(), None
    except Exception as e:
        return None, str(e)

def ai_processor_loop():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[API Error] GEMINI_API_KEY not found in .env – AI processor disabled.")
        return

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[API Error] Failed to initialize Gemini Client: {e}")
        return

    # Build the model list: user override first, then defaults
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    models_to_try = ([env_model] if env_model else []) + DEFAULT_MODELS
    # Deduplicate while preserving order
    seen = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]

    print(f"[AI] Model priority: {models_to_try}")

    while not shutdown_event.is_set():
        try:
            text = ai_queue.get(timeout=1)
        except queue.Empty:
            continue

        print("[AI] Analyzing...")
        prompt = ("Analyze this clipboard text. Classify it strictly as one of "
                  "the following: [CODE, URL, ADDRESS, TASK, GENERAL]. "
                  f"Then provide a 1-sentence summary. Text: {text}")

        success = False
        for model in models_to_try:
            for attempt in range(1, MAX_RETRIES + 1):
                result, err = _try_generate(client, model, prompt)

                if result is not None:
                    print(f"[AI RESULT] (model={model})\n{result}")
                    try:
                        notification.notify(
                            title="Neural Clipboard",
                            message=result[:256],
                            app_name="Neural Clipboard",
                            timeout=5,
                        )
                    except Exception:
                        pass
                    success = True
                    break  # break retry loop

                # ── Handle specific error codes ──
                if "404" in err or "NOT_FOUND" in err:
                    print(f"[AI] Model '{model}' not found – skipping.")
                    break  # skip to next model, no point retrying

                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    if "limit: 0" in err:
                        print(f"[AI] Free-tier quota is 0 for '{model}' – "
                              "enable billing or try another model. Skipping.")
                        break  # skip to next model
                    delay = BASE_DELAY * (2 ** (attempt - 1))
                    print(f"[AI] Rate-limited on '{model}' – "
                          f"retry {attempt}/{MAX_RETRIES} in {delay}s...")
                    shutdown_event.wait(timeout=delay)
                    if shutdown_event.is_set():
                        break
                    continue

                # Unknown error – log and skip to next model
                print(f"[API Error] {model} attempt {attempt}: {err}")
                break

            if success or shutdown_event.is_set():
                break  # break model loop

        if not success and not shutdown_event.is_set():
            print("[API Error] All models failed. Check your API key / billing.")
            try:
                notification.notify(
                    title="Neural Clipboard Error",
                    message="All AI models failed. Check API key & billing.",
                    app_name="Neural Clipboard",
                    timeout=5,
                )
            except Exception:
                pass

        ai_queue.task_done()
    print("[AI Processor] Stopped.")

# ── 5. Tray Menu Callbacks ──────────────────────────────────────────
def on_toggle_privacy(icon, item):
    if privacy_event.is_set():
        privacy_event.clear()
        icon.icon = create_icon_image(COLOR_GREEN)
        icon.title = "Neural Clipboard"
        print("[Tray] Privacy Mode OFF")
    else:
        privacy_event.set()
        icon.icon = create_icon_image(COLOR_RED)
        icon.title = "Neural Clipboard (Privacy)"
        print("[Tray] Privacy Mode ON")

def on_exit(icon, item):
    print("[Tray] Exit requested – shutting down...")
    shutdown_event.set()
    icon.stop()

# ── 6. Main Entry Point ─────────────────────────────────────────────
def main():
    global _tray_icon

    watcher = threading.Thread(target=watcher_loop, daemon=True)
    ai_proc = threading.Thread(target=ai_processor_loop, daemon=True)
    
    watcher.start()
    ai_proc.start()

    _tray_icon = pystray.Icon(
        name="NeuralClipboard",
        icon=create_icon_image(COLOR_GREEN),
        title="Neural Clipboard",
        menu=pystray.Menu(
            pystray.MenuItem(
                "Privacy Mode",
                on_toggle_privacy,
                checked=lambda item: privacy_event.is_set(),
            ),
            pystray.MenuItem("Exit", on_exit),
        ),
    )

    _tray_icon.run()

    shutdown_event.set()
    watcher.join(timeout=3)
    ai_proc.join(timeout=5)
    print("[Main] Clean shutdown complete.")

if __name__ == "__main__":
    main()