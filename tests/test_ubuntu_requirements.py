from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def read_ubuntu_requirements():
    requirements = {}
    lines = (REPOSITORY_ROOT / "requirements-ubuntu.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        requirement = Requirement(line)
        name = canonicalize_name(requirement.name)
        assert name not in requirements, f"duplicate requirement {name}"
        requirements[name] = str(requirement.specifier)
    return requirements


def test_ubuntu_requirements_have_exact_runtime_distribution_set_and_pins():
    assert read_ubuntu_requirements() == {
        "torch": "==2.6.0+cpu",
        "torchvision": "==0.21.0+cpu",
        "torchaudio": "==2.6.0+cpu",
        "numpy": "==1.26.4",
        "mediapipe": "==0.10.14",
        "opencv-contrib-python": "==4.11.0.86",
        "jsonlines": "==4.0.0",
        "filterpy": "==1.4.5",
        "onnxruntime": "==1.27.0",
        "tqdm": "==4.69.0",
        "pyside6": "==6.11.1",
        "scikit-learn": "==1.9.0",
        "ncnn": "==1.0.20260526",
        "pyyaml": "==6.0.3",
        "python-xlib": "==0.33",
        "pyorbbecsdk2": "==2.1.1",
    }


def test_ubuntu_requirements_never_install_both_opencv_wheels():
    requirements = read_ubuntu_requirements()
    opencv_distributions = {
        "opencv-python",
        "opencv-contrib-python",
    } & requirements.keys()

    assert opencv_distributions == {"opencv-contrib-python"}


def test_readmes_document_exact_opencv_collision_repair():
    repair_sequence = (
        "python -m pip install -r requirements-ubuntu.txt\n"
        "python -m pip uninstall -y opencv-python\n"
        "python -m pip install --no-deps --force-reinstall "
        "opencv-contrib-python==4.11.0.86"
    )
    approved_pip_check_failure = (
        "pyorbbecsdk2 2.1.1 requires opencv-python, which is not installed.\n"
        "ncnn 1.0.20260526 requires opencv-python, which is not installed."
    )

    for filename in ("README.md", "README-CN.md"):
        text = (REPOSITORY_ROOT / filename).read_text(encoding="utf-8")
        assert repair_sequence in text
        assert approved_pip_check_failure in text
        assert "No broken requirements found." not in text

    progress = (
        REPOSITORY_ROOT / "docs/ubuntu-xorg-port-progress.md"
    ).read_text(encoding="utf-8")
    assert approved_pip_check_failure in progress
    historical_successes = [
        line
        for line in progress.splitlines()
        if "No broken requirements found." in line
    ]
    assert len(historical_successes) == 3
    assert all(
        "已废止历史证据" in line and "不是当前 gate" in line
        for line in historical_successes
    )
