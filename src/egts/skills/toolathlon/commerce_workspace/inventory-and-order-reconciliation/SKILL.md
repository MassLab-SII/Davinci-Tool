# Inventory And Order Reconciliation

## Description

Reconcile WooCommerce orders, products, and local inventory records to decide stock, category, or fulfillment updates. Use this for Toolathlon commerce tasks involving warehouse SQLite files, low-selling products, order-derived material consumption, or product availability.

## Use Cases

- Compare WooCommerce product stock with local warehouse inventory records
- Identify products that meet low-selling or aging criteria and require category updates
- Derive raw-material changes from paid orders and local bill-of-material files
- Save a reconciliation table before mutating product records

## Workflow

### Step 1: Read local inventory or rule files
- **Tool**: `filesystem-read_file` × 1-n times
- **Example**: `filesystem-read_file({"path": "/workspace/stock_thresholds.csv"})`
- **Purpose**: Load warehouse records, thresholds, SKU mappings, BOM rules, or category criteria before querying WooCommerce.

### Step 2: List relevant products
- **Tool**: `woocommerce-list_products` × 1-n times
- **Example**: `woocommerce-list_products({})`
- **Purpose**: Collect product IDs, SKUs, categories, stock quantities, and visibility state needed for reconciliation.

### Step 3: List relevant orders
- **Tool**: `woocommerce-list_orders` × 1-n times
- **Example**: `woocommerce-list_orders({"status": "completed"})`
- **Purpose**: Identify paid/completed/recent orders and line-item quantities that affect inventory decisions.

### Step 4: Write a reconciliation plan
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/inventory_reconciliation.md", "content": "SKU | Local inventory | Woo stock | Order evidence | Action\n--- | --- | --- | --- | ---"})`
- **Purpose**: Save the evidence and intended product changes before mutating the store.

### Step 5: Apply grounded product updates when required
- **Tool**: `woocommerce-update_product` × 1-n times
- **Example**: `woocommerce-update_product({"id": "grounded product id", "stock_quantity": 12})`
- **Purpose**: Update only products whose IDs and desired changes are supported by the reconciliation plan.

### Step 6: Verify WooCommerce and saved evidence
- **Tool**: `woocommerce-list_products`, `woocommerce-list_orders`, `filesystem-read_file` × 1-n times
- **Examples**:
  - `woocommerce-list_products({})`
  - `filesystem-read_file({"path": "/workspace/inventory_reconciliation.md"})`
- **Purpose**: Confirm post-update product state and durable reconciliation evidence.

## Tools Involved

`woocommerce-list_products`, `woocommerce-list_orders`, `woocommerce-update_product`, `filesystem-read_file`, `filesystem-write_file`

## Tips

- Use product IDs for updates; preserve SKU/name only as human-readable evidence
- Separate products that need no action from products that need category, stock, or visibility updates
- Verify after every store mutation with a fresh product listing
- If local inventory and WooCommerce disagree, record both values and the rule used to choose the final action
