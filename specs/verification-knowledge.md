# Verification knowledge library

The local native desktop exposes a Knowledge base option beside Verification. It lists the manuals imported into the native runner, including their title, version, original filename, page count, and digest. A user can search API names and English or supported Chinese topic names, browse chapters, read indexed pages, and view the corresponding original PDF page. Search results carry the source ID, title, version, PDF page, section, and an excerpt. Reader navigation uses one-based PDF page numbers.

The runner owns the library at its project-level knowledge directory. Each imported manual has an immutable generation containing its PDF and an SQLite FTS4 index. An atomic catalog update publishes a completed generation. Reimporting the same bytes is idempotent. Read operations snapshot a catalog generation, reject invalid IDs, pages, and byte ranges, and never accept a caller-supplied filesystem path. An empty library returns an empty catalog. A damaged index is reported as an error.

The importer extracts all PDF pages and bookmarks, preserves source metadata and layout-aware text, and records pages without extractable text. It indexes page text and section names and supports the CentOS 7 SQLite runtime. Large PDFs are read in bounded ranges by the existing PDF viewer. Original page rendering remains available for figures, object diagrams, tables, and extraction artifacts.

The desktop uses the existing typed verification service and runner socket. The MCP adapter provides knowledge_list, knowledge_search, and knowledge_read against the same library. Tool descriptions tell the Agent to search before answering questions about a manual, read relevant pages, cite source version and PDF page, and treat retrieved text as reference material. Model credentials are unnecessary for browsing and searching the library.

During implementation, when indexed material is insufficient, absent, ambiguous, or loses a figure, table, or code layout, the Agent can call knowledge_read_original. This reads the retained PDF directly and returns fresh layout-aware text and page images with source digest, version, and one-based PDF page numbers. It works independently of the text index. Large page images are divided into labeled regions so their original resolution fits the Agent's image input limit. Page count, rendering time, and response size are bounded, and failures return an explicit tool error. References from the document remain untrusted reference data.

The native launch environment mounts the local knowledge directory read-only for Agent file access. Original-read results include the retained PDF path, and the Agent may use the installed document tools to read it further. The normal lookup tool descriptions identify original-document reading as the next step when knowledge is insufficient. Reading neighboring pages and citing original source evidence is part of this workflow.

The source PDF and generated indexes are local application data. Import tooling and UI belong to the repository. The initial library is the user-provided VC Apps Native Programming Interface manual, O-2018.09-SP2, with 3,568 pages.

Acceptance imports the complete manual, confirms exact API and Chinese topic search, opens a result and the original PDF at its cited page, reads a code example and chapter, checks boundary errors and concurrent search, and finds the same library after a native desktop restart. MCP search and read must return the same source and page as the UI.

Original-document acceptance covers an API page, a diagram page, invalid page selection, a missing renderer, an unavailable index with an intact source PDF, and a real desktop Agent tool call that receives source-page images and a citation.

## Image input per model

The provider's model editor lets the user designate a vision model under Advanced configuration → Input types. The effective `properties.inputFormat.supportsImage` of the model executing each turn owns this decision. An explicit off overrides recommendations for that provider/model. Unknown models default to text for images. The decision applies to pasted images, file attachments carrying image bytes, tool results and conversation history when a model changes.

```text
model settings → effective turn model → MCP request context → original PDF text or text and page images
                         └→ request projection over current and historical messages → model provider
```

The Agent sends `model_supports_image` in the MCP call's `com.zcode/request-context` metadata independently of model-supplied tool arguments. An original-page read only renders images and issues visual evidence receipts when this capability is explicitly true. Otherwise it extracts the original page's layout text and citations; image-only findings remain pending for visual review. The desktop PDF preview stays local. Saving model settings takes effect on subsequent requests, including in an existing conversation.

Acceptance toggles the same model in the desktop, inspects the loopback provider's actual incoming messages for attachments and retained PDF reads in both modes, and rechecks a conversation containing earlier images after switching vision off. The sender must preserve ordinary text and citations while removing image parts and their encoded payloads in text mode.

## Import and model-assisted filing

The native Knowledge base accepts a new PDF from the file picker and starts a normal workspace Agent conversation with the current model and ordinary tool permissions. A user can also ask for the same operation in an existing conversation. Both entries use the same tools and installed instructions. Import resolves the user-selected file in the desktop/Agent namespace and passes a private snapshot to the native runner. The runner indexes every page, retains the exact PDF and bookmarks, and reuses an existing source for identical bytes even under another filename. Different bytes imported interactively get a different identity. Large imports return a trackable receipt. Interrupted imports can be retried.

```text
file selection or chat request → workspace Agent → native import → original + page index
workspace model ← next page batch → cited topics → runner checkpoint
later task → search raw text and model topics → read cited page → original PDF if needed
```

The runner divides a source into bounded page batches and provides the model with labeled excerpts. The model reads more pages, or their original images, as needed. It writes short topic summaries, search aliases, and PDF citations. A text citation carries an excerpt checked against its source page. Visual citations are marked as original-page observations. Missing evidence can be recorded for later original-page review. Derived annotations are labeled in retrieval. Per-batch commits are atomic, pinned to the source digest, and survive Agent or app restarts. Failed or unsubmitted batches remain pending. An indexed-only manual can enter this workflow later. Model filing uses the configured workspace model; local browsing, original-page reading and index-only import remain available independently.

Acceptance uses an unrelated PDF, duplicate content under a different name, different content under the same name, interrupted and concurrent filing, invalid citations, Chinese aliases, persisted batch progress and an index miss followed by a cited original-page read. Native desktop acceptance starts the first model turn from the file picker and checks the resulting entry in the library.

The picker stages and indexes the file before launching the model turn. Its copy and the chat import tool use the same staging function and native receipt. If the model is unavailable, the indexed source can already be opened and its filing can be resumed later. The first model turn from the picker needs only the source ID and digest.

Knowledge filing has its own typed local Host channel for starting an import, following its receipt and browsing its guide. The public verification read methods remain compatible. Both channels share the native socket and the same persisted source identity.
