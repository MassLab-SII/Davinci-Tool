# Multi-Step Transaction Completion

## Description
Complete multi-page form transactions such as booking flights, buying tickets, ordering food, filling form sequences, and managing social media interactions. These MiniWoB++ tasks require navigating through multiple screens/pages, filling fields at each step, and finalizing the transaction.

## Use Cases
- book-flight, book-flight-nodelay — search and book a flight
- buy-ticket — purchase a ticket through a multi-step form
- order-food — place a food order with multiple selections
- form-sequence, form-sequence-2, form-sequence-3 — complete multi-page form sequences
- social-media, social-media-all, social-media-some — manage social media content

## Workflow

1. **Read the full instruction carefully**
   - Tool: `get_instruction`
   - Example: `get_instruction()` → understand the complete transaction goal
   - Purpose: Know the final outcome and all required steps

2. **Observe the first page/form**
   - Tool: `get_observation`, `get_dom_elements`
   - Example: `get_observation()` → see form fields, buttons; `get_dom_elements()` → get refs
   - Purpose: Map all fields and buttons on the first step

3. **Check pre-filled field values** (if any)
   - Tool: `get_fields`
   - Example: `get_fields()` → see what's already entered
   - Purpose: Know what needs to be filled

4. **Fill the first page's fields**
   - Tool: `type_text`
   - Example: `type_text(ref=2, text="New York")` → fill origin city for a flight
   - Purpose: Enter required data

5. **Navigate to the next page** (click Next, Search, or Continue)
   - Tool: `click_element` or `press_key`
   - Example: `click_element(ref=8)` — click the Search/Next button
   - Purpose: Advance the transaction

6. **Observe the new page** and repeat for each step
   - Tool: `get_observation`, `get_dom_elements`
   - Example: Get fresh element refs and page content after navigation
   - Purpose: Each page may have different fields and options

7. **Make selections from results** (e.g., choose a flight, select a food item)
   - Tool: `click_element`
   - Example: `click_element(ref=5)` — select a flight from the results
   - Purpose: Choose from the options presented

8. **Review and submit/confirm** the final step
   - Tool: `click_element` on the final submit/confirm button
   - Example: `click_element(ref=12)` — click "Complete Booking" or "Place Order"
   - Purpose: Finalize the transaction

9. **Verify completion**
   - Tool: `get_observation`
   - Example: `get_observation()` → see confirmation message
   - Purpose: Confirm the transaction was successful

## Tools Involved
- `get_instruction` — transaction goal
- `get_observation` — each page's state
- `get_dom_elements` — element refs per page
- `get_fields` — current field values
- `type_text` — fill form fields
- `click_element` — navigate and submit
- `press_key` — keyboard navigation (Enter to submit, Tab to move)

## Tips
- Always re-query `get_dom_elements()` after each page transition — EGTS refs change completely
- Keep track of which step you're on; multi-step forms may have 3-5 pages
- For flight booking: departure city, destination, dates, and passenger info are typical fields
- For food ordering: cuisine type, specific items, quantity, and delivery details are common steps
- For social media: like, share, comment, and follow are the main operations
- If a page load is slow (nodelay variants), wait briefly before querying DOM elements
- Form validation errors may appear on any step — read error messages and correct the relevant field
- The confirmation page usually contains a success message or order number
