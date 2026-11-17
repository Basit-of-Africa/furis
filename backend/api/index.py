"""Vercel entry point: Vercel's Python runtime serves the ASGI `app` exported here.
All paths are routed to this function by vercel.json."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from furis.main import app  # noqa: E402,F401
