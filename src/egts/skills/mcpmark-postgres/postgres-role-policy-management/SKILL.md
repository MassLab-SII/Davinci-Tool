# Postgres Role and Policy Management

## Description

Manage roles, grants, row-level security policies, and privilege checks with before-and-after verification.

## Use Cases

- Creating or modifying roles.
- Granting or revoking table privileges.
- Enabling row-level security or changing policies.
- Checking whether a role can access a table or operation.

## Workflow

### Step 1: Read existing roles and grants
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT rolname FROM pg_roles ORDER BY rolname;"})`
- **Purpose**: Understand current role state before mutation.

### Step 2: Inspect target table metadata
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "accounts"})`
- **Purpose**: Confirm the table exists and identify security-relevant columns.

### Step 3: Apply role or policy SQL
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "GRANT SELECT ON accounts TO analyst;"})`
- **Purpose**: Perform the requested access-control change.

### Step 4: Verify privileges
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_name = 'accounts';"})`
- **Purpose**: Confirm grants or revocations are reflected in metadata.

### Step 5: Verify policies
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT policyname, cmd, roles FROM pg_policies WHERE tablename = 'accounts';"})`
- **Purpose**: Confirm row-level security policy state.

## Tools Involved

- `query`
- `execute_sql`
- `list_tables`
- `get_schema`
- `describe_table`

## Tips

- Distinguish role creation, grants, and row-level policies.
- Verify changes through catalog views after execution.
- Avoid granting broad privileges unless explicitly requested.
- Use schema-qualified names when ambiguity is possible.
