# MCPMark Playwright Skill Taxonomy

This skill set is anchored to the actual MCPMark Playwright task families, then expanded with realistic adjacent application workflows when the benchmark task count is too small for skill-guided exploration.

The count is not forced to match benchmark task count. It should satisfy both:

- enough diversity for `skills_max` sampling inside a single-domain episode
- clear professional workflow boundaries grounded in the domain's tools and state space

## Domain Counts

- `eval_web`: 4 skills from 2 standard tasks plus adjacent web-app workflows
  - table-to-CSV extraction
  - auth form plus Turnstile-style challenge
  - generic form state validation
  - DOM/visual/console/network diagnostic audit
- `web_search`: 4 skills from 2 standard tasks plus adjacent research workflows
  - public profile fact research
  - research-paper section extraction
  - multi-source fact verification
  - source/citation audit
- `reddit`: 6 skills for 7 Postmill task families
  - account/session setup
  - forum listing metrics
  - search/sort/pagination/comment mining
  - exact report post composition
  - forum/wiki/community creation
  - voting/settings engagement
- `shopping`: 6 skills for 7 storefront task families
  - product search/filter/sort
  - product detail attributes and reviews
  - comparison list workflows
  - cart quantity/subtotal workflows
  - checkout shipping form workflow
  - multi-category/budget optimization
- `shopping_admin`: 7 skills for 7 Magento Admin task families
  - login/navigation baseline
  - dashboard KPI/widget analysis
  - product catalog grid analysis
  - sales orders grid analysis
  - marketing search terms/promotions/newsletter
  - customer segmentation/record creation
  - store tax/order-status configuration analysis

## Design Rule

Each exploration episode enters one domain state space. Skills are therefore domain-specific and should only be sampled for the active `selected_domain`. Cross-cutting browser grounding belongs in world prompts, hard filters, and the workflow steps inside each domain skill, not in a separate sampled `common` skill.

Small domains such as `eval_web` and `web_search` may have more skills than current benchmark tasks when the extra skills are credible adjacent workflows for the same state/tool space. This keeps skill-guided exploration diverse without inventing unrelated behavior.
