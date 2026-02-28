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

# Constant storing the Gemini model name used for all API calls.
MODEL = "gemini-2.5-flash"
# Max number of retry attempts when hitting a rate-limit error.
MAX_RETRIES = 3

# Starting backoff delay in seconds. Doubles each retry: 5 → 10 → 20.
BASE_DELAY  = 5

# Helper function that wraps a single API call.
# Returns a tuple: (result_text, None) on success or (None, error_string) on failure.
# This clean separation lets the caller decide what to do with success vs failure.
def _try_generate(client, prompt):
    """Attempt a single generate_content call. Returns (result_text, None) on
    success or (None, error_string) on failure."""
    try:
        # Sends the prompt to Gemini and gets a response object.
        response = client.models.generate_content(model=MODEL, contents=prompt)

        # Success — return cleaned response text and None for the error slot.
        return response.text.strip(), None
    except Exception as e:
        # Failure — return None for text and the error message as a string.
        # This prevents the thread from crashing on API errors.
        return None, str(e)

# The main consumer thread function. Runs in an infinite loop, pulling clipboard
# items from ai_queue, sending them to Gemini, and displaying the results.
def ai_processor_loop():

    # Read the API key from environment (loaded earlier by load_dotenv).
    api_key = os.getenv("GEMINI_API_KEY")

    # If missing, print error and kill this thread — no point running without a key.
    if not api_key:
        print("[API Error] GEMINI_API_KEY not found in .env – AI processor disabled.")
        return

    # Create the Gemini client object using the API key.
    # If initialization fails (bad key format, network issue), log and exit thread.
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[API Error] Failed to initialize Gemini Client: {e}")
        return

    # Startup log confirming which model is active.
    print(f"[AI] Using model: {MODEL}")

    # Main loop — keeps consuming queue items until shutdown is triggered.
    while not shutdown_event.is_set():
        try:
            # Try to grab text from the queue. If nothing arrives within 1 second,
            # throws queue.Empty so we loop back and re-check the shutdown flag.
            text = ai_queue.get(timeout=1)
        except queue.Empty:
            continue

        # Log that a new clipboard item is being processed.
        print("[AI] Analyzing...")

        # Build the AI prompt: asks Gemini to classify the text as one of
        # 5 categories (CODE, URL, ADDRESS, TASK, GENERAL) and give a 1-sentence summary.
        prompt = ("Analyze this clipboard text. Classify it strictly as one of "
                  "the following: [CODE, URL, ADDRESS, TASK, GENERAL]. "
                  f"Then provide a 1-sentence summary. Text: {text}")

        # Track whether the API call eventually succeeded.
        success = False

        # Retry loop: attempts 1, 2, 3.
        for attempt in range(1, MAX_RETRIES + 1):

            # Make the API call via the helper function.
            result, err = _try_generate(client, prompt)

            # If we got a result, show it and send a desktop notification.
            if result is not None:
                print(f"[AI RESULT]\n{result}")
                try:
                    # Show a Windows toast notification with the AI result.
                    # Truncated to 256 chars (OS limit for notification messages).
                    # Wrapped in try/except so notification failure doesn't crash the thread.
                    notification.notify(
                        title="Neural Clipboard",
                        message=result[:256],
                        app_name="Neural Clipboard",
                        timeout=5,
                    )
                except Exception:
                    pass
                success = True
                break  # Exit retry loop — we have our answer.

            # Rate-limited (HTTP 429) — wait with exponential backoff then retry.
            # Exponential backoff: attempt 1 → 5s, attempt 2 → 10s, attempt 3 → 20s.
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                delay = BASE_DELAY * (2 ** (attempt - 1))
                print(f"[AI] Rate-limited – retry {attempt}/{MAX_RETRIES} in {delay}s...")

                # Wait the backoff duration, but wake early if shutdown happens.
                shutdown_event.wait(timeout=delay)
                if shutdown_event.is_set():
                    break  # Shutdown triggered during wait — stop retrying.
                continue  # Go to next retry attempt.

            # Any non-rate-limit error (auth failure, bad request, etc.)
            # Don't retry — these won't fix themselves.
            print(f"[API Error] Attempt {attempt}: {err}")
            break

        # All retries exhausted with no success (and not shutting down):
        # Log failure and send an error toast notification.
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

        # Signal the queue that this item is fully processed.
        # Required for queue.Queue bookkeeping (so queue.join() works correctly).
        ai_queue.task_done()

    # Final log when the consumer thread exits.
    print("[AI Processor] Stopped.")

