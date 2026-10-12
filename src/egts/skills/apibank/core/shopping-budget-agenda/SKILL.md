# Shopping Budget Agenda

## Description

Plan a shopping-like task by checking balance, calculating a budget, creating agenda/reminder entries, and verifying stored planning records. This skill reflects API-Bank Level-3 shopping scenes using stable core APIs.

## Use Cases

- Check whether a user has enough balance for a purchase
- Calculate remaining budget after planned spending
- Add a shopping agenda item or reminder
- Query reminders and agenda items to verify the plan

## Workflow

### Step 1: Retrieve token
- **Tool**: `GetUserToken`
- **Example**: `GetUserToken({"username": "John", "password": "123456"})`
- **Purpose**: Balance, agenda, and reminder tools require authenticated user context.

### Step 2: Query current balance
- **Tool**: `QueryBalance`
- **Example**: `QueryBalance({"token": "returned_token"})`
- **Purpose**: Ground budget decisions in financial evidence.

### Step 3: Calculate shopping budget
- **Tool**: `Calculator` × 1-n times
- **Example**: `Calculator({"formula": "500 - 129.99"})`
- **Purpose**: Compute remaining funds, total price, or affordability.

### Step 4: Add shopping agenda
- **Tool**: `AddAgenda`
- **Example**: `AddAgenda({"token": "returned_token", "content": "buy groceries", "time": "2023-04-02 18:00:00", "location": "supermarket"})`
- **Purpose**: Store the shopping trip as a calendar plan.

### Step 5: Add shopping reminder
- **Tool**: `AddReminder` × 1-n times
- **Example**: `AddReminder({"token": "returned_token", "content": "bring reusable bags and coupon", "time": "2023-04-02 17:30:00"})`
- **Purpose**: Store shopping-specific follow-up actions.

### Step 6: Verify agenda and reminder
- **Tool**: `QueryAgenda` or `QueryReminder` × 1-n times
- **Examples**:
  - `QueryAgenda({"token": "returned_token", "content": "buy groceries", "time": "2023-04-02 18:00:00", "location": "supermarket"})`
  - `QueryReminder({"token": "returned_token", "content": "bring reusable bags and coupon", "time": "2023-04-02 17:30:00"})`
- **Purpose**: Confirm the budget-driven plan was stored.

## Tools Involved

`GetUserToken`, `QueryBalance`, `Calculator`, `AddAgenda`, `QueryAgenda`, `AddReminder`, `QueryReminder`

## Tips

- Query balance before calculating affordability.
- Use calculator outputs to justify agenda/reminder content.
- Create at least one verification query after adding shopping records.
