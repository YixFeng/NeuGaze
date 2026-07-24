from dataclasses import dataclass
from typing import Mapping


VALID_CAMERA_BACKENDS = frozenset({"orbbec", "opencv"})


@dataclass(frozen=True)
class CameraConfig:
    backend: str
    device_id: int
    width: int
    height: int
    fps: int


def resolve_camera_backend(camera_backend: Mapping[str, str], platform: str) -> str:
    if not isinstance(camera_backend, Mapping):
        raise TypeError("integrated_config.camera_backend must be a platform mapping")
    if platform not in camera_backend:
        raise ValueError(f"camera_backend has no explicit value for platform {platform!r}")
    backend = camera_backend[platform]
    if backend not in VALID_CAMERA_BACKENDS:
        raise ValueError(
            f"camera_backend[{platform!r}] must be one of "
            f"{sorted(VALID_CAMERA_BACKENDS)}, got {backend!r}"
        )
    if platform == "win32" and backend != "opencv":
        raise ValueError("Windows camera_backend must remain 'opencv'")
    return backend


def camera_config_from_mapping(
    integrated_config: Mapping[str, object], platform: str
) -> CameraConfig:
    backend = resolve_camera_backend(integrated_config["camera_backend"], platform)
    values = {}
    for field in ("cam_id", "camera_width", "camera_height", "camera_fps"):
        value = integrated_config[field]
        if not isinstance(value, int) or value < 0 or (field != "cam_id" and value == 0):
            requirement = "a non-negative integer" if field == "cam_id" else "a positive integer"
            raise ValueError(f"{field} must be {requirement}")
        values[field] = value
    return CameraConfig(
        backend=backend,
        device_id=values["cam_id"],
        width=values["camera_width"],
        height=values["camera_height"],
        fps=values["camera_fps"],
    )
