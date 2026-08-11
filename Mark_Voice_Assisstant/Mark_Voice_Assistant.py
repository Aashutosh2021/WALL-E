"""
WALL-E AI Companion Robot - Backward Compatibility Re-exporter
Redirects all assistant calls to WALL_E_Assistant.py
"""

from WALL_E_Assistant import Assistant, entrypoint, set_eye_state

__all__ = ["Assistant", "entrypoint", "set_eye_state"]
