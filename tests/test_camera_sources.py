import sys
import weakref
from types import SimpleNamespace

import numpy as np
import pytest

from my_model_arch.cpu_fast import camera
from my_model_arch.cpu_fast.camera import (
    CameraConfig,
    CameraInfo,
    OpenCVCamera,
    OrbbecColorCamera,
)


class FakeCapture:
    def __init__(
        self,
        read_result=None,
        *,
        opened=True,
        set_results=None,
        negotiated=None,
        release_errors=None,
    ):
        if read_result is None:
            read_result = (
                True,
                np.zeros((720, 1280, 3), dtype=np.uint8),
            )
        self.read_result = read_result
        self.opened = opened
        self.set_results = set_results or {}
        self.negotiated = negotiated or {
            camera.cv2.CAP_PROP_FRAME_WIDTH: 1280.0,
            camera.cv2.CAP_PROP_FRAME_HEIGHT: 720.0,
            camera.cv2.CAP_PROP_FPS: 30.0,
        }
        self.release_errors = list(release_errors or ())
        self.set_calls = []
        self.release_calls = 0

    def isOpened(self):
        return self.opened

    def set(self, prop, value):
        self.set_calls.append((prop, value))
        return self.set_results.get(prop, True)

    def get(self, prop):
        return self.negotiated[prop]

    def read(self):
        return self.read_result

    def release(self):
        self.release_calls += 1
        if self.release_errors:
            raise self.release_errors.pop(0)


class FakeColorFrame:
    def __init__(self, data):
        self._data = data

    def get_data(self):
        if isinstance(self._data, np.ndarray):
            return self._data.tobytes()
        return self._data


class FakeFrameSet:
    def __init__(self, color_data):
        self._color_data = color_data

    def get_color_frame(self):
        if self._color_data is MISSING_COLOR_FRAME:
            return None
        return FakeColorFrame(self._color_data)


MISSING_COLOR_FRAME = object()


class FakeOrbbecPipeline:
    def __init__(self, color_data, *, stop_errors=None):
        self.color_data = color_data
        self.stop_errors = list(stop_errors or ())
        self.wait_calls = []
        self.stop_calls = 0

    def start(self, config):
        self.started_with = config

    def wait_for_frames(self, timeout_ms):
        self.wait_calls.append(timeout_ms)
        if self.color_data is None:
            return None
        return FakeFrameSet(self.color_data)

    def stop(self):
        self.stop_calls += 1
        if self.stop_errors:
            raise self.stop_errors.pop(0)


class FakeDeviceInfo:
    def __init__(self, name, serial):
        self._name = name
        self._serial = serial

    def get_name(self):
        return self._name

    def get_serial_number(self):
        return self._serial


class FakeDevice:
    def __init__(self, name, serial):
        self.info = FakeDeviceInfo(name, serial)

    def get_device_info(self):
        return self.info


class FakeDeviceList:
    def __init__(self, devices):
        self.devices = devices

    def get_count(self):
        return len(self.devices)

    def get_device_by_index(self, index):
        return self.devices[index]


class FakeContext:
    def __init__(self, devices):
        self.devices = devices
        self.query_calls = 0

    def query_devices(self):
        self.query_calls += 1
        return FakeDeviceList(self.devices)


class FakeProfileList:
    def __init__(self):
        self.calls = []
        self.profile = object()

    def get_video_stream_profile(self, width, height, format, fps):
        self.calls.append((width, height, format, fps))
        return self.profile


class FakePipelineFactory:
    def __init__(self):
        self.devices = []
        self.instances = []

    def __call__(self, device):
        self.devices.append(device)
        pipeline = FakeOrbbecPipeline(
            np.zeros((720, 1280, 3), dtype=np.uint8)
        )
        pipeline.profiles = FakeProfileList()
        pipeline.get_stream_profile_list = (
            lambda sensor_type: pipeline.profiles
        )
        self.instances.append(pipeline)
        return pipeline


class FakeConfig:
    def __init__(self):
        self.enabled_profiles = []

    def enable_stream(self, profile):
        self.enabled_profiles.append(profile)


def fake_orbbec_sdk(devices):
    context = FakeContext(devices)
    pipelines = FakePipelineFactory()
    color_sensor = object()
    rgb_format = object()
    sdk = SimpleNamespace(
        Context=lambda: context,
        Pipeline=pipelines,
        Config=FakeConfig,
        OBSensorType=SimpleNamespace(COLOR_SENSOR=color_sensor),
        OBFormat=SimpleNamespace(RGB=rgb_format),
    )
    return sdk, context, pipelines, color_sensor, rgb_format


def test_open_camera_does_not_fallback_after_v4l2_failure(monkeypatch):
    called = []
    monkeypatch.setattr(
        camera,
        "_open_opencv",
        lambda config, platform: called.append("opencv")
        or (_ for _ in ()).throw(RuntimeError("v4l2 failed")),
    )
    monkeypatch.setattr(
        camera, "_open_orbbec", lambda config: called.append("orbbec")
    )
    with pytest.raises(RuntimeError, match="v4l2 failed"):
        camera.open_camera(
            CameraConfig("opencv", 0, 1280, 720, 30), "linux"
        )
    assert called == ["opencv"]


