from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_update_feed(app: FastAPI, directory: str | None) -> None:
    """Expose a dedicated public release directory, never the installer/secret root."""
    if directory:
        app.mount('/updates', StaticFiles(directory=directory), name='updates')
