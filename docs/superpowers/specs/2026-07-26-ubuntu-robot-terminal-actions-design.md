# Ubuntu Robot Terminal Actions Design

## Goal

Replace NeuGaze's Ubuntu keyboard and mouse action output with a small,
semantic robot-action path that can be verified in a terminal before any robot
controller is connected.

The first implementation validates this path:

```text
Gemini 335 RGB
-> facial-expression recognition
-> direct action or gaze-selected wheel action
-> RobotAction
-> one terminal line
```

Windows keeps its existing `game`, `game_cs`, `game_wz`, and `type` modes and
their keyboard and mouse behavior. Ubuntu has one `robot` mode and must not
emit keyboard, mouse-button, pointer-motion, or scroll events.

## Scope

This phase includes:

- an Ubuntu-only robot action configuration;
- seven initial robot action terms;
- one-shot terminal output;
- a four-direction gaze-selected wheel;
- removal of Ubuntu desktop input output;
- correction of the wheel's screen-to-window coordinate conversion;
- automated regression tests and a documented live acceptance procedure.

This phase does not connect to SONIC, select a reference-motion directory,
start a controller, send ZMQ data, or control a simulated or physical robot.
Those changes require a separate design after live recognition and wheel
acceptance passes.

## Platform Boundary

The two platform paths are explicit and mutually exclusive.

Windows:

```text
recognition -> existing key configuration -> Action -> desktop backend
```

Ubuntu:

```text
recognition -> robot action configuration -> RobotAction -> terminal
```

The Windows output path accepts only the existing keyboard/mouse `Action`.
The Ubuntu output path accepts only `RobotAction`. Receiving the wrong action
type at either boundary is an error. There is no fallback from robot output to
desktop input and no fallback from desktop input to robot output.

Xorg remains an Ubuntu runtime requirement for the GUI, wheel, and gaze
overlay. It is not used to inject input in robot mode.

## Robot Action Model

Use one immutable value object:

```text
RobotAction(
    action_id="move_forward_step",
    label="前进一步",
    source="wheel",
)
```

`action_id` is the stable machine-facing identity. `label` is the Chinese
wheel and terminal label. `source` is either `wheel` or `expression`.

The terminal emitter is one direct function, not a manager, factory, plugin
registry, transport abstraction, or background worker. It prints and flushes
one line:

```text
[ROBOT_ACTION] id=move_forward_step label=前进一步 source=wheel
```

This value object creates the future hand-off point. A later SONIC integration
can map `action_id` to a reference-motion directory without changing
recognition or wheel selection.

## Ubuntu Configuration

Ubuntu does not reuse `keyname`, `KEYPRESS`, or the four Windows modes. It uses
an independent configuration:

```yaml
robot_action_config:
  actions:
    move_forward_step: 前进一步
    move_backward_step: 后退一步
    turn_left: 左转
    turn_right: 右转
    wave: 挥手
    dance: 舞蹈
    stop: 停止

  expressions:
    numlock:
      wheel:
        - move_forward_step
        - move_backward_step
        - turn_left
        - turn_right
    left_click:
      action: wave
    num8:
      action: dance
    extra:
      action: stop
```

The existing expression evaluator IDs are retained so this phase does not
change facial recognition:

| Recognition ID | Facial action | Ubuntu behavior |
|---|---|---|
| `numlock` | Open and hold the mouth | Open the four-action wheel |
| `left_click` | Pucker the lips | Emit `wave` |
| `num8` | Raise the inner brows | Emit `dance` |
| `extra` | Blink the left eye without the right | Emit `stop` |

Other recognized expression and head-motion IDs have no action mapping in
Ubuntu robot mode. They remain recognition data but do not produce output.

Configuration validation runs before the live pipeline starts:

- every referenced action ID must exist in `actions`;
- every label must be a non-empty string;
- an expression must contain exactly one of `action` or `wheel`;
- a wheel must contain at least two valid action IDs;
- duplicate action IDs in one wheel are invalid;
- unknown keys in the owned robot-action schema are invalid.

Invalid configuration raises an error with the offending field path. It is
not ignored, rewritten, retried, or translated into an old key action.

## Trigger Semantics

Direct expression actions are one-shot:

- emit on the `False -> True` recognition transition;
- do not emit repeatedly while the expression remains true;
- do not emit on the `True -> False` transition.

The wheel is commit-on-release:

1. The `numlock` expression changes from false to true.
2. The wheel opens while the mouth remains open.
3. Gaze position updates the highlighted sector.
4. The mouth closes.
5. The selected `RobotAction` is emitted once and the wheel closes.

