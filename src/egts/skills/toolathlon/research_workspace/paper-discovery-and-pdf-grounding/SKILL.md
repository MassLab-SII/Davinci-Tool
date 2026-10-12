# Paper Discovery And PDF Grounding

## Description

Find papers, download or inspect PDFs, and ground answers in paper text. Use for arXiv lookup, AI-conference paper reports, and paper/profile update tasks.

## Use Cases

- Read target topic, date, venue, or title constraints
- Search arXiv/scholarly sources with exact terms
- Download or inspect candidate PDFs
- Extract title/author/venue/result evidence from pages
- Write a grounded paper note and verify it
- Preserve durable evidence for EGTS synthesis and post-action verification

## Workflow

### Step 1: Discover the workspace and task boundary
- **Tool**: `filesystem-list_allowed_directories`
- **Example**: `filesystem-list_allowed_directories({})`
- **Purpose**: Establish the allowed workspace or top-level task files before using domain tools. Use returned paths and identifiers in later steps.

### Step 2: Read grounded requirements and source evidence
- **Tool**: `filesystem-read_file` × 1-n times
- **Example**: `filesystem-read_file({"path": "/workspace/instructions.txt"})`
- **Purpose**: Extract exact entities, IDs, dates, schemas, output filenames, and non-negotiable constraints. Do not infer these from the skill name.

### Step 3: Execute the benchmark-specific domain operation
- **Tool**: `arxiv_local-search_papers` × 1-n times
- **Example**: `arxiv_local-search_papers({"query": "grounded task-specific identifier"})`
- **Purpose**: Perform the core workflow action using the specialized Toolathlon server. Repeat for each course, product, repository, paper, email, resource, or file named by the task.

### Step 4: Cross-check with complementary evidence
- **Tool**: `pdf-tools-read_pdf_pages` × 1-n times
- **Example**: `pdf-tools-read_pdf_pages({"path": "/workspace/source-or-output"})`
- **Purpose**: Validate the primary result through another source surface: local files, attachments, PDFs, browser state, API read-back, command output, or repository metadata.

### Step 5: Apply, export, or record the result
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/result.md", "content": "Task-specific evidence, actions, and verification notes"})`
- **Purpose**: Produce the required report, spreadsheet, app update, outbound message, or local artifact only after the evidence chain is grounded.

### Step 6: Verify final state and artifact integrity
- **Tool**: `filesystem-read_file` or another read/list/get/status tool × 1-n times
- **Example**: `filesystem-read_file({"path": "/workspace/result.md"})`
- **Purpose**: Confirm the saved output or mutated service state matches the task requirements. For service mutations, always use a fresh read/list/get/status call after the mutation.

## Tools Involved

`filesystem-list_allowed_directories`, `filesystem-list_directory`, `filesystem-read_file`, `arxiv_local-search_papers`, `arxiv_local-download_paper`, `pdf-tools-read_pdf_pages`, `filesystem-write_file`

## Tips

- Keep the workflow anchored to the task family described in the Description and Use Cases; do not drift into generic tool exploration
- Preserve exact IDs, filenames, course codes, product IDs, repository names, or resource names returned by tools
- Record exclusions and rejected candidates when filtering is part of the benchmark task
- After every write, send, update, upload, or cluster/store mutation, verify with a read/list/get/status operation
