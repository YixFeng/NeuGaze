import pytest

from my_model_arch.cpu_fast.camera import (
    CameraConfig,
    camera_config_from_mapping,
    resolve_camera_backend,
)


def test_resolve_camera_backend_is_platform_explicit():
    configured = {"linux": "orbbec", "win32": "opencv"}
    assert resolve_camera_backend(configured, "linux") == "orbbec"
    assert resolve_camera_backend(configured, "win32") == "opencv"


@pytest.mark.parametrize("configured", [{}, {"linux": "auto"}, "orbbec", None])
def test_resolve_camera_backend_rejects_missing_or_implicit_values(configured):
    with pytest.raises((TypeError, ValueError)):
        resolve_camera_backend(configured, "linux")


def test_camera_config_reads_exact_stream_values():
    mapping = {
        "camera_backend": {"linux": "opencv", "win32": "opencv"},
        "cam_id": 2,
        "camera_width": 1280,
        "camera_height": 720,
        "camera_fps": 30,
    }
    assert camera_config_from_mapping(mapping, "linux") == CameraConfig(
        backend="opencv", device_id=2, width=1280, height=720, fps=30
    )


@pytest.mark.parametrize("field,value", [
    ("cam_id", -1), ("camera_width", 0), ("camera_height", 0), ("camera_fps", 0)
])
def test_camera_config_rejects_invalid_numeric_values(field, value):
    mapping = {
        "camera_backend": {"linux": "orbbec", "win32": "opencv"},
        "cam_id": 0,
        "camera_width": 1280,
        "camera_height": 720,
        "camera_fps": 30,
    }
    mapping[field] = value
    with pytest.raises(ValueError, match=field):
        camera_config_from_mapping(mapping, "linux")