Closing the wheel without a valid selected sector is an expected,
user-visible cancellation rather than a robot action:

```text
[ROBOT_ACTION_CANCELLED] reason=no_selection source=wheel
```

Cancellation does not alter action state and does not choose a default sector.

## Wheel Layout and Gaze Selection

The Ubuntu robot wheel is a centered, borderless, semitransparent,
always-on-top `800 x 800` window with a default radius of 400 pixels.
Windows keeps its existing wheel configuration and behavior.

The four Ubuntu sectors have fixed spatial meaning:

```text
          前进一步

左转                    右转

          后退一步
```

Ubuntu robot mode uses gaze position, not head angle, for selection. Gaze
coordinates remain internal to NeuGaze and never move the Xorg pointer.

The current wheel receives screen coordinates where its selection code expects
canvas-local coordinates. The Ubuntu implementation must convert them
explicitly:

```text
local_x = gaze_screen_x - wheel_screen_left
local_y = gaze_screen_y - wheel_screen_top
```

Selection is calculated from these local coordinates. A point outside the
wheel produces no selected sector. No clamping may turn an out-of-wheel point
into a valid selection.

## Failure and Cleanup Behavior

Debuggability rules apply to the entire path:

- an old desktop `Action` reaching Ubuntu robot output is an error;
- a `RobotAction` reaching Windows desktop output is an error;
- an unknown action ID is an error;
- terminal write or flush failure propagates its original exception;
- wheel-thread failure is rethrown in the main pipeline with its traceback;
- cleanup attempts preserve the primary error and attach cleanup failures;
- no error causes retry, desktop-input fallback, cached output, or success
  output.

An unconfigured recognition ID is not an error because the Ubuntu action
configuration explicitly selects which recognition channels are enabled.

The `stop` term is only a validation event in this phase. Facial recognition
must never be treated as the sole emergency-stop mechanism for a real robot.
A physical emergency stop remains mandatory in future hardware testing.

## Automated Verification

Tests must verify behavior, not only mock call counts:

1. The seven action IDs resolve to their exact Chinese labels.
2. Every invalid configuration case fails with the relevant field path.
3. Each direct expression emits exactly once on activation.
4. Holding and releasing a direct expression emits nothing further.
5. Top, bottom, left, and right gaze positions select the specified actions.
6. Screen-to-window coordinate conversion remains correct on non-square
   screens and when the wheel window has a non-zero origin.
7. An out-of-wheel point followed by release prints only the cancellation
   line.
8. Ubuntu tests replace every desktop input function with a function that
   fails immediately, proving that no keyboard, mouse, pointer, or scroll
   operation occurs.
9. Passing an action across the wrong platform boundary fails visibly.
10. Existing Windows keyboard, mouse, hotkey, wheel, and cleanup tests remain
    green.
11. The full applicable Ubuntu test suite and compile/static gates run on the
    final source state.

## Live Acceptance

The live Ubuntu Xorg acceptance procedure uses the connected Gemini 335 and
records original terminal output.

1. Hold a neutral expression for two minutes and record any false trigger.
2. Test pucker, brow raise, and left-eye-only blink five independent times
   each.
3. Confirm each activation prints exactly one correct action line.
4. Confirm holding and releasing each direct expression adds no line.
5. Select each of the four wheel sectors five times, for twenty selections.
6. Confirm highlighted sector, spatial direction, action ID, and Chinese label
   agree on every selection.
7. Confirm holding the mouth open does not reopen the wheel or emit an action.
8. Close the wheel without a selected sector and confirm the explicit
   cancellation line.
9. Confirm no system pointer movement, key press, mouse click, or scroll is
   generated.
10. Exit and confirm the camera, wheel thread, overlays, and NeuGaze processes
    are gone.

Any failure remains failed and is recorded with its original logs. Threshold
or coordinate changes are made only from observed evidence and rerun through
the same acceptance procedure.

## Later SONIC Integration

After live acceptance, create a separate design for:

```text
RobotAction.action_id
-> validated reference-motion directory
-> SONIC selection/play interface
-> MuJoCo simulation
-> physical robot
```

GR00T WholeBodyControl loads reference motions as per-motion directories and
supports selecting and playing the loaded motion in reference-motion mode:

- <https://github.com/NVlabs/GR00T-WholeBodyControl>
- <https://nvlabs.github.io/GR00T-WholeBodyControl/references/motion_reference.html>

That later phase must use stable action IDs rather than display labels, test
all reference motions in MuJoCo first, preserve a physical emergency stop, and
define the exact SONIC process boundary before any real-robot command is sent.
