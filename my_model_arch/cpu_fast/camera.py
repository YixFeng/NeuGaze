from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import cv2
import numpy as np


VALID_CAMERA_BACKENDS = frozenset({"orbbec", "opencv"})


@dataclass(frozen=True)
class CameraConfig:
    backend: str
    device_id: int
    width: int
    height: int
    fps: int


@dataclass(frozen=True)
class CameraInfo:
    backend: str
    device_id: int
    label: str
    serial: str | None = None


class OpenCVCamera:
    def __init__(self, capture, config: CameraConfig, backend_name: str):
        self.capture = capture
        self.config = config
        self.backend_name = backend_name
        self._closed = False

    @classmethod
    def open(cls, config: CameraConfig, platform: str) -> "OpenCVCamera":
        if platform == "linux":
            api = cv2.CAP_V4L2
            backend_name = "V4L2"
        elif platform == "win32":
            api = cv2.CAP_DSHOW
            backend_name = "DirectShow"
        else:
            raise ValueError(f"unsupported OpenCV camera platform: {platform!r}")

        capture = cv2.VideoCapture(config.device_id, api)
        try:
            if not capture.isOpened():
                raise RuntimeError(
                    f"{backend_name} camera {config.device_id} failed to open"
                )

            if platform == "linux":
                requested = (
                    (cv2.CAP_PROP_FRAME_WIDTH, config.width, "frame width"),
                    (cv2.CAP_PROP_FRAME_HEIGHT, config.height, "frame height"),
                    (cv2.CAP_PROP_FPS, config.fps, "FPS"),
                )
                for prop, value, label in requested:
                    if not capture.set(prop, value):
                        raise RuntimeError(
                            f"{backend_name} camera {config.device_id} "
                            f"failed to set {label} to {value}"
                        )

                actual_width = capture.get(cv2.CAP_PROP_FRAME_WIDTH)
                actual_height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
                actual_fps = capture.get(cv2.CAP_PROP_FPS)
                if (
                    actual_width != config.width
                    or actual_height != config.height
                    or actual_fps != config.fps
                ):
                    raise RuntimeError(
                        f"{backend_name} camera {config.device_id} requested "
                        f"{config.width}x{config.height} @ {config.fps} FPS, "
                        f"got {actual_width:g}x{actual_height:g} @ "
                        f"{actual_fps:g} FPS"
                    )
        except Exception as error:
            try:
                capture.release()
            except Exception as release_error:
                error.add_note(
                    "cleanup after failed open also failed: "
                    f"{release_error!r}"
                )
            raise

        return cls(capture, config, backend_name)

    def read(self) -> np.ndarray:
        ok, frame = self.capture.read()
        if not ok or frame is None:
            raise RuntimeError(
                f"{self.backend_name} camera {self.config.device_id} "
                "failed to read a frame"
            )
        if frame.dtype != np.uint8:
            raise RuntimeError(
                f"{self.backend_name} camera {self.config.device_id} "
                f"frame must have dtype uint8, got {frame.dtype}"
            )
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise RuntimeError(
                f"{self.backend_name} camera {self.config.device_id} "
                f"frame must be HWC with 3 channels, got shape {frame.shape}"
            )
        if (
            self.backend_name == "V4L2"
            and frame.shape[:2]
            != (self.config.height, self.config.width)
        ):
            raise RuntimeError(
                f"{self.backend_name} camera {self.config.device_id} "
                f"frame expected {self.config.width}x{self.config.height}, "
                f"got {frame.shape[1]}x{frame.shape[0]}"
            )
        if not frame.flags.c_contiguous:
            raise RuntimeError(
                f"{self.backend_name} camera {self.config.device_id} "
                "frame must be C-contiguous"
            )
        return frame

    def close(self) -> None:
        if self._closed:
            return
        self.capture.release()
        self._closed = True


