# Postgres Security Audit

## Description

Inspect and adjust roles, grants, row-level security, policies, and other security-sensitive database state with explicit verification.

## Use Cases

- Checking which roles or privileges exist.
- Auditing table grants or public access.
- Creating, altering, or dropping row-level security policies.
- Verifying that security metadata changed as intended.

## Workflow

### Step 1: Inspect security-related schema
- **Tool**: `get_schema` × 1-n times
- **Example**: `get_schema({})`
- **Purpose**: Understand which schemas and tables are relevant to the audit.

### Step 2: Query catalog privileges
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT grantee, privilege_type FROM information_schema.role_table_grants LIMIT 20;"})`
- **Purpose**: Read current grants and privilege assignments.

### Step 3: Inspect policies or roles
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM pg_policies;"})`
- **Purpose**: Ground row-level security and policy state.

### Step 4: Apply security change
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;"})`
- **Purpose**: Perform the requested privilege or policy mutation.

### Step 5: Verify catalog state
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM pg_policies WHERE tablename = 'accounts';"})`
- **Purpose**: Confirm the security change exists in database metadata.

## Tools Involved

- `get_schema`
- `list_tables`
- `describe_table`
- `query`
- `execute_sql`

## Tips

- Use PostgreSQL catalog and information_schema queries for security evidence.
- Verify security changes with metadata queries, not only command success.
- Be precise about roles, schemas, and table names.
- Avoid broad grants unless the task explicitly asks for them.
