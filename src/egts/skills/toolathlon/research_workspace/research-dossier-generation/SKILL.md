# Research Dossier Generation

## Description

Build a benchmark-style research dossier by combining local workspace requirements with papers, PDFs, scholarly metadata, and web evidence. Use this for Toolathlon research tasks such as logical-dataset collection, paper/profile updates, and multi-source academic reports.

## Use Cases

- Collect candidate papers or datasets for a research topic and summarize evidence differences
- Build an author, paper, method, or dataset dossier from local notes plus external academic sources
- Support profile or publication updates with traceable publication metadata
- Produce a saved research note with source-by-source evidence and uncertainty

## Workflow

### Step 1: Discover allowed workspace roots
- **Tool**: `filesystem-list_allowed_directories`
- **Example**: `filesystem-list_allowed_directories({})`
- **Purpose**: Find the valid workspace root for source files, downloaded PDFs, and the final dossier.

### Step 2: Inspect the research workspace
- **Tool**: `filesystem-list_directory` × 1-n times
- **Example**: `filesystem-list_directory({"path": "/workspace"})`
- **Purpose**: Locate seed notes, target profile files, PDFs, LaTeX projects, or output templates before querying research tools.

### Step 3: Read local constraints and existing evidence
- **Tool**: `filesystem-read_file` × 1-n times
- **Example**: `filesystem-read_file({"path": "/workspace/topic_requirements.md"})`
- **Purpose**: Extract the exact research question, required fields, date limits, venue constraints, and output schema.

### Step 4: Search primary academic sources
- **Tool**: `arxiv_local-search_papers` × 1-n times
- **Example**: `arxiv_local-search_papers({"query": "agentic reasoning Alita"})`
- **Purpose**: Find candidate papers from academic metadata. Preserve title, authors, date/version, and identifier for later verification.

### Step 5: Download or inspect source documents
- **Tool**: `arxiv_local-download_paper` or `pdf-tools-read_pdf_pages` × 1-n times
- **Examples**:
  - `arxiv_local-download_paper({"paper_id": "arXiv identifier from search results"})`
  - `pdf-tools-read_pdf_pages({"path": "/workspace/paper.pdf", "pages": "1-3"})`
- **Purpose**: Ground claims in paper text, abstract, tables, or figures rather than metadata alone.

### Step 6: Cross-check with web or scholarly evidence
- **Tool**: `fetch-fetch_markdown` or `scholarly-search-google-scholar` × 1-n times
- **Examples**:
  - `fetch-fetch_markdown({"url": "https://example.com/project-or-paper-page"})`
  - `scholarly-search-google-scholar({"query": "paper title authors"})`
- **Purpose**: Verify publication venue, project links, citation context, or dataset availability through an independent source.

### Step 7: Write the dossier with traceable fields
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/research_dossier.md", "content": "## Candidate\n- Evidence from arXiv: ...\n- Evidence from PDF: ...\n- Evidence from web: ...\n- Uncertainty: ..."})`
- **Purpose**: Save a structured dossier that separates observed evidence from inferred conclusions.

### Step 8: Verify the saved dossier
- **Tool**: `filesystem-read_file`
- **Example**: `filesystem-read_file({"path": "/workspace/research_dossier.md"})`
- **Purpose**: Confirm required fields, citations, and uncertainty notes are present before finishing.

## Tools Involved

`filesystem-list_allowed_directories`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`, `arxiv_local-search_papers`, `arxiv_local-download_paper`, `pdf-tools-read_pdf_pages`, `fetch-fetch_markdown`, `scholarly-search-google-scholar`

## Tips

- Prefer primary paper text and official project pages over secondary summaries
- Record rejected candidates when task constraints are narrow; this helps synthesis explain why the final choice is correct
- Keep URLs, arXiv IDs, and file paths in the dossier so evidence remains traceable
- Do not merge uncertain metadata into final claims without labeling the uncertainty
