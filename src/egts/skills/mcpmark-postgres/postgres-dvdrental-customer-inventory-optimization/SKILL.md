# Postgres Dvdrental Customer Inventory Optimization

## Description

Analyze DVD rental customer behavior, payment/rental performance, inventory availability, and indexing/optimization tasks.

## Use Cases

- Analyze rental, payment, customer, film, staff, and inventory behavior.
- Optimize inventory availability or customer segmentation reports.
- Create indexes or reporting views for rental-performance questions.
- Identify top customers, stores, categories, or late-return patterns.
- Validate optimizations with result queries and query plans.

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
- **Example**: `describe_table({"table_name": "rental"})`
- **Purpose**: Confirm exact column names, types, indexes, and keys.

### Step 4: Sample source rows
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT rental_id, rental_date, inventory_id, customer_id FROM rental LIMIT 5;"})`
- **Purpose**: Understand real values and avoid schema-name guesses.

### Step 5: Inspect query plan
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT customer_id, COUNT(*) FROM rental GROUP BY customer_id;"})`
- **Purpose**: Evaluate performance characteristics before or after optimization.

### Step 6: Apply SQL change
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "CREATE INDEX IF NOT EXISTS idx_rental_customer_id ON rental(customer_id);"})`
- **Purpose**: Create or modify the requested table, view, policy, function, index, or rows.

### Step 7: Verify final result
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "EXPLAIN SELECT * FROM rental WHERE customer_id = 1;"})`
- **Purpose**: Confirm the final report, mutation, policy, or optimization result is observable.

## Tools Involved

- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `execute_sql`
- `explain_query`

## Tips

- Rental workflows usually require joins across customer, rental, inventory, film, payment, and store.
- Confirm whether the task asks for mutation, view creation, or read-only analysis.
- Use `explain_query` before and after performance-oriented changes.
- Keep customer and inventory counts grounded in real rows, not table names.
