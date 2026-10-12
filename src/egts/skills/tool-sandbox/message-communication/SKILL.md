# Message Communication

## Description

Send messages to contacts via phone number with full prerequisite checking. Before sending, verify that cellular service is enabled. If cellular is off, turn it on first. Look up recipient phone numbers from contacts if needed. After sending, verify the message appears in the sent message history.

## Use Cases

- Send a message to a known contact and confirm delivery
- Handle the cellular-off error: detect, enable cellular, and retry
- Look up a contact's phone number, then send them a message
- Send messages to multiple contacts in sequence
- Verify sent messages appear in message history search

## Workflow

### Step 1: Check cellular service status
- **Tool**: `get_cellular_service_status`
- **Example**: `get_cellular_service_status({})`
- **Purpose**: Determine whether cellular service is currently enabled. Messages cannot be sent if cellular is off.

### Step 2: Enable cellular if needed
- **Tool**: `set_cellular_service_status`
- **Example**: `set_cellular_service_status({"status": "on"})`
- **Purpose**: Turn on cellular service if it was off. Skip this step if cellular is already on.

### Step 3: Look up the recipient's phone number
- **Tool**: `search_contacts`
- **Example**: `search_contacts({"query": "Carol Williams"})`
- **Purpose**: Find the recipient's contact entry to get their exact phone_number. Record this for the send step.

### Step 4: Send the message
- **Tool**: `send_message_with_phone_number`
- **Example**: `send_message_with_phone_number({"phone_number": "+1-555-0103", "content": "Family dinner this Sunday at 6pm"})`
- **Purpose**: Send a message to the recipient. The `phone_number` must be an exact string and `content` is the message body.

### Step 5: Verify the message was sent
- **Tool**: `search_messages`
- **Example**: `search_messages({"phone_number": "+1-555-0103"})`
- **Purpose**: Confirm the sent message appears in the message history for that phone number.

### Step 6: Search for message content
- **Tool**: `search_messages`
- **Example**: `search_messages({"query": "dinner"})`
- **Purpose**: Alternatively, verify by searching message content for keywords from the sent message.

## Tools Involved

`get_cellular_service_status`, `set_cellular_service_status`, `search_contacts`, `send_message_with_phone_number`, `search_messages`

## Tips

- Always check cellular status before attempting to send — sending with cellular off will fail
- If cellular was off at the start, record that you enabled it for the final summary
- The `phone_number` parameter must exactly match the contact's stored number
- `search_messages` can filter by `phone_number` (outgoing to a specific contact) or by `query` (content keyword search)
- You can restore cellular to its original state after sending if the task requires leaving no side effects
