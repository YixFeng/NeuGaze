import sys

import pytest
from PySide6.QtCore import QProcess, QProcessEnvironment
from PySide6.QtWidgets import QApplication


@pytest.mark.x11
def test_pyside6_parent_waits_for_opencv_qt5_child_window():
    QApplication.instance() or QApplication([])
    process = QProcess()
    environment = QProcessEnvironment.systemEnvironment()
    environment.remove("QT_QPA_PLATFORM")
    process.setProcessEnvironment(environment)
    process.setProgram(sys.executable)
    process.setArguments(
        [
            "-c",
            """import cv2
import numpy as np

cv2.namedWindow("calibration-worker-probe", cv2.WINDOW_NORMAL)
cv2.imshow(
    "calibration-worker-probe",
    np.full((48, 64, 3), 225, dtype=np.uint8),
)
cv2.waitKey(20)
cv2.destroyAllWindows()
print("CALIBRATION_WORKER_WINDOW_OK", flush=True)
""",
        ]
    )
    process.start()

    try:
        assert process.waitForStarted(5000)
        assert process.waitForFinished(5000)
        assert process.exitStatus() == QProcess.NormalExit
        assert process.exitCode() == 0
        assert bytes(process.readAllStandardOutput()) == (
            b"CALIBRATION_WORKER_WINDOW_OK\n"
        )
        assert bytes(process.readAllStandardError()) == b""
    finally:
        if process.state() != QProcess.NotRunning:
            process.kill()
            process.waitForFinished(5000)
