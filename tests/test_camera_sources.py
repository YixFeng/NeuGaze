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


FAKE_RGB_FORMAT = object()


class FakeColorFrame:
    def __init__(self, data, color_format, width, height):
        self._data = data
        self._format = color_format
        self._width = width
        self._height = height

    def get_format(self):
        return self._format

    def get_width(self):
        return self._width

    def get_height(self):
        return self._height

    def get_data(self):
        if isinstance(self._data, np.ndarray):
            return self._data.tobytes()
        return self._data


class FakeFrameSet:
    def __init__(self, color_data, color_format, width, height):
        self._color_data = color_data
        self._color_format = color_format
        self._width = width
        self._height = height

    def get_color_frame(self):
        if self._color_data is MISSING_COLOR_FRAME:
            return None
        return FakeColorFrame(
            self._color_data,
            self._color_format,
            self._width,
            self._height,
        )


MISSING_COLOR_FRAME = object()


class FakeOrbbecPipeline:
    def __init__(
        self,
        color_data,
        *,
        color_format=FAKE_RGB_FORMAT,
        frame_width=None,
        frame_height=None,
        stop_errors=None,
    ):
        self.color_data = color_data
        self.color_format = color_format
        if isinstance(color_data, np.ndarray):
            frame_height, frame_width = color_data.shape[:2]
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.stop_errors = list(stop_errors or ())
        self.wait_calls = []
        self.stop_calls = 0

    def start(self, config):
        self.started_with = config

    def wait_for_frames(self, timeout_ms):
        self.wait_calls.append(timeout_ms)
        if self.color_data is None:
            return None
        return FakeFrameSet(
            self.color_data,
            self.color_format,
            self.frame_width,
            self.frame_height,
        )

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
    expected_set_calls = []
    if platform == "linux":
        expected_set_calls = [
            (camera.cv2.CAP_PROP_FRAME_WIDTH, 1280),
            (camera.cv2.CAP_PROP_FRAME_HEIGHT, 720),
            (camera.cv2.CAP_PROP_FPS, 30),
        ]
    assert capture.set_calls == expected_set_calls


def test_opencv_failed_open_releases_capture_exactly_once(monkeypatch):
    capture = FakeCapture(opened=False)
    monkeypatch.setattr(
        camera.cv2, "VideoCapture", lambda device_id, api: capture
    )

    with pytest.raises(RuntimeError, match="camera 0 failed to open"):
        OpenCVCamera.open(
            CameraConfig("opencv", 0, 1280, 720, 30), "linux"
        )

    assert capture.release_calls == 1


def test_opencv_failed_open_preserves_primary_when_release_also_fails(
    monkeypatch,
):
    primary_error = OSError("capture open probe failed")
    cleanup_error = OSError("capture release failed")
    capture = FakeCapture(release_errors=[cleanup_error])
    capture.isOpened = lambda: (_ for _ in ()).throw(primary_error)
    monkeypatch.setattr(
        camera.cv2, "VideoCapture", lambda device_id, api: capture
    )

    with pytest.raises(OSError) as caught:
        OpenCVCamera.open(
            CameraConfig("opencv", 0, 1280, 720, 30), "linux"
        )

    assert caught.value is primary_error
    assert capture.release_calls == 1
    assert any(
        "capture release failed" in note
        for note in getattr(primary_error, "__notes__", ())
    )


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
    device = FakeDevice("Orbbec Gemini 335", "SN123")
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
    assert source.device_label == (
        "Orbbec Gemini 335 serial SN123 index 0 "
        "RGB 1280x720 @ 30 FPS"
    )


def test_orbbec_listing_returns_only_approved_full_stream_label(
    monkeypatch,
):
    sdk, _, _, _, _ = fake_orbbec_sdk(
        [FakeDevice("Orbbec Gemini 335", "SN123")]
    )
    monkeypatch.setitem(sys.modules, "pyorbbecsdk", sdk)

    assert camera.list_cameras("orbbec", "linux") == [
        CameraInfo(
            "orbbec",
            0,
            "Orbbec Gemini 335 serial SN123 index 0 "
            "RGB 1280x720 @ 30 FPS",
            "SN123",
        )
    ]



