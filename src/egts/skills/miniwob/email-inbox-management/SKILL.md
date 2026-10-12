# Email Inbox Management

## Description
Scan an email inbox interface and perform email operations: forward, reply, delete, star, and mark as important. These MiniWoB++ tasks simulate real-world email management workflows through a webmail interface.

## Use Cases
- email-inbox — general inbox navigation and reading
- email-inbox-delete — find and delete specific emails
- email-inbox-forward, email-inbox-forward-nl, email-inbox-forward-nl-turk — forward emails to specific recipients
- email-inbox-reply — reply to emails
- email-inbox-star-reply — star and reply to emails
- email-inbox-important — mark emails as important
- email-inbox-nl-turk — natural language email management
- email-inbox-noscroll — inbox management without scrolling

## Workflow

1. **Read the email management instruction**
   - Tool: `get_instruction`
   - Example: `get_instruction()` → understand which emails to act on and what actions to take
   - Purpose: Know the exact email subject, sender, and required operation

2. **Observe the inbox**
   - Tool: `get_observation`, `get_dom_elements`
   - Example: `get_observation()` → see email subjects, senders, and available buttons
   - Purpose: Find the target email(s) in the inbox

3. **Locate the target email**
   - Tool: `get_dom_elements`
   - Example: Look for elements whose text matches the email subject or sender
   - Purpose: Get the EGTS ref of the target email row or checkbox

4. **Select the email** (click to open or check its checkbox)
   - Tool: `click_element`
   - Example: `click_element(ref=5)` → select the email
   - Purpose: Choose the email for further action

5. **Scroll if the target email is not visible**
   - Tool: `scroll_page`
   - Example: `scroll_page(direction="down", amount=200)` → reveal more emails
   - Purpose: Access emails below the fold

6. **Execute the required operation**
   - Tool: `click_element` or `type_text`
   - Example: `click_element(ref=12)` — click Delete; or `type_text(ref=8, text="recipient@example.com")` — fill forward address
   - Purpose: Perform delete/forward/reply/star

7. **Verify the operation completed**
   - Tool: `get_observation`
   - Example: `get_observation()` → confirm the email was deleted, forwarded, etc.
   - Purpose: Ensure the operation succeeded

## Tools Involved
- `get_instruction` — email operation goal
- `get_observation` — inbox view
- `get_dom_elements` — find email and button refs
- `click_element` — select emails, click action buttons
- `type_text` — fill forward/recipient addresses
- `scroll_page` — reveal more emails

## Tips
- Email subjects and senders in the instruction may be paraphrased — look for partial matches
- For forward tasks: type the recipient address exactly as specified
- Star and important markers are typically toggle buttons near each email
- Some email tasks require multiple operations on different emails
- Use `scroll_page("bottom")` to quickly see all emails if the inbox is long
- Re-observe after each operation to confirm the inbox state updated
