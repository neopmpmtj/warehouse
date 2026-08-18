---
name: Console column sorting
overview: Add client-side, single-column sort on the staff product console table. Click a header to toggle ascending/descending; reload returns to id order. Empty values sort as smallest.
todos:
  - id: html-headers
    content: Mark sortable th with data-sort; wrap labels for i18n + indicator
    status: completed
  - id: js-sort
    content: Add sort state, comparators, header click, aria-sort, apply in renderTable
    status: completed
  - id: css-i18n
    content: Clickable header styles + EN/pt-PT aria-label strings
    status: completed
isProject: false
---

# Console column sorting

Client-side only. Filters stay as they are; sort runs on the already-filtered list in [`products/static/products/js/console.js`](products/static/products/js/console.js). No API or `services.py` changes.

## Behaviour (locked)

- One column at a time. Checkbox and Actions stay unsortable.
- First click on a column: **ascending**. Click again: **descending**. Click a different column: that column starts at ascending.
- No persistence. Reload (and first paint) keeps today’s order: product `id`.
- Empty internal codes and products with no suppliers sort as the smallest value (first when ascending, last when descending). Do **not** use the displayed “—” or translated “None” as the sort key.
- Tie-break on `id` so the order is stable.
- Changing language re-renders and re-sorts using the new unit/status labels.

## Sort keys

| Column | Compare |
|--------|---------|
| Code | `internal_code` string (empty if unset) |
| Description | `description` |
| Family | `family.name` |
| Stock, Reorder, Price | numeric (`Number(...)`) |
| Unit | displayed label via `unitLabel()` |
| Suppliers | joined supplier names as shown; empty string if none |
| Status | displayed Active/Inactive label (`t("active")` / `t("inactive")`) |

Text compares with `localeCompare` using `currentLang()` (`en` / `pt-PT`).

## UI

In [`products/templates/products/product_console.html`](products/templates/products/product_console.html), mark sortable headers with `data-sort="internal_code"` (etc.). Keep `data-i18n` on a label span so existing i18n still works.

Click the `<th>` (or a button inside it) to sort. Show a compact indicator on the active column only (`▲` / `▼`). Set `aria-sort="ascending"` / `"descending"` / `"none"`. Add i18n strings in [`products/static/products/js/console_i18n.js`](products/static/products/js/console_i18n.js) for `aria-label` (e.g. “Sort by description”).

In [`products/static/products/css/console.css`](products/static/products/css/console.css), make sortable headers look clickable (`cursor: pointer`, no underline, indicator muted until active). Sticky header background stays as it is.

## JS shape

Add to `state`:

```js
sortKey: null,   // data-sort value, or null = id order
sortDir: "asc",
```

New helpers: `sortValue(product, key)`, `sortedProducts(rows)`, `updateSortHeaders()`. `renderTable()` uses `sortedProducts(filteredProducts())`. Header clicks update `state.sortKey` / `state.sortDir` and call `renderTable()`. `setLanguage` already re-renders; no extra hook.

Select-all can keep using `filteredProducts()` (same set, order does not matter).
