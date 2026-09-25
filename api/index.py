"""Vercel serverless entrypoint."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app  # noqa: E402  (Vercel looks for `app`)

# Vercel python runtime serves the Flask `app` object.