# ── 5. Tray Menu Callbacks ──────────────────────────────────────────
# These functions are triggered by right-click menu actions on the system tray icon.
# pystray passes (icon, item) to every callback automatically.

# Callback fired when user clicks "Privacy Mode" in the tray menu.
def on_toggle_privacy(icon, item):

    # If privacy is currently ON → turn it OFF.
    if privacy_event.is_set():
        privacy_event.clear()                       # Clear the flag so watcher resumes sending to AI.
        icon.icon = create_icon_image(COLOR_GREEN)  # Swap tray icon back to green (active).
        icon.title = "Neural Clipboard"              # Reset hover tooltip.
        print("[Tray] Privacy Mode OFF")

    # If privacy is currently OFF → turn it ON.
    else:
        privacy_event.set()                                  # Set the flag so watcher skips clipboard items.
        icon.icon = create_icon_image(COLOR_RED)             # Swap tray icon to red (paused).
        icon.title = "Neural Clipboard (Privacy)"             # Update hover tooltip.
        print("[Tray] Privacy Mode ON")

# Callback for the "Exit" menu item.
def on_exit(icon, item):
    print("[Tray] Exit requested – shutting down...")
    shutdown_event.set()  # Signal all threads to stop their loops.
    icon.stop()           # Stop the tray icon event loop, which unblocks main().

# ── 6. Main Entry Point ─────────────────────────────────────────────
# This is the app's entry function — sets up threads, tray icon, and handles shutdown.
def main():

    # Allow this function to assign to the module-level _tray_icon variable.
    global _tray_icon

    # Create the clipboard watcher thread (producer).
    # daemon=True means it auto-dies if the main thread exits unexpectedly.
    watcher = threading.Thread(target=watcher_loop, daemon=True)

    # Create the AI processor thread (consumer). Same daemon behavior.
    ai_proc = threading.Thread(target=ai_processor_loop, daemon=True)
    
    # Launch both background threads.
    watcher.start()
    ai_proc.start()

    # Create the system tray icon with:
    #   - name: internal identifier
    #   - icon: green square (active state)
    #   - title: hover tooltip text
    #   - menu: right-click context menu with Privacy toggle and Exit
    _tray_icon = pystray.Icon(
        name="NeuralClipboard",
        icon=create_icon_image(COLOR_GREEN),
        title="Neural Clipboard",
        menu=pystray.Menu(
            pystray.MenuItem(
                "Privacy Mode",
                on_toggle_privacy,
                # checked=lambda dynamically shows a checkmark when privacy is ON.
                checked=lambda item: privacy_event.is_set(),
            ),
            pystray.MenuItem("Exit", on_exit),
        ),
    )

    # BLOCKS HERE — runs the tray icon's event loop.
    # Code below this only executes after icon.stop() is called (from on_exit).
    _tray_icon.run()

    # ── Cleanup after tray exits ──
    # Safety net: ensure shutdown flag is set even if tray stopped without on_exit.
    shutdown_event.set()

    # Wait for threads to finish (3s and 5s max respectively) for a clean shutdown.
    watcher.join(timeout=3)
    ai_proc.join(timeout=5)

    print("[Main] Clean shutdown complete.")

# Standard Python idiom: only run main() if this file is executed directly,
# not when imported as a module by another script.
if __name__ == "__main__":
    main()