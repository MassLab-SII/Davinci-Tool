# Postgres Data Mutation

## Description

Make grounded SQL changes with before-and-after validation. This skill covers table updates, inserts, deletes, simple DDL, and verification queries.

## Use Cases

- Updating a record requested by a task.
- Inserting or correcting rows in benchmark tables.
- Creating or altering simple database objects.
- Verifying mutation effects through follow-up SQL.

## Workflow

### Step 1: Identify target table and columns
- **Tool**: `list_tables` × 1-n times and `describe_table`
- **Example**: `describe_table({"table_name": "customers"})`
- **Purpose**: Confirm the exact table and field names before writing SQL.

### Step 2: Read current state
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM customers WHERE customer_id = 42;"})`
- **Purpose**: Capture the pre-mutation state and verify the target row exists.

### Step 3: Apply the mutation
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "UPDATE customers SET status = 'active' WHERE customer_id = 42;"})`
- **Purpose**: Perform the requested database change.

### Step 4: Verify the result
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT status FROM customers WHERE customer_id = 42;"})`
- **Purpose**: Confirm the mutation changed the intended row or object.

### Step 5: Inspect schema after DDL
- **Tool**: `get_schema` × 1-n times
- **Example**: `get_schema({})`
- **Purpose**: Verify schema-level changes such as new columns, views, or indexes.

## Tools Involved

- `list_tables`
- `describe_table`
- `query`
- `execute_sql`
- `get_schema`

## Tips

- Always query the target state before and after mutation.
- Use precise `WHERE` clauses for row-level changes.
- Prefer small, task-specific SQL changes.
- For DDL, validate with schema inspection as well as a query.
