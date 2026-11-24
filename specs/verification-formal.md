# Portable Formal verification

The workbench and Agent submit the same named Formal profile through the verification service. Jobs owns admission, immutable project inputs, the deadline, cancellation, run IDs and evidence. Reruns use the original snapshot and backend. A profile cannot supply an executable to the host.

```text
workbench / MCP → Jobs.submit → snapshot → backend → per-property evidence → run.json
workbench / MCP → Jobs.get / readArtifact ← same run ID
```

* The portable default is Yosys with SMTBMC and Z3. Each required, named assertion is checked from reset and optionally by induction. Covers report observed reachability. Bounded success includes the checked depth. Inconclusive induction, an unreached cover, inconsistent assumptions, and a missing property cannot establish a proof. Reachable failures export a VCD. The open frontend accepts the documented synthesizable SystemVerilog and clocked immediate assertions.
* Existing Formal profiles with a Tcl script and no backend select IFV. The FIFO provides both a portable profile and an optional IFV profile. Installing an optional licensed backend does not add a mandatory stage gate.
* A site can register a commercial adapter by ID outside the project. The job passes a versioned JSON request with the immutable inputs, working directory, top, filelist, named properties, variant and seed. The adapter returns a bound result with tool/version, property states and optional raw reports or waveforms. Jobs validates the result and publishes evidence from that run only. Missing or invalid reports, license failure, timeout and cancellation remain distinguishable.
* A relocatable, offline distribution includes the interpreter, pinned toolchain, runner, an editable FIFO project and a launcher. It runs without system Python, EDA installations, a license server, or an Internet connection. A per-user local endpoint is shared by the desktop and MCP. The build verifies source archive hashes and includes upstream notices.

Acceptance includes the same golden FIFO and simultaneous-operation defect on Windows x64 and Linux x86-64 from clean extracted bundles, plus bounded mode, a second independent DUT, incomplete adapter evidence, and IFV on a licensed host.

## CentOS 7 portable desktop

A single Linux x86-64 `.run` opens the packaged Electron application from the user's X11 session. Invoking it through Bash also works on a downloaded file without an executable bit. The first launch expands verified bytes in the user's cache. Later launches reuse them. The bundle accepts a project directory and opens a writable per-user FIFO example by default. User settings, documents, and verification history live outside the distribution cache.

The package carries its desktop libraries and an isolated Linux runtime for CentOS 7 hosts with disabled unprivileged namespaces. The host account starts it without installing RPMs, changing kernel settings or using an administrator account. Chromium keeps its sandbox. Hardware acceleration is optional. The verification runner and commercial EDA processes execute under the caller on the host and retain its license environment. Only the selected project, required user paths and the local display and service are shared with the desktop runtime.

A private build may select knowledge sources by ID. It carries each selected source PDF, page index and available model guide. First use adds missing sources to the user's library, preserving documents the user has already filed. The project’s private handoff includes the NPI manual.

```text
shell → verified user cache → isolated Electron window → local verification service → host EDA
                                     Agent MCP ────────┘                            → run evidence
```

On the packaged desktop, starting the JavaScript database worker under software CPU emulation can exceed the native 30-second first-response window. Allow up to three minutes for the first storage status on this runtime. A usable workspace still requires explicit storage readiness.

Acceptance exercises a fresh home, a path with spaces, software execution on a CentOS 7 kernel with namespaces disabled, an actual desktop window, successful and failing FIFO runs, and a second launch that preserves the original evidence.