def test_orbbec_listing_rejects_unapproved_model_with_index(monkeypatch):
    sdk, _, _, _, _ = fake_orbbec_sdk(
        [FakeDevice("Femto Bolt", "SN456")]
    )
    monkeypatch.setitem(sys.modules, "pyorbbecsdk", sdk)

    with pytest.raises(
        RuntimeError,
        match=r"index 0.*expected.*Orbbec Gemini 335.*Femto Bolt",
    ):
        camera.list_cameras("orbbec", "linux")



def test_orbbec_listing_keeps_context_alive(monkeypatch):
    device = FakeDevice("Orbbec Gemini 335", "SN123")

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
        CameraInfo(
            "orbbec",
            0,
            "Orbbec Gemini 335 serial SN123 index 0 "
            "RGB 1280x720 @ 30 FPS",
            "SN123",
        )
    ]


def test_orbbec_rgb_is_converted_to_contiguous_bgr():
    rgb = np.array([[[1, 2, 3], [4, 5, 6]]], dtype=np.uint8)
    source = OrbbecColorCamera.from_pipeline(
        FakeOrbbecPipeline(rgb),
        device_label="Gemini 335 SN123",
        width=2,
        height=1,
        fps=30,
        rgb_format=FAKE_RGB_FORMAT,
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
        rgb_format=FAKE_RGB_FORMAT,
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
        rgb_format=FAKE_RGB_FORMAT,
    )

    with pytest.raises(RuntimeError, match="missing a color frame"):
        source.read()


def test_orbbec_wrong_byte_length_is_an_error():
    source = OrbbecColorCamera.from_pipeline(
        FakeOrbbecPipeline(
            b"\x00" * 5,
            frame_width=2,
            frame_height=1,
        ),
        device_label="Gemini 335 SN123",
        width=2,
        height=1,
        fps=30,
        rgb_format=FAKE_RGB_FORMAT,
    )

    with pytest.raises(RuntimeError, match="expected 6 bytes, got 5"):
        source.read()


@pytest.mark.parametrize(
    ("stage", "message"),
    (
        ("wait_for_frames", "wait for frames"),
        ("get_color_frame", "get color frame"),
        ("get_data", "get color frame data"),
        ("memoryview", "inspect color frame buffer"),
        ("frombuffer", "convert color frame buffer to RGB array"),
        ("cvtColor", "convert RGB frame to BGR"),
        ("ascontiguousarray", "make BGR frame contiguous"),
    ),
)
def test_orbbec_read_native_failure_has_device_and_stage_context(
    monkeypatch,
    stage,
    message,
):
    device_label = (
        "Orbbec Gemini 335 serial SN123 index 0 "
        "RGB 1280x720 @ 30 FPS"
    )
    sentinel = OSError(f"{stage} native failure")
    data = b"\x00" * 6
    color_frame = SimpleNamespace(
        get_format=lambda: FAKE_RGB_FORMAT,
        get_width=lambda: 2,
        get_height=lambda: 1,
        get_data=lambda: data,
    )
    frames = SimpleNamespace(get_color_frame=lambda: color_frame)
    pipeline = SimpleNamespace(wait_for_frames=lambda timeout_ms: frames)

    def raise_sentinel(*args, **kwargs):
        raise sentinel

    if stage == "wait_for_frames":
        pipeline.wait_for_frames = raise_sentinel
    elif stage == "get_color_frame":
        frames.get_color_frame = raise_sentinel
    elif stage == "get_data":
        color_frame.get_data = raise_sentinel
    elif stage == "memoryview":
        monkeypatch.setattr(camera, "memoryview", raise_sentinel, raising=False)
    elif stage == "frombuffer":
        monkeypatch.setattr(camera.np, "frombuffer", raise_sentinel)
    elif stage == "cvtColor":
        monkeypatch.setattr(camera.cv2, "cvtColor", raise_sentinel)
    elif stage == "ascontiguousarray":
        monkeypatch.setattr(camera.np, "ascontiguousarray", raise_sentinel)

    source = OrbbecColorCamera.from_pipeline(
        pipeline,
        device_label=device_label,
        width=2,
        height=1,
        fps=30,
        rgb_format=FAKE_RGB_FORMAT,
    )

    with pytest.raises(RuntimeError) as caught:
        source.read()

    assert device_label in str(caught.value)
    assert message in str(caught.value)
    assert caught.value.__cause__ is sentinel
    assert sentinel.__traceback__ is not None


