import sys


if sys.platform == "win32":
    from .gaze_show_utils import GazeOverlay
elif sys.platform.startswith("linux"):
    from .gaze_overlay_x11 import GazeOverlay
else:
    raise RuntimeError(f"unsupported gaze overlay platform: {sys.platform}")


__all__ = ["GazeOverlay"]
