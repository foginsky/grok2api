"""Vercel Python runtime entrypoint.

Define an `app` variable in this file so Vercel can detect the ASGI app.
"""

from main import create_app

app = create_app()
