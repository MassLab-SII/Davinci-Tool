# Postgres View and Report Building

## Description

Create reusable views or reporting objects, inspect their output, and verify that the generated object answers the task correctly.

## Use Cases

- Creating a view for repeated reporting logic.
- Materializing a summary table when requested.
- Encapsulating joins or aggregates in a named object.
- Validating a newly created SQL object.

## Workflow

### Step 1: Inspect report sources
- **Tool**: `list_tables` × 1-n times and `get_schema`
- **Example**: `get_schema({})`
- **Purpose**: Choose the correct source tables and columns.

### Step 2: Prototype the report query
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT customer_id, COUNT(*) AS order_count FROM orders GROUP BY customer_id LIMIT 10;"})`
- **Purpose**: Validate the SQL before creating a view.

### Step 3: Create the view or object
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "CREATE OR REPLACE VIEW customer_order_counts AS SELECT customer_id, COUNT(*) AS order_count FROM orders GROUP BY customer_id;"})`
- **Purpose**: Persist the reusable report.

### Step 4: Query the created object
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM customer_order_counts ORDER BY order_count DESC LIMIT 10;"})`
- **Purpose**: Verify the object exists and returns correct rows.

### Step 5: Confirm schema visibility
- **Tool**: `get_schema` × 1-n times
- **Example**: `get_schema({})`
- **Purpose**: Ensure the new object is visible in database metadata.

## Tools Involved

- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `execute_sql`

## Tips

- Prototype with `query` before `execute_sql`.
- Use clear names for created views or report tables.
- Validate both object existence and output rows.
- Avoid overwriting unrelated objects.
