"""Vercel serverless entrypoint."""
import os
import sys

# Vercel serverless has no writable HOME by default; several libs
# (roboflow SDK, matplotlib, joblib) need one -> point them at /tmp.
os.environ.setdefault("HOME", "/tmp")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")
os.environ.setdefault("MPLCONFIGDIR", "/tmp")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app  # noqa: E402  (Vercel looks for `app`)

# Vercel python runtime serves the Flask `app` object.