class OrbbecColorCamera:
    def __init__(
        self,
        pipeline,
        device_label: str,
        width: int,
        height: int,
        fps: int,
        rgb_format,
    ):
        self.pipeline = pipeline
        self.device_label = device_label
        self.width = width
        self.height = height
        self.fps = fps
        self.rgb_format = rgb_format
        self._closed = False

    @classmethod
    def open(cls, config: CameraConfig) -> "OrbbecColorCamera":
        if (config.width, config.height, config.fps) != (1280, 720, 30):
            raise ValueError(
                "Orbbec Gemini 335 requires RGB 1280x720 @ 30 FPS; "
                f"got {config.width}x{config.height} @ {config.fps} FPS"
            )

        import pyorbbecsdk

        context = pyorbbecsdk.Context()
        devices = context.query_devices()
        device_count = devices.get_count()
        if config.device_id >= device_count:
            raise RuntimeError(
                f"Orbbec camera index {config.device_id} is unavailable; "
                f"detected {device_count} device(s)"
            )

        device = devices.get_device_by_index(config.device_id)
        info = device.get_device_info()
        name = info.get_name()
        serial = info.get_serial_number()
        if name != "Orbbec Gemini 335":
            raise RuntimeError(
                f"Orbbec camera index {config.device_id} expected "
                f"'Orbbec Gemini 335', got {name!r}"
            )
        stream = (
            f"{name} serial {serial} index {config.device_id} RGB "
            f"{config.width}x{config.height} @ {config.fps} FPS"
        )

        pipeline = pyorbbecsdk.Pipeline(device)
        try:
            profiles = pipeline.get_stream_profile_list(
                pyorbbecsdk.OBSensorType.COLOR_SENSOR
            )
            profile = profiles.get_video_stream_profile(
                config.width,
                config.height,
                pyorbbecsdk.OBFormat.RGB,
                config.fps,
            )
        except Exception as error:
            raise RuntimeError(
                f"{stream} profile lookup failed"
            ) from error

        try:
            sdk_config = pyorbbecsdk.Config()
            sdk_config.enable_stream(profile)
        except Exception as error:
            raise RuntimeError(f"{stream} config failed") from error

        try:
            pipeline.start(sdk_config)
        except Exception as error:
            raise RuntimeError(f"{stream} start failed") from error

        return cls(
            pipeline,
            stream,
            config.width,
            config.height,
            config.fps,
            pyorbbecsdk.OBFormat.RGB,
        )

    @classmethod
    def from_pipeline(
        cls,
        pipeline,
        device_label: str,
        width: int,
        height: int,
        fps: int,
        rgb_format,
    ) -> "OrbbecColorCamera":
        return cls(
            pipeline,
            device_label,
            width,
            height,
            fps,
            rgb_format,
        )

    def read(self) -> np.ndarray:
        frames = self.pipeline.wait_for_frames(1000)
        stream = self.device_label
        if frames is None:
            raise TimeoutError(
                f"{stream} did not return a FrameSet within 1000 ms"
            )
        color_frame = frames.get_color_frame()
        if color_frame is None:
            raise RuntimeError(f"{stream} FrameSet is missing a color frame")

        try:
            actual_format = color_frame.get_format()
            actual_width = color_frame.get_width()
            actual_height = color_frame.get_height()
        except Exception as error:
            raise RuntimeError(
                f"{stream} failed to read color frame metadata"
            ) from error
        if actual_format != self.rgb_format:
            raise RuntimeError(
                f"{stream} expected format {self.rgb_format!r}, "
                f"got {actual_format!r}"
            )
        if (actual_width, actual_height) != (self.width, self.height):
            raise RuntimeError(
                f"{stream} expected dimensions {self.width}x{self.height}, "
                f"got {actual_width}x{actual_height}"
            )

        data = color_frame.get_data()
        actual_bytes = memoryview(data).nbytes
        expected_bytes = self.width * self.height * 3
        if actual_bytes != expected_bytes:
            raise RuntimeError(
                f"{stream} expected {expected_bytes} bytes, got {actual_bytes}"
            )

        rgb = np.frombuffer(data, dtype=np.uint8).reshape(
            self.height, self.width, 3
        )
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return np.ascontiguousarray(bgr)

    def close(self) -> None:
        if self._closed:
            return
        self.pipeline.stop()
        self._closed = True


def _list_orbbec() -> list[CameraInfo]:
    import pyorbbecsdk

    context = pyorbbecsdk.Context()
    devices = context.query_devices()
    cameras = []
    for device_id in range(devices.get_count()):
        info = devices.get_device_by_index(device_id).get_device_info()
        name = info.get_name()
        serial = info.get_serial_number()
        if name != "Orbbec Gemini 335":
            raise RuntimeError(
                f"Orbbec camera index {device_id} expected "
                f"'Orbbec Gemini 335', got {name!r}"
            )
        cameras.append(
            CameraInfo(
                "orbbec",
                device_id,
                f"{name} serial {serial} index {device_id} "
                "RGB 1280x720 @ 30 FPS",
                serial,
            )
        )
    return cameras


def _list_opencv(platform: str) -> list[CameraInfo]:
    if platform == "linux":
        paths = sorted(
            (
                path
                for path in Path("/dev").glob("video*")
                if path.name[5:].isdigit()
            ),
            key=lambda path: int(path.name[5:]),
        )
        return [
            CameraInfo("opencv", int(path.name[5:]), str(path))
            for path in paths
        ]
    if platform == "win32":
        cameras = []
        for device_id in range(10):
            capture = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
            try:
                if capture.isOpened():
                    ok, frame = capture.read()
                    if ok and frame is not None:
                        cameras.append(
                            CameraInfo(
                                "opencv",
                                device_id,
                                f"Camera {device_id}",
                            )
                        )
            except BaseException as error:
                try:
                    capture.release()
                except BaseException as release_error:
                    error.add_note(
                        "DirectShow probe cleanup failed with "
                        f"{type(release_error).__name__}: {release_error}"
                    )
                raise
            else:
                capture.release()
        return cameras
    raise ValueError(f"unsupported OpenCV camera platform: {platform!r}")


def list_cameras(backend: str, platform: str) -> list[CameraInfo]:
    if backend == "orbbec":
        return _list_orbbec()
    if backend == "opencv":
        return _list_opencv(platform)
    raise ValueError(f"unsupported camera backend: {backend!r}")


def _open_orbbec(config: CameraConfig) -> OrbbecColorCamera:
    return OrbbecColorCamera.open(config)


def _open_opencv(config: CameraConfig, platform: str) -> OpenCVCamera:
    return OpenCVCamera.open(config, platform)


def open_camera(config: CameraConfig, platform: str):
    if config.backend == "orbbec":
        return _open_orbbec(config)
    if config.backend == "opencv":
        return _open_opencv(config, platform)
    raise ValueError(f"unsupported camera backend: {config.backend!r}")


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
        if (
            type(value) is not int
            or value < 0
            or (field != "cam_id" and value == 0)
        ):
            requirement = (
                "a non-negative integer"
                if field == "cam_id"
                else "a positive integer"
            )
            raise ValueError(f"{field} must be {requirement}")
        values[field] = value
    return CameraConfig(
        backend=backend,
        device_id=values["cam_id"],
        width=values["camera_width"],
        height=values["camera_height"],
        fps=values["camera_fps"],
    )
