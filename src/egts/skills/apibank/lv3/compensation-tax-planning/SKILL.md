# Compensation Tax Planning

## Description

Plan compensation scenarios by looking up occupation salary, calculating tax-adjusted income, and performing follow-up arithmetic. This skill covers salary and tax planning workflows.

## Use Cases

- Query salary for a known occupation
- Calculate after-tax salary
- Compare gross and after-tax income
- Run arithmetic summaries over salary or tax results

## Workflow

### Step 1: Discover compensation APIs
- **Tool**: `Lv3ToolSearcher`
- **Example**: `Lv3ToolSearcher({"keywords": "occupation salary tax calculator"})`
- **Purpose**: Identify salary, tax, and calculation APIs.

### Step 2: Query occupation salary
- **Tool**: `GetOccupationSalary`
- **Example**: `GetOccupationSalary({"occupation": "Software Engineer"})`
- **Purpose**: Retrieve salary evidence for a career or occupation.

### Step 3: Calculate tax-adjusted income
- **Tool**: `TaxCalculator`
- **Example**: `TaxCalculator({"salary": 100000})`
- **Purpose**: Convert gross salary into after-tax salary.

### Step 4: Run arithmetic comparison
- **Tool**: `Lv3Calculator`
- **Example**: `Lv3Calculator({"formula": "100000 - 80000"})`
- **Purpose**: Compute tax delta, monthly amount, or simple comparison values.

### Step 5: Explore another occupation or salary
- **Tool**: `GetOccupationSalary` or `TaxCalculator` × 1-n times
- **Example**: `TaxCalculator({"salary": 50000})`
- **Purpose**: Compare multiple compensation cases.

## Tools Involved

`Lv3ToolSearcher`, `GetOccupationSalary`, `TaxCalculator`, `Lv3Calculator`

## Tips

- Use occupation names likely present in the seeded API, and recover by trying another occupation if one fails.
- `TaxCalculator` accepts numeric salary values.
- Keep arithmetic formulas simple; `Lv3Calculator` supports basic integer operations.

