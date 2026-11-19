# Native coverage data extraction

The workspace Agent, desktop verification workbench and local CLI read the same immutable extraction by ID. The input is a VCS coverage database directory (.vdb), a path inside it, or a completed verification run containing it. Each saved extraction contains every record traversed by the installed Verdi NPI Coverage Model, without a display row cap. Tests retain their separate identities and provenance. Read native hierarchy, code coverage (line, condition, branch, toggle, FSM), assertions, functional covergroups and crosses, and low-power coverage when available. Keep object kinds, relationships, source locations, reported counts, goals, status flags, and covered-test attribution when NPI exposes them. Optional report exclusions are applied per test in memory. The original database is read only.

```text
desktop / MCP / CLI → native queue → isolated Verdi NPI process → complete SQLite + JSON Lines export
                                                        ↳ status and paged, filtered record reads
```

The runner owns job IDs, source identity and results. Reject a changed input during extraction. Publish exports only after the traversal finishes. Interrupted or malformed inputs report a failure. An absent test result is distinct from zero hits. A shape-only VDB can export static coverage shape without fabricating measurements. The UI labels counts as record counts and presents only counters exposed by the model. Rows link to parent IDs and preserve per-test and per-instance hierarchy. Status bits (including exclusions) remain available in raw and decoded form. An export includes all native rows in JSON Lines and SQLite, plus the original VDB files with a SHA-256 manifest and a streamed XML-node export for additional vendor fields. An XML member that cannot be decoded is identified in the manifest together with its original bytes in the archive. The complete export remains available after restart. Existing summary reports and waveform tools keep their entry points.

Acceptance uses a real VCS multi-test design with distinct stimuli, compared with independent URG reports, including at least one uncovered functional bin, its hit counterpart, assertion data, bit-level toggle directions, branches, conditions, line and FSM bins. Page through all records without losing or repeating IDs, open by job ID from the desktop and MCP, and reject invalid input. Report any coverage family for which the fixture has no real data.

