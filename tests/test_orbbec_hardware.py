import numpy as np
import pytest

from my_model_arch.cpu_fast.camera import (
    CameraConfig,
    list_cameras,
    open_camera,
)


pytestmark = pytest.mark.orbbec_hardware

CONFIG = CameraConfig("orbbec", 0, 1280, 720, 30)


def assert_valid_bgr_frame(frame):
    assert frame.shape == (720, 1280, 3)
    assert frame.dtype == np.uint8
    assert frame.flags.c_contiguous


def test_gemini_335_reads_100_frames_and_reopens():
    cameras = list_cameras("orbbec", "linux")
    assert cameras, "selected Orbbec camera 0 is not connected"
    assert "Gemini 335" in cameras[0].label

    source = open_camera(CONFIG, "linux")
    try:
        for _ in range(100):
            assert_valid_bgr_frame(source.read())
    finally:
        source.close()

    reopened = open_camera(CONFIG, "linux")
    try:
        assert_valid_bgr_frame(reopened.read())
    finally:
        reopened.close()