def test_open_camera_does_not_fallback_after_orbbec_failure(monkeypatch):
    called = []
    monkeypatch.setattr(
        camera,
        "_open_orbbec",
        lambda config: called.append("orbbec")
        or (_ for _ in ()).throw(RuntimeError("orbbec failed")),
    )
    monkeypatch.setattr(
        camera,
        "_open_opencv",
        lambda config, platform: called.append("opencv"),
    )
    with pytest.raises(RuntimeError, match="orbbec failed"):
        camera.open_camera(
            CameraConfig("orbbec", 0, 1280, 720, 30), "linux"
        )
    assert called == ["orbbec"]


@pytest.mark.parametrize(
    ("platform", "expected_api", "backend_name"),
    [
        ("linux", camera.cv2.CAP_V4L2, "V4L2"),
        ("win32", camera.cv2.CAP_DSHOW, "DirectShow"),
    ],
)
def test_opencv_open_uses_only_the_platform_api(
    monkeypatch, platform, expected_api, backend_name
):
    capture = FakeCapture()
    calls = []
    monkeypatch.setattr(
        camera.cv2,
        "VideoCapture",
        lambda device_id, api: calls.append((device_id, api)) or capture,
    )

    source = OpenCVCamera.open(
        CameraConfig("opencv", 3, 1280, 720, 30), platform
    )

    assert calls == [(3, expected_api)]
    assert source.backend_name == backend_name
    assert capture.set_calls == [
        (camera.cv2.CAP_PROP_FRAME_WIDTH, 1280),
        (camera.cv2.CAP_PROP_FRAME_HEIGHT, 720),
        (camera.cv2.CAP_PROP_FPS, 30),
    ]


def test_opencv_open_rejects_negotiated_v4l2_mismatch(monkeypatch):
    capture = FakeCapture(
        negotiated={
            camera.cv2.CAP_PROP_FRAME_WIDTH: 640.0,
            camera.cv2.CAP_PROP_FRAME_HEIGHT: 480.0,
            camera.cv2.CAP_PROP_FPS: 30.0,
        }
    )
    monkeypatch.setattr(
        camera.cv2, "VideoCapture", lambda device_id, api: capture
    )

    with pytest.raises(
        RuntimeError,
        match=r"requested 1280x720 @ 30 FPS.*got 640x480 @ 30",
    ):
        OpenCVCamera.open(
            CameraConfig("opencv", 0, 1280, 720, 30), "linux"
        )


def test_opencv_open_rejects_failed_capture_setting(monkeypatch):
    capture = FakeCapture(
        set_results={camera.cv2.CAP_PROP_FRAME_HEIGHT: False}
    )
    monkeypatch.setattr(
        camera.cv2, "VideoCapture", lambda device_id, api: capture
    )

    with pytest.raises(
        RuntimeError, match="failed to set frame height to 720"
    ):
        OpenCVCamera.open(
            CameraConfig("opencv", 0, 1280, 720, 30), "linux"
        )


def test_opencv_read_rejects_empty_frame():
    source = OpenCVCamera(
        FakeCapture(read_result=(False, None)),
        CameraConfig("opencv", 0, 1280, 720, 30),
        backend_name="V4L2",
    )
    with pytest.raises(
        RuntimeError, match="V4L2 camera 0 failed to read a frame"
    ):
        source.read()


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (
            np.zeros((720, 1280, 3), dtype=np.float32),
            "uint8",
        ),
        (
            np.zeros((720, 1280), dtype=np.uint8),
            "HWC with 3 channels",
        ),
        (
            np.zeros((480, 640, 3), dtype=np.uint8),
            "expected 1280x720",
        ),
        (
            np.zeros((720, 1280, 3), dtype=np.uint8)[:, ::-1],
            "C-contiguous",
        ),
    ],
)
def test_opencv_read_rejects_invalid_frame(frame, message):
    source = OpenCVCamera(
        FakeCapture(read_result=(True, frame)),
        CameraConfig("opencv", 0, 1280, 720, 30),
        backend_name="V4L2",
    )

    with pytest.raises(RuntimeError, match=message):
        source.read()


def test_opencv_close_is_idempotent_after_success():
    capture = FakeCapture()
    source = OpenCVCamera(
        capture,
        CameraConfig("opencv", 0, 1280, 720, 30),
        backend_name="V4L2",
    )

    source.close()
    source.close()

    assert capture.release_calls == 1


def test_opencv_close_failure_leaves_cleanup_retryable():
    capture = FakeCapture(release_errors=[RuntimeError("release failed")])
    source = OpenCVCamera(
        capture,
        CameraConfig("opencv", 0, 1280, 720, 30),
        backend_name="V4L2",
    )

    with pytest.raises(RuntimeError, match="release failed"):
        source.close()
    source.close()

    assert capture.release_calls == 2


