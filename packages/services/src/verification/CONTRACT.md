# Verification service

The local desktop Host adapts typed RPC to the native runner socket. The runner owns the queue, stage transitions, snapshots and evidence. The desktop channel is injected only on the local base attachment. MCP calls the same runner.

The designQuery channel also starts immutable native coverage extractions, reads status and pages records. The runner owns the per-test and merged views, NPI evidence, database identity and full source exports. See the [coverage specification](../../../../specs/verification-coverage.md).

The designQuery channel reads the native verification tool catalog and creates project-owned starter scripts. Tool definitions are shared with MCP and the Python extension client. See the [tool catalog specification](../../../../specs/verification-tool-catalog.md).

See [the verification workbench specification](../../../../specs/verification-workbench.md).

Knowledge catalog, search, page reads, and bounded original-PDF ranges use this same channel. The runner owns the imported manual generations. Knowledge reads do not require a verification project. See the [knowledge specification](../../../../specs/verification-knowledge.md).

The catalog includes model filing progress. A source guide exposes checkpointed topics and their page evidence. The native runner owns the checkpoints. File selection starts the normal workspace Agent, which uses the same import and filing tools as a chat request.

The local `knowledgeFiling` channel stages files, follows indexing receipts and reads saved guides. It shares the verification socket and library with the existing read methods.

The `designQuery` channel starts a workspace-scoped Verdi NPI query against an explicit compiled KDB and retrieves it by ID. The native runner owns execution, status and evidence across the desktop, MCP and CLI. See the [RTL design query specification](../../../../specs/verification-npi-query.md).

The same channel exposes FSDB file discovery, signal catalogs, time-window extraction and display documents. The runner retains exact tick strings, NPI records and job IDs. The window manager opens a read-only waveform document for a completed workspace query. See the [FSDB specification](../../../../specs/verification-fsdb.md).

Formal profiles expose their backend and the run carries its actual engine label and property evidence. Portable and site-registered backends use the same submit, rerun and artifact operations. See the [Formal specification](../../../../specs/verification-formal.md).
