# Postgres Vector Similarity Search

## Description

Inspect vector or embedding tables, run similarity-style retrieval queries, and validate nearest-neighbor results in vector-focused databases.

## Use Cases

- Finding rows nearest to an embedding or vector.
- Inspecting vector dimensions and indexes.
- Checking whether pgvector-like extensions are available.
- Explaining or validating vector retrieval behavior.

## Workflow

### Step 1: Inspect database capabilities
- **Tool**: `get_database_info`
- **Example**: `get_database_info({})`
- **Purpose**: Check extensions and database metadata relevant to vector search.

### Step 2: Locate vector tables
- **Tool**: `list_tables` × 1-n times and `get_schema`
- **Example**: `get_schema({})`
- **Purpose**: Identify tables and columns that store embeddings or vector-like data.

### Step 3: Describe target table
- **Tool**: `describe_table` × 1-n times
- **Example**: `describe_table({"table_name": "documents"})`
- **Purpose**: Confirm vector column type and associated metadata columns.

### Step 4: Run similarity query
- **Tool**: `query` × 1-n times
- **Example**: `query({"sql": "SELECT id, content FROM documents ORDER BY embedding <-> '[0.1,0.2,0.3]' LIMIT 5;"})`
- **Purpose**: Retrieve nearest records for the target vector.

### Step 5: Explain retrieval query
- **Tool**: `explain_query` × 1-n times
- **Example**: `explain_query({"sql": "SELECT id FROM documents ORDER BY embedding <-> '[0.1,0.2,0.3]' LIMIT 5;"})`
- **Purpose**: Check whether vector indexes or scan behavior are relevant.

## Tools Involved

- `get_database_info`
- `list_tables`
- `get_schema`
- `describe_table`
- `query`
- `explain_query`

## Tips

- Confirm vector dimensions before constructing literal vectors.
- Use the operator supported by the database extension and column type.
- Retrieve metadata with the vector result so the answer is interpretable.
- Explain only valid SQL that already runs or is clearly well-formed.
