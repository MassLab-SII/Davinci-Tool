# MCPMark Postgres Skill Taxonomy

This skill set combines generic SQL/DBA capabilities with task-family skills anchored to the actual MCPMark Postgres datasets.

## Dataset-Anchored Families

- `chinook`: customer migration, employee hierarchy updates, sales/music charts
- `employees`: HR analytics, materialized dashboards, retention/cohort/project/management reports
- `dvdrental`: customer analytics, film inventory management, payment/rental indexing
- `lego`: inventory consistency, transfer functions, role/RLS policies
- `sports`: baseball/player analytics, roster management, participant performance reports
- `security`: business permission audit and application RLS access rules
- `vectors`: pgvector storage/performance/data-quality analysis

## Design Rule

Generic skills such as schema investigation, join analysis, performance indexing, and transactional mutation are reusable across datasets. Dataset-anchored skills are retained because MCPMark tasks repeatedly combine multiple generic capabilities into recognizable professional workflows.
