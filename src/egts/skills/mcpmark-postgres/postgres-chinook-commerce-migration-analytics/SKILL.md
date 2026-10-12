# Postgres Chinook Commerce Migration Analytics

## Description

Handle Chinook commerce workflows: customer migration, employee reporting hierarchy changes, and music sales/chart analytics.

## Use Cases

- Analyze Chinook customers, invoices, tracks, artists, albums, and employees.
- Build music sales reports and customer migration summaries.
- Modify reporting or migration helper tables with verification.
- Inspect employee/customer hierarchy before writing update SQL.
- Validate commerce analytics with before-and-after queries.

## Workflow

### Step 1: List candidate tables
- **Tool**: `list_tables` × 1-n times
- **Example**: `list_tables({})`
- **Purpose**: Identify relevant tables before writing SQL.

### Step 2: Inspect schema structure
- **Tool**: `get_schema` × 1-n times
- **Example**: `get_schema({})`
- **Purpose**: Review columns, relations, and available schemas.

### Step 3: Describe target table
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "customers"})`
- **Purpose**: Confirm exact column names, types, indexes, and keys.

### Step 4: Sample source rows
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT customer_id, first_name, last_name, country FROM customers LIMIT 5;"})`
- **Purpose**: Understand real values and avoid schema-name guesses.

### Step 5: Apply SQL change
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "CREATE VIEW chinook_country_sales AS SELECT c.country, SUM(i.total) AS sales FROM customers c JOIN invoices i ON i.customer_id = c.customer_id GROUP BY c.country;"})`
- **Purpose**: Create or modify the requested table, view, policy, function, index, or rows.

### Step 6: Verify final result
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM chinook_country_sales ORDER BY sales DESC LIMIT 5;"})`
- **Purpose**: Confirm the final report, mutation, policy, or optimization result is observable.

## Tools Involved

- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `execute_sql`

## Tips

- Chinook table names can be mixed case; use schema inspection before querying.
- Validate joins among customers, invoices, invoice lines, tracks, and albums.
- For mutation tasks, read affected rows before and after `execute_sql`.
- Use `LIMIT` while exploring, then run exact aggregate queries for final evidence.
