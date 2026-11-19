# Native FSDB waveform window

A local ZCode user can select a VM FSDB, search its recorded signals by hierarchical name, select several traces, and open a waveform window inside the desktop. The same operations are available to the workspace Agent. Read a closed time interval or locate a recorded trigger transition and request ticks before and after it. Use the file's scale and exact integer tick strings throughout, including when ticks exceed JavaScript's safe integer range. Four-state digital signals retain X and Z. Show widths, full hierarchy and bus values, a shared cursor, and zoom and pan on a common time axis.

```text
Workspace desktop / Agent → native runner → Verdi NPI FSDB model → durable query ID
                                                       ↓
                        recorded initial value + ordered changes → waveform window
```

The native runner owns query IDs, bounded samples and original file identity. The renderer owns selected signals, cursor and view range. A search enumerates signal metadata; a wave request reads only selected signals and its trigger. A view reopened by ID displays the saved samples even when the source later changes. File replacement between selection and a new read, errors and missing signals are explicit. A last-known value is valid until the first omitted transition; the rest of a truncated lane is visually unavailable. Before a signal's first recorded value the lane is unavailable. A no-transition signal retains its value at the left boundary. A partial search is labeled. Clock ticks use the FSDB time scale; rising/falling match 0→1 / 1→0, and change includes X/Z transitions. A missed trigger is distinct from an empty signal catalog.

Completed SV/UVM runs register FSDB files produced in their run directory as binary waveform evidence. The workbench opens them by run ID and artifact name. Searches and extractions accept UTF-8 project and file names, including spaces. A successful extraction includes the path to its saved interactive HTML document.

Use VCS to dump a small reproducible SystemVerilog design containing two instances with like-named signals, a four-state control, a bus and a stable signal. Compare NPI samples with known stimulus and the vendor FSDB-to-VCD decoder, exercise trigger prehistory, narrow windows, missing signals and truncation. Verify the native Electron window, cursor, zoom and reopening an Agent query. Existing VCD previews retain their entry point.

