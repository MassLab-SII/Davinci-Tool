# Quiz And Submission Workflow

## Description

Inspect, create, complete, or grade Canvas quizzes and submissions using Canvas state plus local files or email evidence. Use this for Toolathlon LMS tasks involving unfinished quizzes, late assignments, quiz authoring, or homework grading.

## Use Cases

- List unfinished assignments or quizzes for a student and prepare a completion plan
- Create a Canvas quiz from locally provided questions and answers
- Match local homework files or email attachments to Canvas assignments
- Inspect submissions and produce a grade or status report

## Workflow

### Step 1: Inspect local task files
- **Tool**: `filesystem-list_directory`, then `filesystem-read_file` × 1-n times
- **Examples**:
  - `filesystem-list_directory({"path": "/workspace"})`
  - `filesystem-read_file({"path": "/workspace/quiz_questions.txt"})`
- **Purpose**: Find quiz questions, assignment files, grading scripts, student identity, or expected output tables.

### Step 2: Identify relevant Canvas courses
- **Tool**: `canvas-list_courses`
- **Example**: `canvas-list_courses({})`
- **Purpose**: Locate the course IDs for assignment, quiz, or submission inspection.

### Step 3: List assignments and quizzes
- **Tool**: `canvas-list_assignments`, `canvas-list_quizzes` × 1-n times
- **Examples**:
  - `canvas-list_assignments({"course_id": "grounded course id"})`
  - `canvas-list_quizzes({"course_id": "grounded course id"})`
- **Purpose**: Determine which assessments exist, which are due, and which match local files or task instructions.

### Step 4: Inspect submissions in detail
- **Tool**: `canvas-list_submissions`, `canvas-get_submission` × 1-n times
- **Examples**:
  - `canvas-list_submissions({"course_id": "grounded course id", "assignment_id": "grounded assignment id"})`
  - `canvas-get_submission({"course_id": "grounded course id", "assignment_id": "grounded assignment id", "user_id": "grounded user id"})`
- **Purpose**: Verify submitted/unsubmitted state, attachment evidence, grades, or quiz completion before acting.

### Step 5: Save the assessment action record
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/canvas_assessment_actions.md", "content": "Course | Assessment | Current state | Evidence | Required action\n--- | --- | --- | --- | ---"})`
- **Purpose**: Preserve which quizzes/submissions require completion, creation, grading, or notification.

### Step 6: Verify the record and Canvas state
- **Tool**: `filesystem-read_file`, then `canvas-list_submissions`
- **Examples**:
  - `filesystem-read_file({"path": "/workspace/canvas_assessment_actions.md"})`
  - `canvas-list_submissions({"course_id": "grounded course id", "assignment_id": "grounded assignment id"})`
- **Purpose**: Confirm the saved record and post-action state align with Canvas.

## Tools Involved

`canvas-list_courses`, `canvas-list_assignments`, `canvas-list_quizzes`, `canvas-list_submissions`, `canvas-get_submission`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`

## Tips

- Always distinguish course ID, assignment ID, quiz ID, and user ID
- For grading tasks, execute or inspect local submissions only after matching them to Canvas users
- Record unsubmitted, submitted, and no-final/no-action cases separately when filtering assessments
- Verify Canvas state after any submission, quiz, or grading mutation
