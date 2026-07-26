from pathlib import Path

import pytest

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


EXACT_EXTRA_INDEX = (
    "--extra-index-url https://download.pytorch.org/whl/cpu"
)


def parse_ubuntu_requirements(text):
    requirements = {}
    extra_index_count = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            assert line == EXACT_EXTRA_INDEX, f"unsupported directive {line!r}"
            extra_index_count += 1
            continue
        requirement = Requirement(line)
        assert requirement.extras == set()
        assert requirement.marker is None
        assert requirement.url is None
        specs = list(requirement.specifier)
        assert len(specs) == 1 and specs[0].operator == "=="
        name = canonicalize_name(requirement.name)
        assert name not in requirements, f"duplicate requirement {name}"
        requirements[name] = requirement
    assert extra_index_count == 1, (
        f"expected one exact extra-index directive, got {extra_index_count}"
    )
    return requirements


def read_ubuntu_requirements():
    parsed = parse_ubuntu_requirements(
        (REPOSITORY_ROOT / "requirements-ubuntu.txt").read_text(
            encoding="utf-8"
        )
    )
    return {
        name: str(requirement.specifier)
        for name, requirement in parsed.items()
    }


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


@pytest.mark.parametrize(
    "directive",
    (
        "--index-url https://example.invalid/simple",
        "--extra-index-url https://example.invalid/cpu",
        "--find-links ./wheels",
        "-r other-requirements.txt",
    ),
)
def test_requirements_parser_rejects_directive_bypasses(directive):
    text = (
        "--extra-index-url https://download.pytorch.org/whl/cpu\n"
        f"{directive}\n"
        "numpy==1.26.4\n"
    )
    with pytest.raises(AssertionError):
        parse_ubuntu_requirements(text)


def test_requirements_parser_requires_one_exact_extra_index_directive():
    with pytest.raises(AssertionError):
        parse_ubuntu_requirements("numpy==1.26.4\n")
    with pytest.raises(AssertionError):
        parse_ubuntu_requirements(
            "--extra-index-url https://download.pytorch.org/whl/cpu\n"
            "--extra-index-url https://download.pytorch.org/whl/cpu\n"
            "numpy==1.26.4\n"
        )


def test_every_runtime_requirement_is_plain_exact_pin():
    requirements = parse_ubuntu_requirements(
        (REPOSITORY_ROOT / "requirements-ubuntu.txt").read_text(
            encoding="utf-8"
        )
    )
    for requirement in requirements.values():
        assert requirement.extras == set()
        assert requirement.marker is None
        assert requirement.url is None
        specs = list(requirement.specifier)
        assert len(specs) == 1
        assert specs[0].operator == "=="
        assert specs[0].version


def test_ubuntu_install_order_and_admin_boundaries_are_documented():
    ordered = (
        "conda create -n neugaze python=3.11.11",
        "conda activate neugaze",
        "export NEUGAZE_ORBBEC_SDK_ROOT=/absolute/path/to/OrbbecSDK_v2",
        "python scripts/check_ubuntu_install.py --orbbec-sdk-root \"$NEUGAZE_ORBBEC_SDK_ROOT\" --require-overlay",
        "python -m pip install -r requirements-ubuntu.txt",
        "python -m pip uninstall -y opencv-python",
        "python -m pip install --no-deps --force-reinstall opencv-contrib-python==4.11.0.86",
        "python scripts/check_ubuntu_runtime.py --config configs/cpu.yaml --require-overlay",
    )
    required_commands = (
        "sudo apt-get update",
        "sudo apt-get install --no-install-recommends xcompmgr libxcb-cursor0",
        "sudo apt-get install --no-install-recommends xvfb",
        "sudo \"$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/install_udev_rules.sh\"",
        "sha256sum \"$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/99-obsensor-libusb.rules\"",
        "cmp --silent \"$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/99-obsensor-libusb.rules\" /etc/udev/rules.d/99-obsensor-libusb.rules",
    )
    for filename in (
        "README.md",
        "README-CN.md",
        "docs/superpowers/specs/2026-07-23-ubuntu-xorg-port-design.md",
        "docs/superpowers/plans/2026-07-24-ubuntu-xorg-port.md",
    ):
        text = (REPOSITORY_ROOT / filename).read_text(encoding="utf-8")
        assert "\n".join(ordered) in text
        for command in required_commands:
            assert command in text
        assert "check_ubuntu_install.py" in text
        assert "pyorbbecsdk2==2.1.1" in text
        assert "SDK 2.8.6" in text
        assert "Ubuntu on Xorg" in text


def test_progress_records_final_review_commits_and_manual_boundaries():
    progress = (
        REPOSITORY_ROOT / "docs/ubuntu-xorg-port-progress.md"
    ).read_text(encoding="utf-8")
    for commit in (
        "84a68dc", "9217ae8", "0c485eb", "06b7123",
        "ca0c631", "4950cce",
    ):
        assert commit in progress
    assert "12/12" in progress
    assert "Windows 实机" in progress
    assert "用户批准" in progress
