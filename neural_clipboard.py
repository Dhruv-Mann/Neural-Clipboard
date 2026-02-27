"""
Neural Clipboard – Phase 1
A Windows background service with a system tray icon and a daemon watcher thread.
"""

import threading
import time
import pystray
from PIL import Image

# ── Shared shutdown signal ───────────────────────────────────────────
# An Event acts like a thread-safe boolean flag.
# Any thread can check it, any thread can set it.
shutdown_event = threading.Event()


# ── Background watcher ───────────────────────────────────────────────
def watcher_loop() -> None:
    """Runs on a daemon thread. Prints a heartbeat every 2 seconds
    until the shutdown Event is set."""
    while not shutdown_event.is_set():
        print("[Watcher] Running...")
        # wait() sleeps up to 2 s BUT returns immediately if the
        # event gets set, so shutdown is almost instant.
        shutdown_event.wait(timeout=2)
    print("[Watcher] Stopped.")


# ── Tray helpers ─────────────────────────────────────────────────────
def create_icon_image(size: int = 64) -> Image.Image:
    """Generate a simple green square icon in memory (no .ico file)."""
    return Image.new("RGB", (size, size), color=(0, 180, 0))


def on_exit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Called when the user clicks 'Exit' in the tray menu."""
    print("[Tray] Exit requested – shutting down...")
    shutdown_event.set()   # 1. tell the watcher thread to stop
    icon.stop()            # 2. tear down the tray icon (unblocks the main thread)


# ── Entry point ──────────────────────────────────────────────────────
def main() -> None:
    # Start the watcher on a daemon thread so it dies automatically
    # if the main thread exits unexpectedly.
    watcher = threading.Thread(target=watcher_loop, daemon=True)
    watcher.start()

    # Build the system-tray icon (runs on the main thread).
    icon = pystray.Icon(
        name="NeuralClipboard",
        icon=create_icon_image(),
        title="Neural Clipboard",
        menu=pystray.Menu(
            pystray.MenuItem("Exit", on_exit),
        ),
    )

    # icon.run() blocks until icon.stop() is called from the menu.
    icon.run()

    # After the tray is torn down, make sure the watcher finishes.
    shutdown_event.set()
    watcher.join(timeout=3)
    print("[Main] Clean shutdown complete.")


if __name__ == "__main__":
    main()