def test_orbbec_open_selects_exact_device_and_rgb_profile(monkeypatch):
    device = FakeDevice("Gemini 335", "SN123")
    sdk, context, pipelines, color_sensor, rgb_format = fake_orbbec_sdk(
        [device]
    )
    monkeypatch.setitem(sys.modules, "pyorbbecsdk", sdk)

    source = OrbbecColorCamera.open(
        CameraConfig("orbbec", 0, 1280, 720, 30)
    )

    pipeline = pipelines.instances[0]
    assert context.query_calls == 1
    assert pipelines.devices == [device]
    assert pipeline.profiles.calls == [
        (1280, 720, rgb_format, 30)
    ]
    assert pipeline.started_with.enabled_profiles == [
        pipeline.profiles.profile
    ]
    assert source.device_label == "Gemini 335 SN123"


def test_orbbec_listing_returns_model_serial_and_index(monkeypatch):
    devices = [
        FakeDevice("Gemini 335", "SN123"),
        FakeDevice("Femto Bolt", "SN456"),
    ]
    sdk, _, _, _, _ = fake_orbbec_sdk(devices)
    monkeypatch.setitem(sys.modules, "pyorbbecsdk", sdk)

    assert camera.list_cameras("orbbec", "linux") == [
        CameraInfo("orbbec", 0, "Gemini 335 SN123", "SN123"),
        CameraInfo("orbbec", 1, "Femto Bolt SN456", "SN456"),
    ]


def test_orbbec_listing_keeps_context_alive(monkeypatch):
    device = FakeDevice("Gemini 335", "SN123")

    class ContextBoundDeviceList(FakeDeviceList):
        def __init__(self, context):
            super().__init__([device])
            self.context = weakref.ref(context)

        def get_device_by_index(self, index):
            if self.context() is None:
                raise RuntimeError("device context was destroyed")
            return super().get_device_by_index(index)

    class Context:
        def query_devices(self):
            return ContextBoundDeviceList(self)

    sdk = SimpleNamespace(Context=Context)
    monkeypatch.setitem(sys.modules, "pyorbbecsdk", sdk)

    assert camera.list_cameras("orbbec", "linux") == [
        CameraInfo("orbbec", 0, "Gemini 335 SN123", "SN123")
    ]


def test_orbbec_rgb_is_converted_to_contiguous_bgr():
    rgb = np.array([[[1, 2, 3], [4, 5, 6]]], dtype=np.uint8)
    source = OrbbecColorCamera.from_pipeline(
        FakeOrbbecPipeline(rgb),
        device_label="Gemini 335 SN123",
        width=2,
        height=1,
        fps=30,
    )
    bgr = source.read()
    assert bgr.tolist() == [[[3, 2, 1], [6, 5, 4]]]
    assert bgr.flags.c_contiguous


def test_orbbec_timeout_is_an_error_not_an_empty_frame():
    source = OrbbecColorCamera.from_pipeline(
        FakeOrbbecPipeline(None),
        device_label="Gemini 335 SN123",
        width=1280,
        height=720,
        fps=30,
    )
    with pytest.raises(TimeoutError, match="1000 ms"):
        source.read()


def test_orbbec_missing_color_frame_is_an_error():
    source = OrbbecColorCamera.from_pipeline(
        FakeOrbbecPipeline(MISSING_COLOR_FRAME),
        device_label="Gemini 335 SN123",
        width=1280,
        height=720,
        fps=30,
    )

    with pytest.raises(RuntimeError, match="missing a color frame"):
        source.read()


def test_orbbec_wrong_byte_length_is_an_error():
    source = OrbbecColorCamera.from_pipeline(
        FakeOrbbecPipeline(b"\x00" * 5),
        device_label="Gemini 335 SN123",
        width=2,
        height=1,
        fps=30,
    )

    with pytest.raises(RuntimeError, match="expected 6 bytes, got 5"):
        source.read()


def test_orbbec_close_is_idempotent_after_success():
    pipeline = FakeOrbbecPipeline(None)
    source = OrbbecColorCamera.from_pipeline(
        pipeline,
        device_label="Gemini 335 SN123",
        width=1280,
        height=720,
        fps=30,
    )

    source.close()
    source.close()

    assert pipeline.stop_calls == 1


def test_orbbec_close_failure_leaves_cleanup_retryable():
    pipeline = FakeOrbbecPipeline(
        None, stop_errors=[RuntimeError("stop failed")]
    )
    source = OrbbecColorCamera.from_pipeline(
        pipeline,
        device_label="Gemini 335 SN123",
        width=1280,
        height=720,
        fps=30,
    )

    with pytest.raises(RuntimeError, match="stop failed"):
        source.close()
    source.close()

    assert pipeline.stop_calls == 2


def test_dispatchers_reject_unknown_backends():
    with pytest.raises(
        ValueError, match="unsupported camera backend: 'auto'"
    ):
        camera.list_cameras("auto", "linux")
    with pytest.raises(
        ValueError, match="unsupported camera backend: 'auto'"
    ):
        camera.open_camera(
            CameraConfig("auto", 0, 1280, 720, 30), "linux"
        )
