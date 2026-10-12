# Finance Balance Stock Planning

## Description

Explore API-Bank finance workflows by combining account/token access, bank balance lookup, stock lookup, calculator reasoning, bank-account creation, and financial reminders.

## Use Cases

- Query balance before planning a purchase or transfer
- Look up stock data and calculate changes or totals
- Open a bank account and verify account-related state changes
- Add reminders for bills, investments, or financial follow-up

## Workflow

### Step 1: Discover finance tools
- **Tool**: `ToolSearcher`
- **Example**: `ToolSearcher({"keywords": "balance stock calculator bank account reminder"})`
- **Purpose**: Ground the workflow in API-Bank's available finance APIs.

### Step 2: Retrieve token
- **Tool**: `GetUserToken`
- **Example**: `GetUserToken({"username": "John", "password": "123456"})`
- **Purpose**: Balance query and reminder tools require a token.

### Step 3: Query balance
- **Tool**: `QueryBalance` × 1-n times
- **Example**: `QueryBalance({"token": "returned_token"})`
- **Purpose**: Obtain financial state before planning or budgeting.

### Step 4: Query stock information
- **Tool**: `QueryStock` × 1-n times
- **Example**: `QueryStock({"stock_code": "AAPL", "date": "2023-03-31"})`
- **Purpose**: Retrieve stock evidence for investment or comparison tasks.

### Step 5: Calculate derived values
- **Tool**: `Calculator` × 1-n times
- **Example**: `Calculator({"formula": "2500 - 799"})`
- **Purpose**: Compute budgets, remaining balances, percentages, or totals from API results.

### Step 6: Open bank account when required
- **Tool**: `OpenBankAccount`
- **Example**: `OpenBankAccount({"account": "alice_bank", "password": "BankPass123", "name": "Alice"})`
- **Purpose**: Exercise a finance mutation workflow with local API state.

### Step 7: Add financial reminder
- **Tool**: `AddReminder`
- **Example**: `AddReminder({"token": "returned_token", "content": "review stock portfolio", "time": "2023-04-03 09:00:00"})`
- **Purpose**: Store follow-up action based on financial evidence.

### Step 8: Verify final plan
- **Tool**: `QueryReminder` or `QueryBalance`
- **Example**: `QueryReminder({"token": "returned_token", "content": "review stock portfolio", "time": "2023-04-03 09:00:00"})`
- **Purpose**: Confirm the finance-derived plan or final state.

## Tools Involved

`ToolSearcher`, `GetUserToken`, `QueryBalance`, `QueryStock`, `Calculator`, `OpenBankAccount`, `AddReminder`, `QueryReminder`

## Tips

- Use `Calculator` after retrieving numeric API outputs, not before.
- Query balance before adding budget reminders.
- `OpenBankAccount` has local state; use unique account names to avoid duplicate failures.
