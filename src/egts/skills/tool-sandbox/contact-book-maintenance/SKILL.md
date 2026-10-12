# Contact Book Maintenance

## Description

Manage the full lifecycle of contacts in the address book. Add new contacts with name, phone number, and relationship. Search for existing contacts to find their person_id. Modify contact fields (name, phone, relationship) using the person_id. Remove contacts by person_id, and verify the final state after each operation.

## Use Cases

- Add a new contact and verify it appears in search results
- Update a contact's phone number or relationship after a life event
- Remove outdated or duplicate contacts
- Verify contact information before sending messages
- Audit the contact list for completeness and accuracy

## Workflow

### Step 1: Survey existing contacts
- **Tool**: `search_contacts`
- **Example**: `search_contacts({})`
- **Purpose**: Get the baseline list of all contacts with their person_id, name, phone_number, and relationship fields.

### Step 2: Search for a specific contact
- **Tool**: `search_contacts`
- **Example**: `search_contacts({"query": "Alice"})`
- **Purpose**: Find a contact by name to get their person_id for subsequent modify or remove operations.

### Step 3: Add a new contact
- **Tool**: `add_contact`
- **Example**: `add_contact({"name": "Grace Hopper", "phone_number": "+1-555-0200", "relationship": "colleague"})`
- **Purpose**: Create a new contact entry. Returns the new contact with a unique person_id. Record this person_id for later steps.

### Step 4: Verify the addition
- **Tool**: `search_contacts`
- **Example**: `search_contacts({"query": "Grace"})`
- **Purpose**: Confirm the new contact is now in the address book and all fields are correct.

### Step 5: Modify an existing contact
- **Tool**: `modify_contact`
- **Example**: `modify_contact({"person_id": "<id>", "phone_number": "+1-555-0199"})`
- **Purpose**: Update specific fields of a contact. At least one of `name`, `phone_number`, or `relationship` must be provided.

### Step 6: Verify the modification
- **Tool**: `search_contacts`
- **Example**: `search_contacts({"query": "Alice"})`
- **Purpose**: Confirm the contact's fields were updated correctly.

### Step 7: Remove a contact
- **Tool**: `remove_contact`
- **Example**: `remove_contact({"person_id": "<id>"})`
- **Purpose**: Delete a contact from the address book permanently by their person_id.

### Step 8: Final verification
- **Tool**: `search_contacts`
- **Example**: `search_contacts({})`
- **Purpose**: Confirm the removed contact is gone and the remaining contacts are correct. Validate counts and specific entries.

## Tools Involved

`search_contacts`, `add_contact`, `modify_contact`, `remove_contact`

## Tips

- Always record the `person_id` returned by `add_contact` — you will need it for `modify_contact` and `remove_contact`
- `search_contacts` returns the full contact list when called with an empty object `{}`; use a `query` string to filter by name or phone number
- When modifying a contact, you only need to provide the fields that should change — unchanged fields can be omitted
- Verify after every mutation (add, modify, remove), not just at the end
- `remove_contact` is irreversible — double-check the person_id before calling it
