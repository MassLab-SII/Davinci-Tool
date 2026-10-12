# Course Roster And Assignment Review

## Description

Review Canvas courses, rosters, assignments, and local course files to decide enrollment, exam, or course-management actions. Use this for Toolathlon Canvas LMS tasks involving course setup, new-student enrollment, exam schedules, or assignment inventory.

## Use Cases

- Identify courses a user teaches or attends from Canvas and local course files
- Compare Canvas rosters with local student lists before enrollment or notification
- Gather assignment and announcement evidence for course-management reports
- Save a course roster, assignment, or exam-status table in the workspace

## Workflow

### Step 1: Inspect local course files
- **Tool**: `filesystem-list_directory`, then `filesystem-read_file` × 1-n times
- **Examples**:
  - `filesystem-list_directory({"path": "/workspace"})`
  - `filesystem-read_file({"path": "/workspace/course_summary.txt"})`
- **Purpose**: Locate local rosters, schedules, templates, or spreadsheets that define the Canvas task.

### Step 2: List Canvas courses
- **Tool**: `canvas-list_courses`
- **Example**: `canvas-list_courses({})`
- **Purpose**: Find candidate courses and course IDs. Match against local course names/codes and remove task-specific suffixes or aliases when required.

### Step 3: Inspect selected course details and users
- **Tool**: `canvas-get_course`, `canvas-list_users` × 1-n times
- **Examples**:
  - `canvas-get_course({"course_id": "grounded course id"})`
  - `canvas-list_users({"course_id": "grounded course id"})`
- **Purpose**: Verify instructor/student membership before making course-management decisions.

### Step 4: Inspect assignments or announcements-related records
- **Tool**: `canvas-list_assignments` × 1-n times
- **Example**: `canvas-list_assignments({"course_id": "grounded course id"})`
- **Purpose**: Gather deadlines, assignment names, or exam-related course evidence for the final table/report.

### Step 5: Write the course evidence table
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/course_canvas_review.md", "content": "Course | Role | Roster evidence | Assignment/exam evidence | Action\n--- | --- | --- | --- | ---"})`
- **Purpose**: Persist a structured course review that can drive enrollment, notification, or schedule-filling tasks.

### Step 6: Verify saved evidence and Canvas state
- **Tool**: `filesystem-read_file`, then `canvas-list_courses`
- **Examples**:
  - `filesystem-read_file({"path": "/workspace/course_canvas_review.md"})`
  - `canvas-list_courses({})`
- **Purpose**: Confirm the output exists and remains aligned with Canvas course IDs.

## Tools Involved

`canvas-list_courses`, `canvas-get_course`, `canvas-list_users`, `canvas-list_assignments`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`

## Tips

- Treat Canvas course IDs as grounded identifiers; do not reuse names where an ID is required
- When local course codes include suffixes, normalize only according to task instructions
- Record courses excluded from the final answer when the task has filtering rules
- Verify Canvas state after any course-management mutation using list/get tools
