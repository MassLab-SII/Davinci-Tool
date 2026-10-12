# Knowledge Document Search And QA

## Description

Answer information needs using API-Bank's local search, wiki, document QA, historical lookup, and calculator tools. This skill is primarily retrieval-oriented but can feed later planning actions.

## Use Cases

- Search local documents for a topic
- Ask a question about a document URL
- Look up wiki information or historical facts
- Calculate a final numerical answer based on retrieved evidence
- Use ToolSearcher to select an information API

## Workflow

### Step 1: Search for relevant information APIs
- **Tool**: `ToolSearcher`
- **Example**: `ToolSearcher({"keywords": "search wiki document question answering history calculator"})`
- **Purpose**: Select the most relevant retrieval tool for the user's information need.

### Step 2: Run local search
- **Tool**: `SearchEngine` × 1-n times
- **Example**: `SearchEngine({"keyword": "artificial intelligence"})`
- **Purpose**: Retrieve local search result titles, URLs, and abstracts.

### Step 3: Query wiki or history
- **Tool**: `Wiki` or `QueryHistoryToday` × 1-n times
- **Examples**:
  - `Wiki({"keyword": "Alan Turing"})`
  - `QueryHistoryToday({"date": "03-31"})`
- **Purpose**: Gather factual context from structured local databases.

### Step 4: Ask document questions
- **Tool**: `DocumentQA` × 1-n times
- **Example**: `DocumentQA({"url": "https://example.com/document", "question": "What is the main conclusion?"})`
- **Purpose**: Extract answer-like evidence from document QA data.

### Step 5: Compute derived answer
- **Tool**: `Calculator` × 1-n times
- **Example**: `Calculator({"formula": "42 * 3"})`
- **Purpose**: Calculate totals, differences, or ratios after retrieving evidence.

### Step 6: Cross-check with another retrieval API
- **Tool**: `SearchEngine`, `Wiki`, or `DocumentQA` × 1-n times
- **Example**: `SearchEngine({"keyword": "Alan Turing computer science"})`
- **Purpose**: Strengthen retrieval trajectories by using multiple evidence sources.

## Tools Involved

`ToolSearcher`, `SearchEngine`, `Wiki`, `DocumentQA`, `QueryHistoryToday`, `Calculator`

## Tips

- Retrieval-only trajectories are useful, but they should include clear evidence from tool outputs.
- Use `Calculator` only when the retrieved evidence requires arithmetic.
- Prefer multiple search/query calls when the first result is ambiguous or incomplete.
