# Postgres Aggregate Reporting

## Description

Build SQL reports using grouping, filtering, aggregation, ordering, and ranking. This skill is read-oriented and focuses on producing accurate summarized results.

## Use Cases

- Counting records by category, status, team, customer, or period.
- Ranking top entities by revenue, quantity, score, or frequency.
- Computing averages, totals, minimums, and maximums.
- Producing concise answers from benchmark databases.

## Workflow

### Step 1: Locate source tables
- **Tool**: `list_tables` × 1-n times
- **Example**: `list_tables({})`
- **Purpose**: Identify which tables contain the report data.

### Step 2: Inspect relevant columns
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "invoice"})`
- **Purpose**: Confirm grouping keys, numeric measures, and filters.

### Step 3: Sample values
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT status, amount FROM invoice LIMIT 10;"})`
- **Purpose**: Understand value formats and null behavior.

### Step 4: Run aggregate query
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT status, COUNT(*) AS n FROM invoice GROUP BY status ORDER BY n DESC;"})`
- **Purpose**: Produce the requested summarized result.

### Step 5: Verify edge cases
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT COUNT(*) FROM invoice WHERE status IS NULL;"})`
- **Purpose**: Check whether missing or special values affect the result.

## Tools Involved

- `list_tables`
- `describe_table`
- `get_schema`
- `query`

## Tips

- Alias aggregate columns to make results readable.
- Use `ORDER BY` and `LIMIT` for ranking tasks.
- Verify nulls when grouping categories.
- Keep the final answer tied to query output.
