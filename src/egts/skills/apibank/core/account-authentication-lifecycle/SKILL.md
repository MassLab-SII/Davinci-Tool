# Account Authentication Lifecycle

## Description

Manage API-Bank user accounts through registration, login token retrieval, token validation, password recovery, password modification, and account deletion. This skill is the foundation for token-protected API workflows.

## Use Cases

- Register a new user and retrieve a valid token for downstream tools
- Validate whether a token can access protected account data
- Recover a forgotten password with the two-step verification flow
- Modify a password and verify the old token or new credentials
- Delete an account after confirming its token is valid

## Workflow

### Step 1: Discover account-related APIs
- **Tool**: `ToolSearcher`
- **Example**: `ToolSearcher({"keywords": "register user login token password account"})`
- **Purpose**: Identify account tools and confirm when `GetUserToken` is needed before protected mutations.

### Step 2: Create or select credentials
- **Tool**: `RegisterUser`
- **Example**: `RegisterUser({"username": "alice_demo", "password": "Pass1234", "email": "alice@example.com"})`
- **Purpose**: Create an account when the task requires a new user. Reuse known benchmark credentials only when the task gives them.

### Step 3: Retrieve authentication token
- **Tool**: `GetUserToken` × 1-n times
- **Example**: `GetUserToken({"username": "alice_demo", "password": "Pass1234"})`
- **Purpose**: Obtain the token needed by protected account, calendar, meeting, reminder, finance, and assistant APIs.

### Step 4: Validate token status
- **Tool**: `CheckToken`
- **Example**: `CheckToken({"token": "returned_token"})`
- **Purpose**: Verify that the token is active before using it in downstream operations.

### Step 5: Recover or modify password when needed
- **Tool**: `ForgotPassword` or `ModifyPassword`
- **Examples**:
  - `ForgotPassword({"status": "Forgot Password", "username": "alice_demo", "email": "alice@example.com"})`
  - `ForgotPassword({"status": "Verification Code", "verification_code": 970420, "new_password": "NewPass123"})`
  - `ModifyPassword({"token": "returned_token", "old_password": "Pass1234", "new_password": "NewPass123"})`
- **Purpose**: Exercise both the two-call recovery flow and authenticated password update flow.

### Step 6: Verify final account access
- **Tool**: `GetUserToken` or `CheckToken` × 1-n times
- **Example**: `GetUserToken({"username": "alice_demo", "password": "NewPass123"})`
- **Purpose**: Confirm the final credential/token state after password changes.

### Step 7: Delete account if the task requires cleanup
- **Tool**: `DeleteAccount`
- **Example**: `DeleteAccount({"token": "returned_token"})`
- **Purpose**: Remove the account and create a clear mutation trajectory.

## Tools Involved

`ToolSearcher`, `RegisterUser`, `GetUserToken`, `CheckToken`, `ForgotPassword`, `ModifyPassword`, `DeleteAccount`

## Tips

- Many API-Bank tools require `token`; call `GetUserToken` before protected operations.
- `ForgotPassword` is intentionally multi-step: first request a code, then pass `verification_code` and `new_password`.
- Use follow-up token checks after password or deletion operations to make the trajectory verifiable.
