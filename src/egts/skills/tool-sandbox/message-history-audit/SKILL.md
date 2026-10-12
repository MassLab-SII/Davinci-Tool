# Message History Audit

## Description

Search and audit the complete message history. Retrieve all messages sent to a specific phone number. Search across all messages by content keywords. Cross-reference messages with contacts to build a full communication picture. Identify communication patterns, verify message delivery, and audit message records for completeness.

## Use Cases

- Review all messages sent to a specific contact
- Search for messages containing specific keywords or topics
- Count how many messages have been sent to each contact
- Verify that a recently sent message is recorded in the history
- Audit message history alongside contact list for consistency

## Workflow

### Step 1: Search messages by phone number
- **Tool**: `search_messages`
- **Example**: `search_messages({"phone_number": "+1-555-0102"})`
- **Purpose**: Retrieve all messages sent to a specific phone number. Each result includes message_id, recipient_phone_number, content, and sent_timestamp.

### Step 2: Search messages by content keyword
- **Tool**: `search_messages`
- **Example**: `search_messages({"query": "meeting"})`
- **Purpose**: Find all messages containing a specific keyword regardless of recipient. Useful for topic-based audit.

### Step 3: List all messages
- **Tool**: `search_messages`
- **Example**: `search_messages({})`
- **Purpose**: Get the complete message history across all contacts. Use this for a full audit baseline.

### Step 4: Cross-reference with contacts
- **Tool**: `search_contacts`
- **Example**: `search_contacts({"query": "+1-555-0102"})`
- **Purpose**: Identify which contact a phone number belongs to. Match message history to contact names for readable audit reports.

### Step 5: Verify recent communication
- **Tool**: `search_messages`
- **Example**: `search_messages({"phone_number": "+1-555-0102"})`
- **Purpose**: Confirm that the most recent message to a contact was delivered. Check the sent_timestamp is recent and content matches.

### Step 6: Compile audit summary
- **Tool**: `search_messages`
- **Example**: `search_messages({})`
- **Purpose**: Final full scan to count messages per contact, identify most recent messages, and note any gaps or anomalies.

## Tools Involved

`search_messages`, `search_contacts`

## Tips

- `search_messages({})` with an empty object returns all messages — use this for a complete audit
- Combine phone_number filtering and content querying for precise results — search by phone first, then scan content manually
- Message `sent_timestamp` is a Unix timestamp — use `timestamp_to_datetime_info` to convert to human-readable format if needed
- Message history audits are read-only — state hash will not change
- When auditing for a specific contact, always cross-reference `search_contacts` to confirm the phone number matches the expected person
