# tests/__init__.py
"""Automated unit test suite for Pokémon Web Application and Tournament Battle Engine."""

import sys
import os

# Ensure the root pokemon-web-app directory is on sys.path regardless of execution CWD
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)
