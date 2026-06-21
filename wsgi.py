#!/usr/bin/env python3
"""
wsgi.py — Production WSGI entrypoint for Render / gunicorn.
Usage:  gunicorn -b 0.0.0.0:$PORT wsgi:app
"""
import os
from dashboard import app  # noqa: F401

# Ensure PORT is respected when running under gunicorn
_PORT = int(os.environ.get("PORT", "5000"))

if __name__ == "__main__":
    # Development fallback only
    app.run(host="0.0.0.0", port=_PORT, debug=False)
