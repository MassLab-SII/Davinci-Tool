# Postgres Security RLS Permission Consulting

## Description

Perform business database permission audits and implement row-level-security access rules for application-style schemas.

## Use Cases

- Audit database roles, grants, policies, schemas, and security-sensitive tables.
- Design RLS access rules for application-style business schemas.
- Create policies or grants and verify access boundaries.
- Report security risks with exact catalog evidence.
- Validate permission changes with before-and-after catalog queries.

## Workflow

### Step 1: Read database metadata
- **Tool**: `get_database_info`
- **Example**: `get_database_info({})`
- **Purpose**: Confirm active database, extensions, schemas, and high-level state.

### Step 2: List candidate tables
- **Tool**: `list_tables` × 1-n times
- **Example**: `list_tables({})`
- **Purpose**: Identify relevant tables before writing SQL.

### Step 3: Inspect schema structure
- **Tool**: `get_schema` × 1-n times
- **Example**: `get_schema({})`
- **Purpose**: Review columns, relations, and available schemas.

### Step 4: Describe target table
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "orders"})`
- **Purpose**: Confirm exact column names, types, indexes, and keys.

### Step 5: Sample source rows
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants LIMIT 5;"})`
- **Purpose**: Understand real values and avoid schema-name guesses.

### Step 6: Apply SQL change
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "ALTER TABLE orders ENABLE ROW LEVEL SECURITY;"})`
- **Purpose**: Create or modify the requested table, view, policy, function, index, or rows.

### Step 7: Verify final result
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT schemaname, tablename, policyname FROM pg_policies WHERE tablename = 'orders';"})`
- **Purpose**: Confirm the final report, mutation, policy, or optimization result is observable.

## Tools Involved

- `get_database_info`
- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `execute_sql`

## Tips

- Inspect existing roles and policies before creating new ones.
- Security changes should include both catalog verification and data visibility checks.
- Use least-privilege grants unless the task explicitly asks otherwise.
- Document which role can see or modify which rows after RLS changes.
