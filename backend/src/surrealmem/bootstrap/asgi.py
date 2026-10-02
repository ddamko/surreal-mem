"""ASGI entrypoint for uvicorn: ``surrealmem.bootstrap.asgi:app``."""

from surrealmem.bootstrap.app import create_app

app = create_app()
