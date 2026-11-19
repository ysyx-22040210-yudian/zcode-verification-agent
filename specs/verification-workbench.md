# Local verification workbench

The workbench and the verification MCP server use one host-side runner socket in the CentOS 7 development VM. The runner owns admission, per-workspace job history, source snapshots, stages, and evidence. Closing or reloading the UI leaves the job's owner running.

## State flow

```text
Electron renderer -> ZCode service channel -> runner socket
ZCode Agent -> verification MCP (stdio) -> runner socket

request -> validate project + snapshot inputs -> queued -> running -> result
read -> workspace-scoped manifest + bounded artifact or waveform excerpt
cancel -> runner signals its process group -> cancelled
rerun -> previous immutable inputs + profile -> a new run ID
```

A missing tool, license failure, timeout, incomplete report, or non-zero compile result is explicit. IFV properties store proof, counterexample, bounded or unknown status and cover reachability individually. A native report or checked SV/UVM result is required for a passing verification run. Coverage is reported from executed tests.

## Product surface

A local workspace with an available runner exposes a Verification view. Read and mutation requests carry the workspace path, and the runner checks that a requested job belongs to that workspace. Remote workspaces keep their existing behavior. A browser snapshot or an Agent claim cannot update the runner's records.

The FIFO acceptance exercises good and mutated RTL through VCS/UVM and IFV, enables evidence links and replays, and checks that a run submitted through MCP appears by the same ID in the Electron view.

The local toolbar also opens the [Knowledge base](verification-knowledge.md), which uses the same native service for indexed reference manuals.

When the workbench has room for two columns, the run history and selected evidence extend to the bottom of the window. Long history and evidence scroll within their own panels. A narrow workbench stacks the panels in the page scroll and keeps long evidence in a scrollable viewer. Native desktop acceptance resizes the same FIFO report between short, tall, and narrow windows, then opens a counterexample waveform.

## Local desktop startup

When the native launcher opens a local project with `ZCODE_VERIFICATION_SOCKET` configured, the desktop window opens the Verification view. The window bootstrap owns this decision for the lifetime of the renderer. Workspace restore and verification do not wait for model provisioning or require an account. The first-run occupation onboarding does not open automatically in this window. Verification calls still use the runner socket, and an unavailable runner is reported by the Verification view.

Account and provider setup remains available on request. Users can dismiss the login screen and return to the workbench. Signing out or losing a model account connection leaves the workbench usable. Model requests use the configured provider's authentication. A standard desktop launch without the runner keeps its regular startup behavior.

Acceptance uses a fresh native profile with no accounts or model configuration. The first view must show the FIFO verification plan without login. The user can run SV, UVM and Formal, dismiss optional sign-in, and still find the run after restarting.
