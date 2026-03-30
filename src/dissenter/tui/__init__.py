from .app import DissenterApp


def launch_tui() -> None:
    app = DissenterApp()
    app.run()
