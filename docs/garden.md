# OcuSense Garden

A native PySide6 game under **Games → OcuSense Garden**, with original vector
artwork: one continuous grassy patch, blue sky, a cottage, wooden fencing,
connecting dirt paths, and full vegetable beds. Small ink stars and primary-color
accents add a light Miró influence. No additional dependencies or downloaded assets.

## Run and play

From the project directory:

```sh
.venv/bin/python -m ocusense
```

1. Open Games, then OcuSense Garden. All six starter crops are planted; one spare
   seed of every type is also free.
2. Select a thirsty crop. Choose **Use my eyes** after calibrating on the Study
   page, or **Use manual alternative**. Manual mode is explicitly self-confirmed:
   follow each instruction, then hold the button for two seconds. Release between steps.
3. The camera path automatically advances after two continuous seconds with both
   eyes open, then closed. Briefly reopen before the final gentle two-second closure.
4. Watering starts that plot's independent growth timer. Close the game or app;
   plants continue growing without further exercises.
5. When ready, select **Collect!**. Coins are awarded once, the plot becomes empty,
   and you can choose another seed. Use Garden shop for seeds, flowers, a cobalt
   watering can, a constellation mobile, or up to three extra beds.

| Crop | Growth time | Harvest | Seed price |
|---|---:|---:|---:|
| Strawberries | 2 hours | 25 | 3 |
| Carrots | 3 minutes | 10 | 2 |
| Tomatoes | 5 minutes | 35 | 4 |
| Lettuce | 45 minutes | 8 | 1 |
| Blueberries | 4 hours | 50 | 5 |
| Pumpkins | 6 hours | 80 | 8 |

The table is configured in `ocusense/core/garden.py`. Crops show four stages:
seedling, leafy plant, flowering plant, fruit. Watering and harvest animations
follow the app's Animations setting and macOS Reduce Motion. Every plot is a
keyboard-focusable button with an accessible state label. The grid reflows with
window width; the containing Games page scrolls.

Garden reminders are off initially. Enable them in the garden and choose 5–120
minutes of monitored study time. The in-app reminder opens the garden, snoozes for
10 minutes, or disables reminders. No browser notifications or new OS permissions
are required by this desktop implementation.

## Implementation map

- `ocusense/core/garden.py`: crop configuration, plot lifecycle, growth fraction,
  seed inventory, coin rewards and purchases.
- `ocusense/core/garden_exercise.py`: timestamp-based eye holds and reminder clock.
- `ocusense/garden_store.py`: validated loading and atomic, rollback-on-failure saves.
- `ocusense/ui/blink_garden_page.py`: garden controller, responsive grid, reminder integration.
- `ocusense/ui/garden_dialogs.py`: eye exercise, accessible manual mode, shop and planting dialogs.
- `ocusense/ui/widgets/garden_art.py`: original crop illustrations, sky, four growth
  stages, watering drops and harvest/basket effects.
- `ocusense/ui/games_page.py`: game card and routing of existing camera updates.
- `ocusense/ui/main_window.py`: garden reminder card in the existing monitoring lifecycle.
- `tests/test_garden.py`: exercise, economy, persistence, reminder and UI tests.

The existing monitoring pipeline supplies per-eye calibrated openness and observation
validity/timestamps. The exercise controller consumes these measurements without
recomputing EAR or replacing blink detection. Both eyes must independently pass the
app's existing open/closed thresholds for every observation throughout each hold.
This continuous hold requirement rejects transient changes. Wrong states, tracking
loss, non-increasing timestamps, and frame gaps over the existing maximum reset
current hold progress. Completed steps remain complete. The final closure requires
an intervening reopening so one long closure cannot count twice.

Camera access uses `start_game_camera` / `stop_game_camera`. Existing study recording
and statistics remain isolated from game observations. Canceling, leaving Games,
or finishing an exercise stops the camera. Camera errors never complete steps.

## Persistence and limits

`~/Library/Application Support/OcuSense/garden.json` stores coins, seeds, decorations,
reminder choices, and each crop's absolute watering/harvest timestamps. The
`OCUSENSE_GARDEN_FILE` environment variable overrides the path for tests. A
preferences-file override also relocates the default garden save beside it.

Absolute deadlines are checked when rendering, harvesting, and loading. Harvesting
clears the plot in the same saved transaction as the coin reward, preventing repeated
clicks or reopening from awarding the same crop again. A failed write restores the
previous in-memory state and shows an error. Malformed saves are preserved and
changes are disabled. An interrupted exercise returns to Needs water after restart.

This is a local, single-app-instance economy, not a server-authoritative multiplayer
system. Editing the save or changing the system clock can alter progression. The old
prototype's break/water counters are left untouched in preferences; they do not become
coins. The garden has its own state file.

Eyelid squeezing is **not** measured. The supported configurable detection mode is
`bilateral_closure`; unsupported modes fail explicitly. Manual mode is a self-confirmed
accessibility alternative, never presented as camera verification. Actual camera
play with a person still needs a live-device check; automated tests use synthetic
calibrated observations. This implementation is for the desktop app, not the separate
website or a mobile browser.

## Verification

```sh
.venv/bin/python -m unittest tests.test_garden tests.test_main_window tests.test_preferences tests.test_morse tests.test_runner tests.test_structure
QT_QPA_PLATFORM=offscreen .venv/bin/python -m ocusense --self-test
```

The focused integration suite covers exercise progression and interruptions,
cancellation, independent timers, restart after deadlines, duplicate rewards,
shop purchases, save rollback, corrupt data, reminders, manual play, and synthetic
camera play. The app self-test loads the existing model and processes a blank frame;
it does not open a webcam. A new packaged macOS application is not built or installed
by this change.
