# Postgres Lego Inventory Consistency Security

## Description

Enforce LEGO inventory consistency, implement transfer functions, and manage theme-based RLS/security policies.

## Use Cases

- Analyze LEGO sets, parts, colors, themes, inventory, and inventory parts.
- Enforce inventory consistency with functions, updates, or constraints.
- Build theme or part availability reports.
- Implement or audit row-level security policies for theme-scoped access.
- Verify security and consistency changes with role-aware checks.

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
- **Example**: `describe_table({"table_name": "inventories"})`
- **Purpose**: Confirm exact column names, types, indexes, and keys.

### Step 4: Sample source rows
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT id, version, set_num FROM inventories LIMIT 5;"})`
- **Purpose**: Understand real values and avoid schema-name guesses.

### Step 5: Inspect query plan
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT theme_id, COUNT(*) FROM sets GROUP BY theme_id;"})`
- **Purpose**: Evaluate performance characteristics before or after optimization.

### Step 6: Apply SQL change
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "CREATE VIEW lego_theme_inventory AS SELECT s.theme_id, COUNT(*) AS n_sets FROM sets s GROUP BY s.theme_id;"})`
- **Purpose**: Create or modify the requested table, view, policy, function, index, or rows.

### Step 7: Verify final result
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM lego_theme_inventory ORDER BY n_sets DESC LIMIT 5;"})`
- **Purpose**: Confirm the final report, mutation, policy, or optimization result is observable.

## Tools Involved

- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `execute_sql`
- `explain_query`

## Tips

- Inspect theme, inventory, and part relationships before writing joins.
- For transfer or consistency functions, validate source and destination counts before and after.
- Security tasks require checking roles, grants, policies, and visible rows.
- Prefer small verification queries that prove the invariant changed as intended.
