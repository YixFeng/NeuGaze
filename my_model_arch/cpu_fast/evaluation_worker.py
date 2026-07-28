"""Run Ubuntu evaluation in a GUI-independent worker process."""

import argparse
from pathlib import Path
import signal
import sys
import threading

from . import desktop
from .calibration_worker import build_pipeline, load_config


def run_evaluation(config_path: Path) -> None:
    state = {
        "pipeline": None,
        "pipeline_cleanup_attempted": False,
        "desktop_cleanup_attempted": False,
        "stop_requested": False,
        "stop_failure": None,
        "evaluation_failure": None,
    }
    previous_handlers = {}

    def request_stop(signum, frame):
        state["stop_requested"] = True
        pipeline = state["pipeline"]
        if pipeline is None:
            return
        try:
            pipeline.request_evaluation_stop()
        except BaseException:
            state["stop_failure"] = sys.exc_info()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, request_stop)

    try:
        desktop.initialize()
        config = load_config(config_path)
        pipeline = build_pipeline(config)
        state["pipeline"] = pipeline
        if state["stop_requested"]:
            if not state["pipeline_cleanup_attempted"]:
                state["pipeline_cleanup_attempted"] = True
                pipeline.quit_pipeline()
        else:
            def evaluate():
                try:
                    pipeline.start_evaluation()
                except BaseException:
                    state["evaluation_failure"] = sys.exc_info()

            evaluation_thread = threading.Thread(
                target=evaluate,
                name="neugaze-evaluation",
                daemon=False,
            )
            evaluation_thread.start()
            evaluation_thread.join()

            evaluation_failure = state["evaluation_failure"]
            stop_failure = state["stop_failure"]
            if evaluation_failure is not None:
                _, error, error_traceback = evaluation_failure
                if stop_failure is not None:
                    _, cleanup_error, _ = stop_failure
                    error.add_note(
                        "pipeline stop also failed with "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
                raise error.with_traceback(error_traceback)
            if stop_failure is not None:
                _, error, error_traceback = stop_failure
                raise error.with_traceback(error_traceback)
            if not pipeline.quit:
                state["pipeline_cleanup_attempted"] = True
                pipeline.quit_pipeline()
        state["desktop_cleanup_attempted"] = True
        desktop.close()
    except BaseException as error:
        pipeline = state["pipeline"]
        if (
            pipeline is not None
            and not pipeline.quit
            and not state["pipeline_cleanup_attempted"]
        ):
            try:
                state["pipeline_cleanup_attempted"] = True
                pipeline.quit_pipeline()
            except BaseException as cleanup_error:
                error.add_note(
                    f"pipeline cleanup also failed: {cleanup_error!r}"
                )
        if not state["desktop_cleanup_attempted"]:
            try:
                state["desktop_cleanup_attempted"] = True
                desktop.close()
            except BaseException as cleanup_error:
                error.add_note(
                    f"desktop cleanup also failed: {cleanup_error!r}"
                )
        raise
    finally:
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    run_evaluation(arguments.config)


if __name__ == "__main__":
    main()
