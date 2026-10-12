# Contact Lookup and Verification

## Description

Search and retrieve contact information from the address book. Look up contacts by name, phone number, or relationship. Cross-reference contacts with message history to verify communication records. Audit contact details for correctness and completeness without making any modifications.

## Use Cases

- Find a contact's phone number before sending a message or making a call
- Verify whether a specific person exists in the contact list
- List all contacts matching a relationship category (e.g., all colleagues)
- Check if a phone number is already associated with a contact
- Cross-reference contacts with message history to see past communication

## Workflow

### Step 1: List all contacts
- **Tool**: `search_contacts`
- **Example**: `search_contacts({})`
- **Purpose**: Get the complete contact list to understand what's available. Returns all contacts with person_id, name, phone_number, and relationship.

### Step 2: Search by name
- **Tool**: `search_contacts`
- **Example**: `search_contacts({"query": "Johnson"})`
- **Purpose**: Find contacts whose name matches the search query. The query matches substrings in the name field.

### Step 3: Search by phone number
- **Tool**: `search_contacts`
- **Example**: `search_contacts({"query": "+1-555-0101"})`
- **Purpose**: Verify if a phone number is already registered, or find the contact associated with a specific number.

### Step 4: Cross-reference with messages
- **Tool**: `search_messages`
- **Example**: `search_messages({"phone_number": "+1-555-0101"})`
- **Purpose**: Check whether you have previously communicated with a contact by searching messages sent to their phone number.

### Step 5: Search messages by content
- **Tool**: `search_messages`
- **Example**: `search_messages({"query": "meeting"})`
- **Purpose**: Search across all messages for specific keywords to find relevant communication threads.

### Step 6: Compile verification report
- **Tool**: `search_contacts`
- **Example**: `search_contacts({})`
- **Purpose**: Final cross-check — confirm all findings are consistent and report the complete picture. Count contacts, list relationships, note any anomalies.

## Tools Involved

`search_contacts`, `search_messages`

## Tips

- `search_contacts({})` with an empty object returns all contacts — use this for a full audit
- The `query` parameter matches substrings in both name and phone_number fields
- When cross-referencing, search messages by phone_number first, then by content query for deeper investigation
- Contact lookups are read-only — state hash will not change after these operations
- If a contact is not found by name, try searching by partial name or phone number before concluding they don't exist
