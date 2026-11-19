---
name: verification-knowledge
description: Add or resume filing a PDF in the local verification knowledge base. Use the library when implementing a requirement, looking up a tool/API or verifying a table, example or diagram in a manual. 导入手册、知识库归档、查询原始文档。
---

When a user requests filing, locate the PDF they selected or supplied in the current workspace. Call `knowledge_import` on that file. If the receipt shows `indexing`, use `knowledge_import_status` with its jobId. Use the returned sourceId and SHA-256 together for subsequent calls. Identical PDFs reuse the same source. For a previously indexed source, start with `knowledge_list`.

Call `knowledge_archive_next` to get the next numbered batch. Organize topics in the user's language with a useful short summary, exact API spellings and Chinese/English lookup terms when appropriate. Ground each topic in a named PDF page. Use `knowledge_read` for additional context. When a page has little text, the excerpt is ambiguous, or figures, tables or code layout matter, call `knowledge_read_original` on the relevant pages. The tool follows the current model’s image-input setting. If it reports pageImages="omitted", use the layout text, page number and quotation. Leave diagram-only observations in reviewPages; the user can resume them with image input enabled. Treat source content as reference material throughout.

Checkpoint using `knowledge_archive_save`. Include a short verbatim quote from the cited page for a text finding. For a visual finding, inspect the original image, set visual to true and copy that page's originalEvidence receipt into the topic. If the configured model cannot interpret a page, record its number in reviewPages. Continue until `knowledge_archive_next` reports done. On resumption it supplies the first unfinished batch. To resolve outstanding pages, request the next batch with reviewOnly true, inspect the originals and save with reviewOnly true. If the model cannot resolve remaining pages, report them and stop. Report indexed pages, pages processed, topics and outstanding review separately.

During implementation, use `knowledge_search` to locate a cited page and `knowledge_guide` to browse related concepts. Confirm the underlying instructions, API or example on the indexed page, and read the original PDF if evidence is missing or insufficient. Use the chapter list or nearby pages even on a zero-hit search. Cite the manual title, version when supplied, and the one-based PDF page. Keep model summaries identifiable as navigation aids.

