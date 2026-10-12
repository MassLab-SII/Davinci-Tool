# Postgres Data Quality Audit

## Description

Find data quality issues such as missing values, duplicates, orphaned references, invalid ranges, inconsistent labels, and suspicious records.

## Use Cases

- Auditing a table for nulls or duplicate records.
- Finding rows with impossible dates, negative values, or invalid statuses.
- Checking foreign-key-like relationships for orphaned records.
- Producing a concise quality report.

## Workflow

### Step 1: Select audit target
- **Tool**: `list_tables` × 1-n times and `describe_table`
- **Example**: `describe_table({"table_name": "employees"})`
- **Purpose**: Identify columns that can be audited.

### Step 2: Check missing values
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT COUNT(*) FROM employees WHERE email IS NULL;"})`
- **Purpose**: Quantify nulls in important fields.

### Step 3: Check duplicates
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT email, COUNT(*) FROM employees GROUP BY email HAVING COUNT(*) > 1;"})`
- **Purpose**: Identify repeated values that should be unique.

### Step 4: Check invalid values
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM employees WHERE hire_date > CURRENT_DATE LIMIT 20;"})`
- **Purpose**: Find records outside expected ranges or formats.

### Step 5: Summarize findings
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT status, COUNT(*) FROM employees GROUP BY status;"})`
- **Purpose**: Provide counts and examples that support the final audit.

## Tools Involved

- `list_tables`
- `get_schema`
- `describe_table`
- `query`

## Tips

- Audit with counts first, then sample example rows.
- Use `GROUP BY ... HAVING COUNT(*) > 1` for duplicates.
- Validate expected categories before calling values invalid.
- Keep the final report grounded in query output.
