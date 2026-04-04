from .app import DissenterApp


def launch_tui() -> None:
    app = DissenterApp()
    app.run()
    # Force-exit to avoid hanging on orphaned litellm/aiohttp threads
    # that can't be cleanly cancelled from a worker thread.
    import os
    os._exit(0)
