# Postgres Temporal Cohort Analysis

## Description

Analyze date and time columns, event windows, cohorts, trends, and period-over-period changes using PostgreSQL SQL.

## Use Cases

- Grouping rows by day, month, year, or season.
- Finding cohorts based on first activity, hire date, rental date, or order date.
- Comparing current and previous periods.
- Filtering records within a time window.

## Workflow

### Step 1: Find date/time columns
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "orders"})`
- **Purpose**: Identify timestamp, date, and period fields.

### Step 2: Sample date values
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT order_date FROM orders WHERE order_date IS NOT NULL LIMIT 10;"})`
- **Purpose**: Understand formats and ranges.

### Step 3: Check date coverage
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT MIN(order_date), MAX(order_date) FROM orders;"})`
- **Purpose**: Determine the valid analysis window.

### Step 4: Run cohort or trend query
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT DATE_TRUNC('month', order_date) AS month, COUNT(*) FROM orders GROUP BY month ORDER BY month;"})`
- **Purpose**: Produce the requested temporal result.

### Step 5: Explain or validate if complex
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT DATE_TRUNC('month', order_date), COUNT(*) FROM orders GROUP BY 1;"})`
- **Purpose**: Check query structure for larger temporal reports.

## Tools Involved

- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `explain_query`

## Tips

- Check min and max dates before choosing time windows.
- Use `DATE_TRUNC` for period grouping.
- Keep timezone assumptions explicit if timestamps include zones.
- Validate missing dates before interpreting cohort counts.
