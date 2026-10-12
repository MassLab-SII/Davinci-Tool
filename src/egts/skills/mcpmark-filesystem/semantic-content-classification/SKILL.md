# Semantic Content Classification

## Description

Intelligently classify and organize files based on semantic understanding of their content. Analyze document topics, identify thematic patterns, categorize by subject matter (e.g., math papers, legal disputes, research domains), and organize files into meaningful groups beyond simple metadata.

## Use Cases

- Find papers analyzing specific topics (e.g., model knowledge, generalization, memorization)
- Classify research papers by domain (machine learning, computer vision, NLP)
- Identify legal documents by dispute type or clause category
- Organize documents by semantic similarity or thematic relevance

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand the document collection layout. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Survey document collection
- **Tool**: `directory_tree` or `search_files`
- **Examples**:
  - `directory_tree({"path": "/workspace/documents"})`
  - `search_files({"path": "/workspace", "pattern": "*.html"})`
  - `search_files({"path": "/workspace", "pattern": "*.txt"})`
- **Purpose**: Understand the scope of documents — how many files, what formats, and where they are located. Both `path` and `pattern` must be **strings**.

### Step 4: Read sample files to understand content format
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/documents/paper_001.html"})`
  - `read_text_file({"path": "/workspace/documents/paper_002.html"})`
  - `read_text_file({"path": "/workspace/documents/agreement_v5.txt"})`
- **Purpose**: Read representative files to understand content format, identify semantic fields (titles, abstracts, keywords, clause text), and plan the classification strategy. The `path` parameter must be a **string**.

### Step 5: Batch-read and extract semantic content
- **Tool**: `read_multiple_files` × 1-n times
- **Examples**:
  - `read_multiple_files({"paths": ["/workspace/documents/paper_001.html", "/workspace/documents/paper_002.html", "/workspace/documents/paper_003.html"]})`
  - `read_multiple_files({"paths": ["/workspace/documents/paper_004.html", "/workspace/documents/paper_005.html", "/workspace/documents/paper_006.html"]})`
- **Purpose**: Batch-read documents to extract semantic signals — titles, abstracts, keywords, subject headings, clause content. Classify each document based on its topic, theme, or domain. The `paths` parameter must be an **array of strings**.

### Step 6: Identify target documents by semantic criteria
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/documents/paper_042.html"})`
  - `read_text_file({"path": "/workspace/documents/paper_077.html"})`
- **Purpose**: Deep-read candidate documents that match the semantic criteria (e.g., papers discussing "knowledge" and "memorization") to confirm they meet the classification requirement.

### Step 7: Create classification directory structure
- **Tool**: `create_directory` × 1-n times
- **Examples**:
  - `create_directory({"path": "/workspace/classified/machine_learning"})`
  - `create_directory({"path": "/workspace/classified/computer_vision"})`
  - `create_directory({"path": "/workspace/classified/natural_language_processing"})`
- **Purpose**: Create directories representing semantic categories for organizing documents.

### Step 8: Organize files by classification
- **Tool**: `move_file` × 1-n times
- **Examples**:
  - `move_file({"source": "/workspace/documents/paper_042.html", "destination": "/workspace/classified/machine_learning/paper_042.html"})`
  - `move_file({"source": "/workspace/documents/paper_077.html", "destination": "/workspace/classified/computer_vision/paper_077.html"})`
- **Purpose**: Move or copy documents into their classified directories. Both `source` and `destination` must be **strings**.

### Step 9: Generate classification output
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - `write_file({"path": "/workspace/answer.html", "content": ""})`
  - `write_file({"path": "/workspace/classified/classification_report.txt", "content": "machine_learning: 23 papers\ncomputer_vision: 15 papers\nnatural_language_processing: 18 papers"})`
  - `write_file({"path": "/workspace/classified/INDEX.md", "content": "# Document Classification\n\n| Category | Count | Description |\n|----------|-------|-------------|\n| ML | 23 | Machine learning theory and applications |"})`
- **Purpose**: Write classification results — rename target files, generate category reports, or produce index documents summarizing the classification.

### Step 10: Verify classification
- **Tool**: `list_directory` or `read_text_file`
- **Examples**:
  - `list_directory({"path": "/workspace/classified/machine_learning"})`
  - `read_text_file({"path": "/workspace/answer.html"})`
- **Purpose**: Confirm that files are correctly classified and output files contain the expected content.

## Tools Involved

`list_allowed_directories`, `list_directory`, `directory_tree`, `search_files`, `read_multiple_files`, `read_text_file`, `create_directory`, `move_file`, `write_file`

## Tips

- When classifying by topic, extract titles and abstracts first — they carry the strongest semantic signals
- For HTML files, look for `<title>`, `<meta name="description">`, and heading tags (`<h1>`, `<h2>`) as primary content indicators
- Process files in batches of 3-5 with `read_multiple_files` and classify each batch before moving to the next
- When searching for a specific topic (e.g., "math paper about memorization"), scan all files systematically rather than guessing — the target may not have an obvious filename
- For large collections (50+ files), plan a multi-pass strategy: first pass to extract metadata, second pass to deep-read candidates
- When the task asks to "find" a specific document, read enough of each candidate to make a confident semantic match before committing to an answer
- All path parameters must be **strings**, `paths` must be an **array of strings**, and numeric parameters must be **numbers** (integers)
