# iOS integration (WDA driver and SDK agent)

This branch adds a WebDriverAgent driver, a localhost task console and iOS
SDK initialization for the existing Flash and Pro engines. The native dashboard supports selecting a physical iPhone/iPad or booted iOS simulator, WDA readiness, queued SDK tasks, live preview and step replay. Android recording and diagnostics remain platform-specific. Do not use
`artemis run --device-serial <ios-udid>` as an iOS entry point.

## Supported path

`artemis ios ui/inspect` → owned device lease → iOS context → existing MCP action
server → IOSActuator → IOSWdaDriver → WebDriverAgent.

Implemented: screenshot, native hierarchy, pixel/point conversion, tap, repeated
tap, long press, swipe, focused text append/clear, home/enter/delete, launch and
terminate by bundle ID, foreground app lookup. Device shell, Android Back and
recording explicitly reject requests. Screen orientation changes reject stale
coordinate actions and require a new observation. Actions are not retried by the
transport, since an HTTP timeout does not prove an action did not execute.

## Prerequisites

Use a dedicated device and a dedicated WDA endpoint. The device ID is a caller
provided mapping to that endpoint; WDA status does not attest the UDID. Never
point two device IDs at one endpoint. The Artemis lease coordinates Artemis
clients, not other WDA clients.

On macOS install Xcode and an iOS simulator runtime. Build official Appium
WebDriverAgent with the WebDriverAgentRunner scheme for the chosen UDID. For a
simulator, code signing can be disabled. For a real device, configure an Apple
signing team and provisioning, enable Developer Mode and device trust, and expose
its WDA port through the chosen USB tunnel. This patch does not select a team,
change signing credentials, or automatically provision a real device.

The new driver uses an already running WDA HTTP(S) endpoint. Prefer loopback
forwarding; WDA itself is a device-control service, not an authenticated public API.

## Usage

From this workspace, use the launcher (it supplies local source import paths):

```sh
sh scripts/artemis-ios.sh inspect --device-id <UDID> --wda-url http://127.0.0.1:8100 --output artifacts/ios-observation
sh scripts/artemis-ios.sh ui --device-id <UDID> --wda-url http://127.0.0.1:8100 --port 8011
```

Open http://127.0.0.1:8011. The page supports manual control plus task submission, status and cancellation.
Each manual action owns a short WDA session and device lease. During a task, manual
control returns HTTP 409; the SDK worker owns the device lease. Cancellation sends
SIGINT, waits for SDK cleanup and process exit, then restores manual access.
Server shutdown cancels and awaits its worker. It does not stop WDA or the device.

For SDK integration, use `artemis.drivers.ios.session.ios_session(device_id, url)`
as an async context manager. It yields `(context, driver, action_session)`.
Use the existing MCP wire schema: click `{target: [x,y]}`, swipe `{start: [x,y],
end: [x,y]}`, input `{text, clear_exist}`, manage_app `{action, app_name}`.
Coordinates at the MCP boundary are normalized 0–1000. Driver coordinates are
physical screenshot pixels; WDA coordinates are logical points.

## Verification and limits

Deterministic tests cover geometry, Unicode input/clear, semantic WDA errors,
unsupported commands, actuator failures and platform routing. Existing action
session/server/actuator regression tests also run. A real simulator smoke script
in the workspace (`scripts/ios_smoke.py`) launches Settings, reads its hierarchy,
clicks Search, types and replaces text, verifies the actual field value, swipes,
returns home and checks unsupported Back handling. It is tied to the dedicated
integration simulator and is not a general benchmark.

Real-device compatibility requires a separate run on the user-selected device.
The scripted smoke does not evaluate a model. Separate model-driven simulator
checks completed with Gemini Flash/Pro and Qwen Flash; they are small integration
checks, not benchmark scores or evidence of real-device compatibility.

## Autonomous SDK tasks and local models

The SDK builder now supports `.for_ios_device(udid, wda_url)`. Initialization
requires no ADB. The SDK acquires its normal per-device queue lease, connects WDA,
sets screenshot dimensions and the iOS actuator, runs Flash or Pro, and closes
WDA before releasing the lease. App installation and app locking fail explicitly.
Video and Android device probes are disabled; ADB/diagnostic tools are filtered.
Idle UI holds no device lease. Avoid running an external SDK task while using
manual controls; the global device lease still arbitrates separate processes.

