# Source Quality Audit

## Description

Audit whether a research or web claim is supported by primary, current, and mutually consistent sources. Use this for Toolathlon research tasks where answers must be justified by papers, official pages, PDFs, or local workspace evidence.

## Use Cases

- Check whether a claimed paper, dataset, author affiliation, or project link is supported by primary sources
- Compare conference/homepage/BibTeX metadata before updating a bibliography or profile
- Identify stale, secondary, or conflicting evidence in a research answer
- Write an uncertainty-aware audit note before producing a final report

## Workflow

### Step 1: Discover and inspect workspace evidence
- **Tool**: `filesystem-list_allowed_directories`, then `filesystem-list_directory`
- **Examples**:
  - `filesystem-list_allowed_directories({})`
  - `filesystem-list_directory({"path": "/workspace"})`
- **Purpose**: Locate local papers, notes, target `.bib` files, profile pages, or required output templates.

### Step 2: Read the claims to audit
- **Tool**: `filesystem-read_file` × 1-n times
- **Example**: `filesystem-read_file({"path": "/workspace/claims.md"})`
- **Purpose**: Extract each claim as an auditable unit: title, author, date, venue, affiliation, dataset, result, or URL.

### Step 3: Check primary web or official source
- **Tool**: `fetch-fetch_markdown` × 1-n times
- **Example**: `fetch-fetch_markdown({"url": "https://example.com/official-source"})`
- **Purpose**: Verify claims against official pages, conference pages, project repositories, or publisher pages when available.

### Step 4: Check scholarly metadata
- **Tool**: `scholarly-search-google-scholar` or `scholarly-search-arxiv` × 1-n times
- **Examples**:
  - `scholarly-search-google-scholar({"query": "exact paper title authors"})`
  - `scholarly-search-arxiv({"query": "exact paper title"})`
- **Purpose**: Cross-check title, authors, publication venue, date, and versions using academic search surfaces.

### Step 5: Inspect local or downloaded source text
- **Tool**: `pdf-tools-read_pdf_pages` or `filesystem-read_file` × 1-n times
- **Examples**:
  - `pdf-tools-read_pdf_pages({"path": "/workspace/paper.pdf", "pages": "1-2"})`
  - `filesystem-read_file({"path": "/workspace/ref.bib"})`
- **Purpose**: Confirm details that only appear inside the paper, bibliography, local profile, or source document.

### Step 6: Write claim-level audit results
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/source_quality_audit.md", "content": "Claim | Primary evidence | Cross-check | Status | Notes\n--- | --- | --- | --- | ---"})`
- **Purpose**: Save an explicit support/contradiction/uncertainty table instead of a vague summary.

### Step 7: Verify the audit artifact
- **Tool**: `filesystem-read_file`
- **Example**: `filesystem-read_file({"path": "/workspace/source_quality_audit.md"})`
- **Purpose**: Confirm each important claim has evidence, status, and uncertainty notes.

## Tools Involved

`filesystem-list_allowed_directories`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`, `fetch-fetch_markdown`, `scholarly-search-google-scholar`, `scholarly-search-arxiv`, `pdf-tools-read_pdf_pages`

## Tips

- Mark a source as secondary unless it is an official paper page, project page, publisher/conference page, or the paper itself
- Use exact titles or unique identifiers when searching scholarly tools
- If sources conflict, preserve both pieces of evidence and label the conflict instead of choosing silently
- For bibliography updates, verify format consistency against the existing `.bib` file before writing
