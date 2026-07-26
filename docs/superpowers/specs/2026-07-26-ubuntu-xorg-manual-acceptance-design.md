# Ubuntu Xorg Manual Acceptance Document Design

## Goal

Provide one Chinese, copy-and-run checklist for the remaining NeuGaze manual
acceptance work on Ubuntu 24.04 Xorg.

## Scope

- Create `docs/ubuntu-xorg-manual-acceptance.md`.
- Cover Ubuntu 24.04 Xorg only; do not include Windows testing.
- Use the connected Orbbec Gemini 335 as the primary camera.
- Keep OpenCV/V4L2 coverage, while marking an independent USB webcam test as
  conditional on such a device being available.

## Document Structure

1. Preconditions and safety rules.
2. Copyable environment, install-audit, runtime-diagnostic, and GUI commands.
3. Gemini 335 identification and sustained GUI preview.
4. Nine-point calibration, model saving, and model reload.
5. Absolute and relative gaze movement.
6. Left, right, middle, X1, X2, scroll, held/released keys, hotkeys, expression
   mapping, and wheel selection.
7. Overlay transparency, topmost behavior, click-through, and focus behavior.
8. ESC+Q resource and input cleanup.
9. Physical Gemini 335 disconnect behavior.
10. OpenCV/V4L2 checks, with the independent webcam case explicitly optional.
11. Result and evidence recording template.

## Failure and Safety Rules

- Runtime commands must not use `sudo`.
- A failed selected backend or device must remain visible.
- Do not retry automatically or switch camera backends.
- Stop the relevant test after an unexpected result and record the original
  error and traceback.
- Do not mark unexecuted or unavailable items as passed.

## Verification

- Cross-check every remaining manual item in
  `docs/ubuntu-xorg-port-progress.md`.
- Verify every command uses the bound `neugaze` environment and repository
  paths.
- Verify the document contains no Windows section.
- Run `git diff --check` and inspect the exact documentation-only diff.
