# Mailbox Evidence Collection

## Description

Collect actionable email evidence for Toolathlon email tasks by locating the right messages, extracting sender/request/attachment facts, and saving a traceable evidence table. Use this before sending replies, processing attachments, scheduling meetings, or debugging issues reported by email.

## Use Cases

- Find application, course, meeting, or bug-report emails by sender, subject, date, or keyword
- Extract required actions, recipients, deadlines, and attachment names from message threads
- Build an evidence table before submitting materials, grading homework, or coordinating follow-up
- Verify that outbound messages are grounded in the correct source emails

## Workflow

### Step 1: Inspect the workspace for local context
- **Tool**: `filesystem-list_directory` × 1-n times
- **Example**: `filesystem-list_directory({"path": "/workspace"})`
- **Purpose**: Find local materials mentioned by email, such as PDFs, submissions, statistics files, repositories, or templates.

### Step 2: Search for candidate emails
- **Tool**: `emails-search_emails` × 1-n times
- **Example**: `emails-search_emails({"query": "PhD Application Materials Submission kaiming"})`
- **Purpose**: Locate messages by grounded sender, subject, keyword, or task-specific phrase. Repeat with narrower queries if multiple unrelated messages appear.

### Step 3: Open and extract message details
- **Tool**: `emails-get_email` × 1-n times
- **Example**: `emails-get_email({"email_id": "id from search result"})`
- **Purpose**: Read the complete body, recipients, timestamps, and attachment metadata before acting. Do not infer requirements from search snippets alone.

### Step 4: Cross-check local files or attachments
- **Tool**: `filesystem-read_file` × 1-n times
- **Example**: `filesystem-read_file({"path": "/workspace/materials/statement.txt"})`
- **Purpose**: Verify that local files named in the email exist and contain the expected content before sending, grading, or summarizing.

### Step 5: Save a mailbox evidence table
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/mailbox_evidence.md", "content": "Email | Request | Required files | Deadline | Action\n--- | --- | --- | --- | ---"})`
- **Purpose**: Preserve the email-to-action mapping so later send/update/debug steps remain grounded.

### Step 6: Verify the evidence artifact
- **Tool**: `filesystem-read_file`
- **Example**: `filesystem-read_file({"path": "/workspace/mailbox_evidence.md"})`
- **Purpose**: Confirm every required message has a corresponding action and evidence source before proceeding.

## Tools Involved

`emails-search_emails`, `emails-get_email`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`

## Tips

- Use exact subject lines when provided; email tasks often evaluate exact requested actions
- Open full messages before acting on attachment or recipient requirements
- Record message IDs or stable identifiers in the evidence table when available
- For outbound email tasks, search again after sending only if the email server exposes sent-message state
