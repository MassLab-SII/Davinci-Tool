# Postgres Transactional Workflow

## Description

Perform multi-step database changes with explicit validation before and after the mutation. This skill is for tasks where correctness depends on several related SQL operations.

## Use Cases

- Updating related rows across multiple tables.
- Inserting dependent records after checking keys.
- Correcting data while preserving relational consistency.
- Validating multi-step mutation outcomes.

## Workflow

### Step 1: Inspect affected tables
- **Tool**: `get_schema` × 1-n times and `describe_table`
- **Example**: `describe_table({"table_name": "orders"})`
- **Purpose**: Understand every table touched by the workflow.

### Step 2: Query preconditions
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM orders WHERE order_id = 1001;"})`
- **Purpose**: Confirm the target records and current state.

### Step 3: Execute the change
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "UPDATE orders SET status = 'shipped' WHERE order_id = 1001;"})`
- **Purpose**: Apply the required mutation.

### Step 4: Validate all affected data
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT status FROM orders WHERE order_id = 1001;"})`
- **Purpose**: Confirm each expected state transition.

### Step 5: Check related consistency
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT COUNT(*) FROM order_items WHERE order_id = 1001;"})`
- **Purpose**: Verify related records still match the intended workflow.

## Tools Involved

- `get_schema`
- `describe_table`
- `list_tables`
- `query`
- `execute_sql`

## Tips

- Keep changes narrow and verify every affected table.
- Use explicit keys and predicates.
- Run a precondition query before each risky mutation.
- If a task requires several updates, verify the final combined state.
