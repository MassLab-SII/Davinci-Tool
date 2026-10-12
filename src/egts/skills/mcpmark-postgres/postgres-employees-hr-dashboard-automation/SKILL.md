# Postgres Employees HR Dashboard Automation

## Description

Build HR analytics tables, materialized views, retention/cohort reports, project tracking, and executive dashboard automation in the employees schema.

## Use Cases

- Build HR headcount, salary, title, and department reports.
- Create dashboard tables or views for employee analytics.
- Analyze retention, cohorts, and project-style assignment data.
- Optimize expensive HR reporting queries with plans or indexes.
- Validate executive summaries against source tables.

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
- **Example**: `describe_table({"table_name": "employees"})`
- **Purpose**: Confirm exact column names, types, indexes, and keys.

### Step 4: Sample source rows
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT emp_no, first_name, last_name, hire_date FROM employees LIMIT 5;"})`
- **Purpose**: Understand real values and avoid schema-name guesses.

### Step 5: Inspect query plan
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT dept_no, COUNT(*) FROM dept_emp GROUP BY dept_no;"})`
- **Purpose**: Evaluate performance characteristics before or after optimization.

### Step 6: Apply SQL change
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "CREATE VIEW employee_department_counts AS SELECT dept_no, COUNT(*) AS n_employees FROM dept_emp GROUP BY dept_no;"})`
- **Purpose**: Create or modify the requested table, view, policy, function, index, or rows.

### Step 7: Verify final result
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM employee_department_counts ORDER BY n_employees DESC LIMIT 5;"})`
- **Purpose**: Confirm the final report, mutation, policy, or optimization result is observable.

## Tools Involved

- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `execute_sql`
- `explain_query`

## Tips

- Employees datasets often require joins through department and title history tables.
- Respect date ranges; current and historical rows can both exist.
- Check query plans before adding indexes for dashboard automation.
- After creating views or tables, query them to verify row counts and sample output.
