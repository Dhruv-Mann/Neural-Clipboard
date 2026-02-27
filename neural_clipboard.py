"""
Neural Clipboard – Phase 3
Queue-based architecture: the clipboard watcher produces items, a
separate AI-processor thread consumes them.
"""

import queue
import threading
import time
import pyperclip
import pystray
from PIL import Image

# ── Shared thread-safe primitives ────────────────────────────────────
shutdown_event = threading.Event()          # Tells every thread to stop
privacy_event  = threading.Event()          # SET = privacy ON

# The bridge between the watcher (producer) and the AI processor
# (consumer).  maxsize=0 means unlimited depth.
ai_queue: queue.Queue[str] = queue.Queue()

_tray_icon: pystray.Icon | None = None


# ── Icon generation ──────────────────────────────────────────────────
COLOR_GREEN = (0, 180, 0)
COLOR_RED   = (200, 0, 0)


def create_icon_image(color: tuple = COLOR_GREEN, size: int = 64) -> Image.Image:
    """Generate a solid-color square icon in memory."""
    return Image.new("RGB", (size, size), color=color)


# ── Thread 1 – Clipboard watcher (PRODUCER) ─────────────────────────
def watcher_loop() -> None:
    """Polls the clipboard every 0.5 s.
    • Privacy ON  → log & discard
    • Privacy OFF → enqueue text for AI processing
    """
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
                print(f"[Watcher] New clip → queue: {current_text}")
                ai_queue.put(current_text)      # non-blocking enqueue
            last_text = current_text

        shutdown_event.wait(timeout=0.5)

    print("[Watcher] Stopped.")


# ── Thread 2 – AI processor (CONSUMER) ──────────────────────────────
def ai_processor_loop() -> None:
    """Blocks on the queue waiting for text.  Simulates a slow LLM API
    call with time.sleep(3).  Uses queue.get(timeout=…) so it can
    still check the shutdown flag periodically."""
    while not shutdown_event.is_set():
        try:
            text = ai_queue.get(timeout=1)      # block up to 1 s
        except queue.Empty:
            continue                             # nothing yet – re-check shutdown

        print(f"[AI] Processing: {text}")
        time.sleep(3)                            # ← simulate LLM latency
        print(f"[AI RESULT] Analyzed: {text}")
        ai_queue.task_done()                     # mark item complete

    print("[AI Processor] Stopped.")


# ── Tray menu callbacks ─────────────────────────────────────────────
def on_toggle_privacy(icon: pystray.Icon, item: pystray.MenuItem) -> None:
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


def on_exit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    print("[Tray] Exit requested – shutting down...")
    shutdown_event.set()
    icon.stop()


# ── Entry point ──────────────────────────────────────────────────────
def main() -> None:
    global _tray_icon

    # Launch both daemon threads
    watcher = threading.Thread(target=watcher_loop, name="watcher", daemon=True)
    ai_proc = threading.Thread(target=ai_processor_loop, name="ai_proc", daemon=True)
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

    _tray_icon.run()           # blocks until icon.stop()

    shutdown_event.set()
    watcher.join(timeout=3)
    ai_proc.join(timeout=5)   # give the AI thread a bit longer to finish
    print("[Main] Clean shutdown complete.")


if __name__ == "__main__":
    main()
