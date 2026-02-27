"""
Neural Clipboard – Phase 2
Clipboard monitoring with a Privacy Mode toggle in the system tray.
"""

import threading
import pyperclip
import pystray
from PIL import Image

# ── Shared thread-safe signals ───────────────────────────────────────
shutdown_event = threading.Event()   # Tells the watcher to stop
privacy_event  = threading.Event()   # SET = privacy ON, CLEAR = privacy OFF

# We also need a reference to the tray icon so the watcher (or the
# toggle callback) can swap the icon image at any time.
_tray_icon: pystray.Icon | None = None


# ── Icon generation ──────────────────────────────────────────────────
COLOR_GREEN = (0, 180, 0)
COLOR_RED   = (200, 0, 0)


def create_icon_image(color: tuple = COLOR_GREEN, size: int = 64) -> Image.Image:
    """Generate a solid-color square icon in memory."""
    return Image.new("RGB", (size, size), color=color)


# ── Background clipboard watcher ─────────────────────────────────────
def watcher_loop() -> None:
    """Polls the clipboard every 0.5 s. Respects Privacy Mode and the
    shutdown signal."""
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
                print(f"[Watcher] New clip: {current_text}")
            last_text = current_text

        # Sleep up to 0.5 s, but wake instantly on shutdown.
        shutdown_event.wait(timeout=0.5)

    print("[Watcher] Stopped.")


# ── Tray menu callbacks ─────────────────────────────────────────────
def on_toggle_privacy(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Flip privacy mode and swap the icon color."""
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
    """Clean shutdown: signal the watcher, then tear down the tray."""
    print("[Tray] Exit requested – shutting down...")
    shutdown_event.set()
    icon.stop()


# ── Entry point ──────────────────────────────────────────────────────
def main() -> None:
    global _tray_icon

    watcher = threading.Thread(target=watcher_loop, daemon=True)
    watcher.start()

    _tray_icon = pystray.Icon(
        name="NeuralClipboard",
        icon=create_icon_image(COLOR_GREEN),
        title="Neural Clipboard",
        menu=pystray.Menu(
            pystray.MenuItem(
                # The lambda makes the checkmark reflect the live state.
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
    print("[Main] Clean shutdown complete.")


if __name__ == "__main__":
    main()
