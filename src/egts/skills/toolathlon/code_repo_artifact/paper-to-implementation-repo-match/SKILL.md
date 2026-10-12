# Paper To Implementation Repo Match

## Description

Match a research paper to a likely implementation repository by comparing paper details, repository claims, code structure, and artifact quality. Use this for Toolathlon code-repo tasks where the official implementation is missing or candidates must be ranked.

## Use Cases

- Find an unofficial implementation for a paper in the workspace
- Verify whether a repository actually implements the target method rather than a similarly named project
- Compare candidate repos by paper linkage, code completeness, dependencies, and reproducibility signals
- Write a recommendation for which repository to use and why

## Workflow

### Step 1: Locate and read the target paper or summary
- **Tool**: `filesystem-list_allowed_directories`, `filesystem-list_directory`, `filesystem-read_file` × 1-n times
- **Examples**:
  - `filesystem-list_allowed_directories({})`
  - `filesystem-read_file({"path": "/workspace/paper_notes.md"})`
- **Purpose**: Extract exact title, authors, method name, datasets, benchmark names, and any official-code statement.

### Step 2: Inspect paper text when available
- **Tool**: `pdf-tools-read_pdf_pages` × 1-n times
- **Example**: `pdf-tools-read_pdf_pages({"path": "/workspace/paper.pdf", "pages": "1-3"})`
- **Purpose**: Ground the search in abstract, method names, experiment names, and repository references from the paper itself.

### Step 3: Search GitHub for implementation candidates
- **Tool**: `github-search_repositories` × 1-n times
- **Example**: `github-search_repositories({"query": "exact paper title method name"})`
- **Purpose**: Find candidate repositories using exact paper and method terms, then broaden only if needed.

### Step 4: Inspect repository evidence
- **Tool**: `github-get_repository`, `github-get_file_contents`, or `fetch-fetch_markdown` × 1-n times
- **Examples**:
  - `github-get_repository({"owner": "candidate-owner", "repo": "candidate-repo"})`
  - `github-get_file_contents({"owner": "candidate-owner", "repo": "candidate-repo", "path": "README.md"})`
- **Purpose**: Check whether README, citations, configs, model files, training scripts, and dependencies match the paper.

### Step 5: Score candidates against paper requirements
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/implementation_match.md", "content": "Candidate | Paper linkage | Code completeness | Reproducibility | Verdict\n--- | --- | --- | --- | ---"})`
- **Purpose**: Save a structured comparison instead of a single ungrounded repo link.

### Step 6: Verify the recommendation artifact
- **Tool**: `filesystem-read_file`
- **Example**: `filesystem-read_file({"path": "/workspace/implementation_match.md"})`
- **Purpose**: Confirm the chosen repo, rejected alternatives, and evidence are present.

## Tools Involved

`filesystem-list_allowed_directories`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`, `github-search_repositories`, `github-get_repository`, `github-get_file_contents`, `fetch-fetch_markdown`, `pdf-tools-read_pdf_pages`

## Tips

- Use exact paper title and distinctive method names before generic keywords
- Verify repository content, not only repository search ranking
- Record rejected candidates when they are plausible but incomplete or unrelated
- Prefer candidates with explicit citation, runnable instructions, datasets/configs, and recent maintenance
