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
