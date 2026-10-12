# Repo Discovery And Evidence Collection

## Description

Find and evaluate repositories or code artifacts for a technical request, then save evidence explaining why each candidate is relevant. Use this for Toolathlon code-repo tasks involving unofficial implementations, dataset licenses, related repositories, or technical video-to-repo mapping.

## Use Cases

- Search GitHub for candidate repositories that implement a paper, model, dataset, or technology
- Collect license, README, issue, or release evidence before answering a repository question
- Compare multiple candidate repos and choose the best-supported one
- Save a repo recommendation or evidence report in the workspace

## Workflow

### Step 1: Discover local inputs
- **Tool**: `filesystem-list_allowed_directories`, then `filesystem-list_directory`
- **Examples**:
  - `filesystem-list_allowed_directories({})`
  - `filesystem-list_directory({"path": "/workspace"})`
- **Purpose**: Locate papers, notes, existing repositories, dataset manifests, or required output files.

### Step 2: Read the technical request and seed evidence
- **Tool**: `filesystem-read_file` × 1-n times
- **Example**: `filesystem-read_file({"path": "/workspace/paper_summary.md"})`
- **Purpose**: Extract exact model names, dataset names, paper titles, repository owners, license constraints, and evaluation criteria.

### Step 3: Search candidate repositories
- **Tool**: `github-search_repositories` × 1-n times
- **Example**: `github-search_repositories({"query": "paper title model name implementation"})`
- **Purpose**: Find candidates using grounded names from local evidence, not generic keywords alone.

### Step 4: Inspect candidate metadata and files
- **Tool**: `github-get_repository`, `github-get_file_contents`, or `fetch-fetch_markdown` × 1-n times
- **Examples**:
  - `github-get_repository({"owner": "candidate-owner", "repo": "candidate-repo"})`
  - `fetch-fetch_markdown({"url": "https://example.com/candidate-readme"})`
- **Purpose**: Check README claims, license files, stars/activity, linked papers, usage instructions, and artifact availability.

### Step 5: Cross-check with local or external evidence
- **Tool**: `filesystem-read_file` or `pdf-tools-read_pdf_pages` × 1-n times
- **Example**: `pdf-tools-read_pdf_pages({"path": "/workspace/paper.pdf", "pages": "1-2"})`
- **Purpose**: Verify that repository claims match the original paper, dataset, or task request.

### Step 6: Write a candidate comparison report
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/repo_evidence.md", "content": "Repo | Evidence | Risk | Recommendation\n--- | --- | --- | ---"})`
- **Purpose**: Save the reasoning for each candidate and the final recommendation.

### Step 7: Verify the saved recommendation
- **Tool**: `filesystem-read_file`
- **Example**: `filesystem-read_file({"path": "/workspace/repo_evidence.md"})`
- **Purpose**: Confirm that the output includes candidate URLs/names, evidence, risks, and the selected answer.

## Tools Involved

`filesystem-list_allowed_directories`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`, `github-search_repositories`, `github-get_repository`, `github-get_file_contents`, `fetch-fetch_markdown`, `pdf-tools-read_pdf_pages`

## Tips

- Prefer repositories that link back to the paper or dataset being requested
- Treat missing license, missing README, or stale activity as explicit risks in the report
- Preserve exact repository owner/name pairs for downstream reproducibility
- Do not recommend a repo solely because its name matches; inspect content evidence first
