# Account Profile Update

## Description

Retrieve and update account profile information using Level-3 account APIs. This skill covers credential-grounded profile lookup, address updates, and read-after-write verification.

## Use Cases

- Retrieve account information for a known user
- Update a user's address or personal information
- Verify a profile update by querying the same account again
- Handle invalid credentials and retry with corrected seeded credentials

## Workflow

### Step 1: Discover account tools
- **Tool**: `Lv3ToolSearcher`
- **Example**: `Lv3ToolSearcher({"keywords": "account info update personal address"})`
- **Purpose**: Find the account lookup and update APIs.

### Step 2: Retrieve account information
- **Tool**: `AccountInfo`
- **Example**: `AccountInfo({"username": "John", "password": "123456"})`
- **Purpose**: Ground the current profile before mutation.

### Step 3: Update profile information
- **Tool**: `PersonalInfoUpdate`
- **Example**: `PersonalInfoUpdate({"username": "John", "password": "123456", "address": {"city": "San Francisco", "street": "Market Street"}})`
- **Purpose**: Mutate the user's personal profile state.

### Step 4: Verify the updated account
- **Tool**: `AccountInfo`
- **Example**: `AccountInfo({"username": "John", "password": "123456"})`
- **Purpose**: Confirm the update by reading back the profile.

### Step 5: Explore another profile or invalid credential case
- **Tool**: `AccountInfo` or `PersonalInfoUpdate` × 1-n times
- **Examples**:
  - `AccountInfo({"username": "Mary", "password": "abcdef"})`
  - `AccountInfo({"username": "John", "password": "wrong"})`
- **Purpose**: Gather successful and recoverable failure evidence.

## Tools Involved

`Lv3ToolSearcher`, `AccountInfo`, `PersonalInfoUpdate`

## Tips

- Seeded credentials include `John/123456`, `Mary/abcdef`, `Peter/qwerty`, `Tom/asdfgh`, and `Jerry/zxcvbn`.
- `address` should be a JSON object, not a plain sentence.
- Always query before and after `PersonalInfoUpdate` for high-quality mutation trajectories.

