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
# Basically we did this so that an image of 64x64 pixels is directly created in computer's ram
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
# Reads your .env file (e.g., containing GEMINI_API_KEY=xyz) and loads those key-value 
# pairs into os.environ so the rest of the code can access them via os.getenv().
load_dotenv() 

# ── 2. Shared Thread-Safe Signals ────────────────────────────────────

# Creates a thread-safe boolean flag (starts as False). When you want to shut down the
# app, you call shutdown_event.set() which flips it to True. All threads check this to
# know when to stop gracefully.
shutdown_event = threading.Event()

# Same idea — a flag to toggle privacy mode. When set, the clipboard watcher likely
#  skips monitoring so your copies aren't processed by AI.
privacy_event  = threading.Event()

#  queue.Queue()	Creates a thread-safe FIFO queue. The clipboard watcher puts
#  copied text into this queue, and the AI processor thread gets from it. This 
#  decouples the two threads cleanly.
ai_queue = queue.Queue()

# A global variable to hold a reference to the system tray icon object. Initialized
# as None, set later when the tray is created. The underscore prefix is a Python 
# convention meaning "internal/private — don't touch from outside."
_tray_icon = None

# RGB tuple for green — used as the tray icon color when the app is active/listening.
COLOR_GREEN = (0, 180, 0)

# RGB tuple for red — used as the tray icon color when in privacy mode (paused).
COLOR_RED   = (200, 0, 0)

# Defines a helper function to generate the tray icon image.
# Defaults: green color and 64×64 size.
def create_icon_image(color=COLOR_GREEN, size=64):

    # Docstring: describes that this creates an in-memory image (not read from disk).
    """Generate a solid-color square icon in memory."""

    # Uses Pillow to create and return a solid RGB square image with the given size/color.
    return Image.new("RGB", (size, size), color=color)

# ── 3. Background Clipboard Watcher (Producer) ──────────────────────
# Section marker: this thread produces clipboard items for the queue.

# Starts the watcher thread(daemon thread) function that continuously monitors clipboard changes.
def watcher_loop():

    # Stores previous clipboard value so duplicates aren’t re-queued repeatedly.
    last_text = ""

    # Main loop runs until shutdown flag is set by another part of the app.
    while not shutdown_event.is_set():

        # Begin protected block for clipboard read (clipboard access can fail on some systems/times).
        try:

            #Reads current clipboard text.
            current_text = pyperclip.paste()

        # If clipboard read errors, fallback to empty string so loop continues safely.
        except pyperclip.PyperclipException:
            current_text = ""
         
        # Only act when clipboard has non-empty text and it changed since last check.
        if current_text and current_text != last_text:

            # Checks privacy mode toggle. If ON, clipboard is not sent to AI.
            if privacy_event.is_set():

                #Debug log showing clip was intentionally skipped due to privacy mode.
                print("[Watcher] Privacy active: ignored")

            # If privacy mode is OFF, logs preview of new text and pushes full text
            # into ai_queue for AI processing.
            else:
                print(f"[Watcher] New clip -> queue: {current_text[:30]}...")
                ai_queue.put(current_text)

            # Updates memory of last clipboard value to prevent duplicate queueing.
            last_text = current_text

        # Waits up to 0.5s before next poll, but wakes early if shutdown is set (responsive stop behavior).
        shutdown_event.wait(timeout=0.5)

    # Final log printed when loop exits and watcher thread ends.
    print("[Watcher] Stopped.")

# ── 4. AI Processor (Consumer) ──────────────────────────────────────
# Section header — this thread consumes items from the queue.

MODEL = "gemini-2.5-flash"
MAX_RETRIES = 3
BASE_DELAY  = 5  # seconds (doubles each retry: 5 → 10 → 20)

def _try_generate(client, prompt):
    """Attempt a single generate_content call. Returns (result_text, None) on
    success or (None, error_string) on failure."""
    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
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

    print(f"[AI] Using model: {MODEL}")

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
        for attempt in range(1, MAX_RETRIES + 1):
            result, err = _try_generate(client, prompt)

            if result is not None:
                print(f"[AI RESULT]\n{result}")
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
                break

            # Rate-limited – wait with exponential backoff then retry
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                delay = BASE_DELAY * (2 ** (attempt - 1))
                print(f"[AI] Rate-limited – retry {attempt}/{MAX_RETRIES} in {delay}s...")
                shutdown_event.wait(timeout=delay)
                if shutdown_event.is_set():
                    break
                continue

            # Any other error – log and stop retrying
            print(f"[API Error] Attempt {attempt}: {err}")
            break

        if not success and not shutdown_event.is_set():
            print("[API Error] Failed after retries. Check your API key / billing.")
            try:
                notification.notify(
                    title="Neural Clipboard Error",
                    message="AI request failed. Check API key & billing.",
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