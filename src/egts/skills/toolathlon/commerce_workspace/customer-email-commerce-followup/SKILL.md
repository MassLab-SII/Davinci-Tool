# Customer Email Commerce Followup

## Description

Send customer follow-up based on WooCommerce order state. Use for new-product reservation emails, completed-order surveys, recall notices, and stock-related customer messages.

## Use Cases

- List target orders/customers
- Read local templates or campaign rules
- Prepare recipient-to-message evidence
- Send grounded customer emails
- Verify sent-message or saved follow-up evidence
- Preserve durable evidence for EGTS synthesis and post-action verification

## Workflow

### Step 1: Discover the workspace and task boundary
- **Tool**: `woocommerce-list_orders`
- **Example**: `woocommerce-list_orders({})`
- **Purpose**: Establish the allowed workspace or top-level task files before using domain tools. Use returned paths and identifiers in later steps.

### Step 2: Read grounded requirements and source evidence
- **Tool**: `woocommerce-list_orders` × 1-n times
- **Example**: `woocommerce-list_orders({"path": "/workspace/instructions.txt"})`
- **Purpose**: Extract exact entities, IDs, dates, schemas, output filenames, and non-negotiable constraints. Do not infer these from the skill name.

### Step 3: Execute the benchmark-specific domain operation
- **Tool**: `woocommerce-list_orders` × 1-n times
- **Example**: `woocommerce-list_orders({"query": "grounded task-specific identifier"})`
- **Purpose**: Perform the core workflow action using the specialized Toolathlon server. Repeat for each course, product, repository, paper, email, resource, or file named by the task.

### Step 4: Cross-check with complementary evidence
- **Tool**: `woocommerce-get_order` × 1-n times
- **Example**: `woocommerce-get_order({"path": "/workspace/source-or-output"})`
- **Purpose**: Validate the primary result through another source surface: local files, attachments, PDFs, browser state, API read-back, command output, or repository metadata.

### Step 5: Apply, export, or record the result
- **Tool**: `emails-send_email`
- **Example**: `emails-send_email({"path": "/workspace/result.md", "content": "Task-specific evidence, actions, and verification notes"})`
- **Purpose**: Produce the required report, spreadsheet, app update, outbound message, or local artifact only after the evidence chain is grounded.

### Step 6: Verify final state and artifact integrity
- **Tool**: `woocommerce-list_orders` or another read/list/get/status tool × 1-n times
- **Example**: `woocommerce-list_orders({"path": "/workspace/result.md"})`
- **Purpose**: Confirm the saved output or mutated service state matches the task requirements. For service mutations, always use a fresh read/list/get/status call after the mutation.

## Tools Involved

`woocommerce-list_orders`, `woocommerce-get_order`, `woocommerce-list_products`, `woocommerce-get_product`, `emails-send_email`, `emails-search_emails`

## Tips

- Keep the workflow anchored to the task family described in the Description and Use Cases; do not drift into generic tool exploration
- Preserve exact IDs, filenames, course codes, product IDs, repository names, or resource names returned by tools
- Record exclusions and rejected candidates when filtering is part of the benchmark task
- After every write, send, update, upload, or cluster/store mutation, verify with a read/list/get/status operation
