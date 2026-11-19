# Verification workbench

A local desktop workspace renders the runner's view of its verification plan and history. The UI owns selection, form input and the selected artifact. It uses the typed service to submit jobs and checks. It refreshes the current projection while visible so runs submitted by Agent become available by the same ID.

The RTL query page accepts a KDB file selection or VM path, submits instance or signal queries against that build and opens existing IDs in the same local workspace. It displays the runner's hierarchy, endpoint source sites, interface bindings, partial results and truncation. See the [RTL design query specification](../../../../specs/verification-npi-query.md).

The FSDB page selects recorded signals and a time or trigger interval. It reopens retained waveform jobs and displays the same standalone waveform document in an embedded or dedicated native window. A new file selection invalidates earlier asynchronous selections. See the [FSDB specification](../../../../specs/verification-fsdb.md).

The coverage view selects a VDB path or verification run. It reads the native runner's test views and pages from the same extraction as MCP. Filters, paging cursors and the selected record are local to this view. See the [coverage specification](../../../../specs/verification-coverage.md).

The workspace Tool button opens the verification catalog. The catalog reads definitions through the injected designQuery channel, opens an existing native view, or sends the user's analysis or development request through the shell. See the [tool catalog specification](../../../../specs/verification-tool-catalog.md).

See [the verification workbench specification](../../../../specs/verification-workbench.md).

The module also renders the native knowledge catalog, search results, page text, and original PDF preview through the same typed service. Reader selection and pending search belong to the UI. Source generations, metadata, indexed text, and PDF bytes belong to the runner. Stale search and page results are discarded on selection changes. See the [knowledge specification](../../../../specs/verification-knowledge.md).

Selecting a PDF or continuing an unfinished guide starts an ordinary Agent turn for the active local workspace. The library displays the persisted filing progress, model topics and their original page references. The conversation runtime owns model selection, tool permissions and the task history.
