---
name: Procurement PO receipts
overview: Current cost/sell/wholesale stay as columns on Product. Purchase-price history for inflation is each approved PO line (frozen cost, supplier, qty, date), not a prices FK. Superuser approves; receipts increment stock.
todos:
  - id: product-prices
    content: Two extra columns on Product (cost, wholesale) as current list values; keep price as sell. Prices drawer on /manage/products/. Product form not given extra money fields.
    status: completed
  - id: stock-ledger
    content: StockMovement + apply_stock_change; lock Product.stock (create always 0); console/admin/CLI/seed/tests follow
    status: completed
  - id: po-models-services
    content: "Procurement app: draft → pending_approval → superuser approve (freeze unit_cost) → receive. Approved lines are purchase-price history."
    status: completed
  - id: po-staff-ui
    content: Staff page /manage/procurement/; product/supplier dropdowns; qty typed; cost read-only; Products|Purchases nav
    status: completed
  - id: handoff-docs
    content: README, AGENTS.md, settings.example; warehouse@ cannot approve (needs superuser)
    status: completed
isProject: false
---

# Procurement: PO then receipt

## What this slice does

Warehouse staff raise a **purchase order** to an existing supplier, a **superuser approves** it, then a **goods receipt** increases on-hand stock. Staff never type money on the PO: they pick product and supplier from dropdowns and type **quantity** only.

## Current prices vs purchase history

Two jobs; do not mix them in a Product → Price foreign key.

**Current catalogue prices** (Prices drawer) — **columns on [`Product`](products/models.py):**

- `cost` (new), `wholesale` (new), `price` (existing = sell)
- Default `0`. Same Decimal type as today.
- Product create/edit form stays quiet: **do not** add cost/wholesale there. Toolbar **Prices** drawer (same pattern as Families / Suppliers). Grid keeps one Price column (sell). Stock on the product form becomes **read-only**.

**Purchase-price history** (inflation / metrics later) — **approved [`PurchaseOrderLine`](procurement/models.py) rows:**

- product, supplier (PO header), frozen `unit_cost`, qty, `approved_at` / `received_at`
- History is per supplier even without a supplier cost list
- Freeze **at approve**, not when the line is first added. After approve, changing `Product.cost` must not rewrite the line
- No metrics/charts UI in this slice; the data is the lines

`ProductChangeLog` still records list-price edits (who changed cost/sell/wholesale). That is not the purchase series.

## Flow

```mermaid
flowchart LR
  subgraph master [Catalogue]
    Product
    Supplier
  end
  subgraph thisSlice [This slice]
    PO[PurchaseOrder]
    POLine[PO line]
    GR[GoodsReceipt]
    Move[StockMovement]
  end
  Product -->|"current cost"| POLine
  Supplier --> PO
  PO --> POLine
  PO -->|"superuser approve freezes cost"| GR
  GR --> Move
  Move --> Product
```

- **draft → submit (pending_approval) → superuser approve → receive**
- Any `is_staff` may draft and submit. Only `is_superuser` may approve
- Seeded `warehouse@centcompras.dev` cannot approve (staff, not superuser). Practice with the site superuser
- Partial receipts allowed; no over-receive; no receipt void
- New products still start inactive (Genesis) with stock **0**
- `create_product` always stock 0; `apply_stock_change` in [`products/services.py`](products/services.py) is the only quantity write

## Models

**products:** `StockMovement` (product, signed qty, reason, source_type/source_id, user). Remove `stock` from `UPDATABLE_FIELDS`.

**procurement:**

- `PurchaseOrder`: supplier, status (`draft` / `pending_approval` / `approved` / `cancelled`), created_by, approved_by, notes
- `PurchaseOrderLine`: product, quantity_ordered, unit_cost (snapshot), unique per PO+product
- `GoodsReceipt` + `GoodsReceiptLine` against outstanding qty

Cancel: draft, pending_approval, or approved with zero receipts.

## UI

- [`/manage/procurement/`](procurement/web_urls.py) — list + drawer; EN/pt-PT; reuse [`console.css`](products/static/products/css/console.css)
- Nav on both staff pages: Products | Purchases
- PO: product dropdown (code + description), supplier dropdown, qty typed, cost shown read-only
- Staff: Save, Submit for approval, Cancel. Superuser: Approve, then Receive

## Out of this slice

Per-supplier list cost, inflation charts, picking sell/wholesale on a PO, extra approval role flag, over-receive, invoices, branch orders, phone catalogue UX.
