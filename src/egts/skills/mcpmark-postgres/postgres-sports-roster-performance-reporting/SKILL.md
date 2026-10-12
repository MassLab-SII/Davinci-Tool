# Postgres Sports Roster Performance Reporting

## Description

Build sports analytics reports, roster/player management tables, participant/event statistics, and performance indexes.

## Use Cases

- Build participant, roster, event, school, and performance reports.
- Create reporting tables or views for sports analytics.
- Analyze event participation and rankings across dimensions.
- Add indexes for roster or participant lookup workloads.
- Validate report outputs with grouped source-table checks.

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
- **Example**: `describe_table({"table_name": "participants"})`
- **Purpose**: Confirm exact column names, types, indexes, and keys.

### Step 4: Sample source rows
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM participants LIMIT 5;"})`
- **Purpose**: Understand real values and avoid schema-name guesses.

### Step 5: Inspect query plan
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT event_id, COUNT(*) FROM participants GROUP BY event_id;"})`
- **Purpose**: Evaluate performance characteristics before or after optimization.

### Step 6: Apply SQL change
- **Tool**: `execute_sql` × 1-n times
- **Example**: `execute_sql({"sql": "CREATE VIEW sports_event_participation AS SELECT event_id, COUNT(*) AS n_participants FROM participants GROUP BY event_id;"})`
- **Purpose**: Create or modify the requested table, view, policy, function, index, or rows.

### Step 7: Verify final result
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT * FROM sports_event_participation ORDER BY n_participants DESC LIMIT 5;"})`
- **Purpose**: Confirm the final report, mutation, policy, or optimization result is observable.

## Tools Involved

- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `execute_sql`
- `explain_query`

## Tips

- Sports schemas can have many tables; identify the event/person/team keys first.
- Use grouped counts to validate reports before writing final artifacts.
- For performance work, compare plans before and after index creation.
- Avoid assuming a single participant table; inspect schema names and relationships.
