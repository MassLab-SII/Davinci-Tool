# Postgres Join Analysis

## Description

Infer relationships across tables, write joins, validate cardinality, and extract linked records or summaries from relational databases.

## Use Cases

- Joining customers to orders, albums to tracks, teams to games, or entities to attributes.
- Finding records that depend on foreign-key-like relationships.
- Building multi-table reports.
- Checking whether a join duplicates or drops records unexpectedly.

## Workflow

### Step 1: Inspect schema relationships
- **Tool**: `get_schema` × 1-n times
- **Example**: `get_schema({})`
- **Purpose**: Identify candidate key columns and table relationships.

### Step 2: Describe the joined tables
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "orders"})`
- **Purpose**: Confirm column types and key names.

### Step 3: Sample join keys
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT customer_id FROM orders LIMIT 5;"})`
- **Purpose**: Verify values and naming before writing the join.

### Step 4: Run the joined query
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT c.name, o.order_id FROM customers c JOIN orders o ON o.customer_id = c.customer_id LIMIT 10;"})`
- **Purpose**: Extract linked records or produce a multi-table result.

### Step 5: Check cardinality or plan
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT c.name, o.order_id FROM customers c JOIN orders o ON o.customer_id = c.customer_id;"})`
- **Purpose**: Validate that the join is plausible and not accidental.

## Tools Involved

- `get_schema`
- `describe_table`
- `list_tables`
- `query`
- `explain_query`

## Tips

- Do not guess join keys; inspect both sides.
- Use table aliases for readability.
- Validate many-to-one versus many-to-many joins with counts.
- Add filters after confirming the base join works.
