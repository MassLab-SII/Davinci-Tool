# Postgres Schema Investigation

## Description

Inspect a PostgreSQL database before writing task-specific SQL. This skill establishes the database scope, available tables, relationships, and representative rows.

## Use Cases

- Understanding an unfamiliar benchmark database.
- Finding candidate tables and columns for a query.
- Checking constraints, indexes, or column types before mutation.
- Grounding later SQL in actual schema evidence.

## Workflow

### Step 1: Read database metadata
- **Tool**: `get_database_info`
- **Example**: `get_database_info({})`
- **Purpose**: Confirm database name, extensions, schemas, and high-level metadata.

### Step 2: List available tables
- **Tool**: `list_tables` × 1-n times
- **Example**: `list_tables({})`
- **Purpose**: Identify candidate tables before choosing where to query.

### Step 3: Inspect schema definitions
- **Tool**: `get_schema` × 1-n times
- **Example**: `get_schema({})`
- **Purpose**: Review columns, relations, and schema-level structure.

### Step 4: Describe target tables
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "orders"})`
- **Purpose**: Confirm column names, types, keys, and indexes for a table.

### Step 5: Sample representative rows
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM orders LIMIT 5;"})`
- **Purpose**: Understand real values and avoid writing SQL from names alone.

## Tools Involved

- `get_database_info`
- `list_tables`
- `get_schema`
- `describe_table`
- `query`

## Tips

- Inspect before mutating; schema mistakes are expensive in trajectory collection.
- Prefer exact column names from `describe_table`.
- Sample rows with `LIMIT` to understand value formats.
- When tables are related, verify key columns before joining.