def test_orbbec_close_is_idempotent_after_success():
    pipeline = FakeOrbbecPipeline(None)
    source = OrbbecColorCamera.from_pipeline(
        pipeline,
        device_label="Gemini 335 SN123",
        width=1280,
        height=720,
        fps=30,
        rgb_format=FAKE_RGB_FORMAT,
    )

    source.close()
    source.close()

    assert pipeline.stop_calls == 1


def test_orbbec_close_failure_has_context_and_leaves_ownership_retryable():
    device_label = (
        "Orbbec Gemini 335 serial SN123 index 0 "
        "RGB 1280x720 @ 30 FPS"
    )
    sentinel = OSError("native stop failed")
    pipeline = FakeOrbbecPipeline(None, stop_errors=[sentinel])
    source = OrbbecColorCamera.from_pipeline(
        pipeline,
        device_label=device_label,
        width=1280,
        height=720,
        fps=30,
        rgb_format=FAKE_RGB_FORMAT,
    )

    with pytest.raises(RuntimeError) as caught:
        source.close()

    assert device_label in str(caught.value)
    assert "stop pipeline" in str(caught.value)
    assert caught.value.__cause__ is sentinel
    assert sentinel.__traceback__ is not None
    assert source._closed is False

    source.close()

    assert pipeline.stop_calls == 2
    assert source._closed is True


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


@pytest.mark.parametrize(
    "config",
    [
        CameraConfig("orbbec", 0, 640, 720, 30),
        CameraConfig("orbbec", 0, 1280, 480, 30),
        CameraConfig("orbbec", 0, 1280, 720, 60),
    ],
)
def test_orbbec_open_rejects_non_approved_stream(monkeypatch, config):
    sdk, _, _, _, _ = fake_orbbec_sdk(
        [FakeDevice("Orbbec Gemini 335", "SN123")]
    )
    monkeypatch.setitem(sys.modules, "pyorbbecsdk", sdk)

    with pytest.raises(
        ValueError, match=r"requires RGB 1280x720 @ 30 FPS"
    ):
        OrbbecColorCamera.open(config)


def test_orbbec_open_rejects_non_approved_model(monkeypatch):
    sdk, _, pipelines, _, _ = fake_orbbec_sdk(
        [FakeDevice("Gemini 335", "SN123")]
    )
    monkeypatch.setitem(sys.modules, "pyorbbecsdk", sdk)

    with pytest.raises(
        RuntimeError,
        match=(
            r"index 0.*expected.*Orbbec Gemini 335"
            r".*got.*Gemini 335"
        ),
    ):
        OrbbecColorCamera.open(
            CameraConfig("orbbec", 0, 1280, 720, 30)
        )

    assert pipelines.instances == []


