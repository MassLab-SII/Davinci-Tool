# Postgres Performance and Indexing

## Description

Analyze SQL performance using query plans and schema metadata, then create or assess indexes and query rewrites when the task calls for optimization.

## Use Cases

- Explaining why a query is slow.
- Creating indexes for filters, joins, or ordering.
- Comparing query plans before and after an index.
- Validating performance-oriented SQL changes.

## Workflow

### Step 1: Understand table structure
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "orders"})`
- **Purpose**: Identify columns, existing indexes, and likely filter keys.

### Step 2: Run the baseline query
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM orders WHERE customer_id = 10 LIMIT 10;"})`
- **Purpose**: Confirm the query is valid and returns expected rows.

### Step 3: Explain the query plan
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT * FROM orders WHERE customer_id = 10;"})`
- **Purpose**: Identify scans, joins, sort steps, and index usage.

### Step 4: Apply an index or rewrite
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);"})`
- **Purpose**: Implement the performance-oriented change.

### Step 5: Re-check the plan
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT * FROM orders WHERE customer_id = 10;"})`
- **Purpose**: Verify the plan reflects the intended optimization.

## Tools Involved

- `describe_table`
- `get_schema`
- `query`
- `explain_query`
- `execute_sql`

## Tips

- Explain the exact query you intend to optimize.
- Avoid creating redundant indexes if the schema already has one.
- Validate that an index matches the query predicate or join key.
- Treat plan changes as evidence; do not rely only on intuition.
