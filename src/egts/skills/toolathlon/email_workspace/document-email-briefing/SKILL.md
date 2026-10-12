# Document Email Briefing

## Description

Create a briefing from email requests and local documents by connecting each requested action to attachments, PDFs, spreadsheets, or workspace files. Use this for Toolathlon email tasks that require summarizing materials before replying, grading, submitting, or coordinating.

## Use Cases

- Summarize application or onboarding material requested by email
- Combine emailed homework submissions with local course statistics before reporting or grading
- Read PDFs or spreadsheets attached to messages and prepare a grounded action brief
- Produce a concise briefing for a later outbound email or saved report

## Workflow

### Step 1: Search for the driving email thread
- **Tool**: `emails-search_emails` × 1-n times
- **Example**: `emails-search_emails({"query": "final presentation assignments NLP"})`
- **Purpose**: Find the thread that defines the task, expected output, recipients, or attachments.

### Step 2: Read the complete email and attachment metadata
- **Tool**: `emails-get_email` × 1-n times
- **Example**: `emails-get_email({"email_id": "id from search result"})`
- **Purpose**: Extract sender, subject, requested action, deadline, recipient list, and attachment names.

### Step 3: Inspect related workspace documents
- **Tool**: `filesystem-read_file` or `pdf-tools-read_pdf_pages` × 1-n times
- **Examples**:
  - `filesystem-read_file({"path": "/workspace/checklist.txt"})`
  - `pdf-tools-read_pdf_pages({"path": "/workspace/resume.pdf", "pages": "1-2"})`
- **Purpose**: Read local documents referenced by the email, such as resumes, applications, manuals, or instructions.

### Step 4: Read tabular context if present
- **Tool**: `excel-read_data_from_excel` × 1-n times
- **Example**: `excel-read_data_from_excel({"path": "/workspace/nlp_statistics.xlsx"})`
- **Purpose**: Incorporate spreadsheet evidence such as student statistics, rosters, grades, or material inventories.

### Step 5: Write an action-oriented briefing
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/email_briefing.md", "content": "## Request\n...\n## Evidence\n...\n## Recommended action\n..."})`
- **Purpose**: Save a briefing that separates the request, evidence, missing items, and next action.

### Step 6: Verify the briefing covers all requested items
- **Tool**: `filesystem-read_file`
- **Example**: `filesystem-read_file({"path": "/workspace/email_briefing.md"})`
- **Purpose**: Confirm that each email request and relevant document source appears before using the briefing for outbound communication.

## Tools Involved

`emails-search_emails`, `emails-get_email`, `pdf-tools-read_pdf_pages`, `excel-read_data_from_excel`, `filesystem-read_file`, `filesystem-write_file`

## Tips

- Preserve exact recipient names, subjects, and requested filenames when the email specifies them
- Do not summarize attachments you have not opened through the appropriate file/PDF/spreadsheet tool
- If documents conflict with email instructions, record the conflict in the briefing
- Use the briefing as the evidence base for any later `emails-send_email` call