@pytest.mark.parametrize("stage", ["profile", "config", "start"])
def test_orbbec_open_chains_sdk_failure_with_full_stream_context(
    monkeypatch, stage
):
    sdk, _, _, _, _ = fake_orbbec_sdk(
        [FakeDevice("Orbbec Gemini 335", "SN123")]
    )
    source_error = OSError(f"{stage} failed")

    if stage == "profile":
        monkeypatch.setattr(
            FakeProfileList,
            "get_video_stream_profile",
            lambda self, *args: (_ for _ in ()).throw(source_error),
        )
    elif stage == "config":
        class FailingConfig(FakeConfig):
            def enable_stream(self, profile):
                raise source_error

        sdk.Config = FailingConfig
    else:
        monkeypatch.setattr(
            FakeOrbbecPipeline,
            "start",
            lambda self, config: (_ for _ in ()).throw(source_error),
        )

    monkeypatch.setitem(sys.modules, "pyorbbecsdk", sdk)

    with pytest.raises(RuntimeError) as caught:
        OrbbecColorCamera.open(
            CameraConfig("orbbec", 0, 1280, 720, 30)
        )

    assert caught.value.__cause__ is source_error
    message = str(caught.value)
    assert stage in message
    assert (
        "Orbbec Gemini 335 serial SN123 index 0 "
        "RGB 1280x720 @ 30 FPS"
    ) in message


@pytest.mark.parametrize(
    ("pipeline", "message"),
    [
        (
            FakeOrbbecPipeline(
                b"\x00" * 6,
                color_format=object(),
                frame_width=2,
                frame_height=1,
            ),
            "expected format",
        ),
        (
            FakeOrbbecPipeline(
                b"\x00" * 6,
                frame_width=3,
                frame_height=1,
            ),
            "expected dimensions 2x1, got 3x1",
        ),
    ],
)
def test_orbbec_read_rejects_wrong_frame_metadata(pipeline, message):
    source = OrbbecColorCamera.from_pipeline(
        pipeline,
        device_label=(
            "Orbbec Gemini 335 serial SN123 index 0 RGB 2x1 @ 30 FPS"
        ),
        width=2,
        height=1,
        fps=30,
        rgb_format=FAKE_RGB_FORMAT,
    )

    with pytest.raises(RuntimeError, match=message):
        source.read()


def test_win32_opencv_uses_directshow_without_strict_stream_negotiation(
    monkeypatch,
):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    capture = FakeCapture(
        read_result=(True, frame),
        set_results={
            camera.cv2.CAP_PROP_FRAME_WIDTH: False,
            camera.cv2.CAP_PROP_FRAME_HEIGHT: False,
            camera.cv2.CAP_PROP_FPS: False,
        },
        negotiated={
            camera.cv2.CAP_PROP_FRAME_WIDTH: 640.0,
            camera.cv2.CAP_PROP_FRAME_HEIGHT: 480.0,
            camera.cv2.CAP_PROP_FPS: 25.0,
        },
    )
    calls = []
    monkeypatch.setattr(
        camera.cv2,
        "VideoCapture",
        lambda device, api: calls.append((device, api)) or capture,
    )

    source = OpenCVCamera.open(
        CameraConfig("opencv", 2, 1280, 720, 30), "win32"
    )

    assert source.read() is frame
    assert calls == [(2, camera.cv2.CAP_DSHOW)]
    assert capture.set_calls == []


def test_win32_listing_requires_successful_read_probe(monkeypatch):
    captures = {
        0: FakeCapture(read_result=(False, None)),
        1: FakeCapture(
            read_result=(
                True,
                np.zeros((480, 640, 3), dtype=np.uint8),
            )
        ),
    }
    monkeypatch.setattr(
        camera.cv2,
        "VideoCapture",
        lambda device, api: captures.get(
            device, FakeCapture(opened=False)
        ),
    )

    assert camera.list_cameras("opencv", "win32") == [
        CameraInfo("opencv", 1, "Camera 1")
    ]
    assert captures[0].release_calls == 1
    assert captures[1].release_calls == 1


def test_win32_listing_exposes_probe_close_failure(monkeypatch):
    close_error = OSError("DirectShow release failed")
    capture = FakeCapture(release_errors=[close_error])
    monkeypatch.setattr(
        camera.cv2,
        "VideoCapture",
        lambda device, api: capture,
    )

    with pytest.raises(OSError) as caught:
        camera.list_cameras("opencv", "win32")

    assert caught.value is close_error
    assert capture.release_calls == 1