Workspace launcher:

```sh
sh scripts/ios-agent.sh --model gemini --profile flash \
  --device-id <UDID> --wda-url http://127.0.0.1:8100 \
  --goal 'Open Settings and verify its main title. Do not change settings.' \
  --max-steps 8 --timeout 180
```

Use `--model qwen` or `--profile pro` to select the other configurations. Results
are written to `benchmark/ios-agent-<model>-<profile>.json`; detailed traces stay
in the ignored local `traces/` directory. A completed status is the agent report,
not a universal assertion that every user requirement was checked.

`scripts/artemis_model_config.py` reads `.env.ios` and `config/ios-models.json`
from this standalone project. The local credential file is ignored by Git and has
owner-only permissions. It was initialized from the authorized APP-tester model
settings; ordinary runs no longer depend on APP-tester or the research workspace.
An explicit `APPTESTER_DIR` override remains available if desired. Gemini uses the configured GEMINI_MODEL, or
`gemini-3.8-flash` when absent (2.5-flash was rejected by the API). Qwen uses the
DashScope API, not the previously tested local Ollama model. The Qwen extra body
is preserved through LLM config, endpoint and client construction. Visual step
summaries respect the selected non-Google provider instead of requiring a hidden
Google client.

`scripts/ios_model_probe.py --model gemini|qwen` tests image input and a function
call using a synthetic red image, without sending a device screenshot. Both
passed. Device-task tests do send the selected simulator observations to the
selected model service. The console invokes this same SDK runner in a separate process per task, so
Gemini and Qwen environment settings do not leak into each other. It shows the
last pre-task screenshot during execution and refreshes after completion. A
completed label explicitly describes the agent report, not an independent pass.
Run results and logs are saved under ARTEMIS_APP_DIR/web-runs with unique IDs.
The UI currently shows only the latest task; restart clears its in-memory status.
Real-device USB connection and screenshot retrieval were verified on 2026-10-21 using a connected iPhone. A subsequent native port-8000 Gemini Flash task verified the Settings title on the physical phone and persisted its result and screenshot in Workspace.

## Real-device preflight and deployment

Read-only inventory: `.venv/bin/python scripts/ios-device-preflight.py`.
Add `--use-apptester` to check APP-tester's configured iOS UDID and team without
printing secrets. A blank device ID does not select an arbitrary paired phone.
Paired/disconnected inventory does not prove a device is ready for deployment.

After selecting an attached, trusted, unlocked phone with Developer Mode enabled:

```sh
sh scripts/ios-wda-device.sh <UDID> <TEAM_ID>
# In a separate terminal, use a different host port from the simulator WDA:
sh scripts/artemis-ios.sh usb-ui --device-id <UDID> --wda-port 8101 --port 8012
```

The build script uses the official local WDA checkout and existing Xcode signing.
It does not automatically change developer accounts, accept agreements, enable
Developer Mode, or create provisioning permissions. Signing account or provisioning errors must be fixed in Xcode. Build products default to the per-user temporary directory to avoid Finder metadata added by synced folders; override with ARTEMIS_WDA_BUILD_DIR.

`artemis ios devices` lists physical devices only and reports USB presence separately from the CoreDevice tunnel. A disconnected tunnel does not mean the USB phone is absent. `usb-ui` requires an explicit USB UDID, checks WDA status, binds forwarding only to loopback, and terminates its own proxy when the console exits. It never falls back to a simulator. The native port-8000 dashboard now uses this driver through a platform-specific queue worker; see README_IOS.md for its setup flow.

## iPad simulator validation

On 2026-10-21, the native port-8000 dashboard completed a three-step Gemini Flash task on an iPad Pro 11-inch (M5), iPadOS 26.5 simulator: launch Settings, navigate to General → About, and report version/model. Screenshot replay was verified. Session: `532b7eb5-e511-4d7e-8bf9-c5554edff272`. Physical iPad hardware has not yet been validated.

Start simulator WDA with `sh scripts/ios-wda-simulator.sh <simulator-UDID> 8102`, then select the booted simulator in the native dashboard and use `http://127.0.0.1:8102`. Use a separate port per device. The connection checks simulator/physical and iPhone/iPad type consistency.
