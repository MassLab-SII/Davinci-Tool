# Finance Market and Asset Lookup

## Description

Use finance, market, stock, asset, income, currency, and business APIs to answer financial information requests. This skill emphasizes precise parameter grounding for symbols, dates, ZIP codes, currencies, and market identifiers.

## Use Cases

- Retrieve stock, asset, market, or company information
- Compare finance APIs that expose similar quote or history endpoints
- Query income, financial statistics, or economic indicators
- Validate financial API calls through trace and schema checks

## Workflow

### Step 1: Identify financial entities
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Extract tickers, company names, ZIP codes, currencies, date ranges, or requested metrics.

### Step 2: Search finance candidates
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "finance stock quote symbol history", "top_k": 6})`
- **Purpose**: Find finance-related APIs and endpoints that match the metric being requested.

### Step 3: Inspect parameter requirements
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Finance::Yahoo Finance_v2::Get Stock Quote"})`
- **Purpose**: Confirm whether the API expects a symbol, region, date, interval, ZIP code, or other identifier.

### Step 4: Call the finance API
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Finance::Yahoo Finance_v2::Get Stock Quote", "arguments": {"symbol": "AAPL"}})`
- **Purpose**: Retrieve deterministic financial evidence with complete arguments.

### Step 5: Verify the evidence
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Ensure the selected API was successful and relevant to the financial request.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Keep symbols and currency codes exactly as written
- For dates and intervals, prefer schema defaults unless the request specifies a range
- If a company name is provided without a ticker, search both the company and finance terms
- Compare quote, history, and profile endpoints before calling when the request is ambiguous
