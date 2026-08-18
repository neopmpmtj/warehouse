# Procurement (PO → receipt) — session report

**Date:** 18 August 2026  
**App:** CentCompras (central warehouse + satellite branches)  
**Scope of this session:** inbound stock via **purchase orders** and **goods receipts**; product **cost / sell / wholesale** and a **stock ledger** so warehouse staff no longer type quantity on the product row. Staff purchases console at `/manage/procurement/`. Branch **orders** remain the next business phase.

Read this document first if you are resuming work on procurement, stock movements, or the Prices drawer on the product console. The branch phone catalogue at `/` was not changed.

---

## 1. Who this is for

Anyone opening this repository after this session: a future agent, a developer who was not in the conversation, or the same people returning later without the chat history.

The conversation itself will not be available. This file is the handoff for **what was asked, what was decided, what was built, what broke, and what was deliberately left out**.

---

## 2. Business context (as stated in the session)

CentCompras is a **central warehouse** with satellite branches. Branch staff browse a read-only catalogue and will eventually place orders against warehouse stock.

Before this session, **`Product.stock` was typed on the product form** in `/manage/products/`. That was acceptable for early catalogue work but wrong for production logistics: stock should increase when goods **arrive from suppliers**, not when someone edits a product row.

The agreed sequence was:

```text
Warehouse buys from supplier (purchase order)
    → superuser approves (freezes unit cost on each line)
    → goods receipt (partial allowed)
    → Product.stock increases via stock ledger
    → branch orders (later) run against real stock
```

Branch **orders** were explicitly **held** until inbound stock existed. Implementing the tenancy-doc `Order` stub (`item_name`, free-text lines) was forbidden.

Warehouse staff (`is_staff`, seeded `warehouse@centcompras.dev`) draft and submit purchase orders. **Only Django `is_superuser`** may approve them. The seeded warehouse user is staff but **not** superuser — practice approval with `createsuperuser`.

Operators on a PO pick **product** and **supplier** from dropdowns and type **quantity only**. They do **not** type money on the PO; **unit cost** is copied from `Product.cost` and shown read-only. There is **no per-supplier cost table** in this slice.

---

## 3. What already existed before this session

| Area | State |
|------|--------|
| **Catalogue** | Global `Product`, families, suppliers, staff console `/manage/products/`, audit logs, branch read-only API + offline cache |
| **Product prices** | Single `price` field (sell); no `cost` or `wholesale` |
| **Stock** | `Product.stock` editable in console and admin; `create_product` accepted `stock` |
| **Procurement** | Nothing — no `procurement` app, no PO, no receipt |
| **Orders** | Not built (planned next after inbound stock) |
| **Auth / tenancy** | Email login, branches, `ActiveBranchMiddleware`, seed script with warehouse + branch admins |

Staff console patterns were already established: plain Django template + `console.css` + `console.js` + `console_i18n.js`, staff JSON under `/api/manage/…`, mutations only through `services.py`.

---

## 4. Planning decisions (agreed before coding)

These were locked in the “Procurement: PO then receipt” plan and implemented accordingly.

### 4.1 Two jobs for money — do not merge them

| Job | Where it lives | Purpose |
|-----|----------------|---------|
| **Current catalogue prices** | Columns on `Product`: `cost`, `price` (sell), `wholesale` | List prices; edited in **Prices drawer** on `/manage/products/` |
| **Purchase-price history** | Approved `PurchaseOrderLine.unit_cost` (frozen at approve) | Inflation / metrics later; per supplier via PO header |

There is **no** `Product → Price` foreign key. `ProductChangeLog` still records list-price edits (who changed cost/sell/wholesale). That is **not** the purchase-price time series.

### 4.2 PO lifecycle

| Status | Who can act | Notes |
|--------|-------------|-------|
| `draft` | Staff | Edit lines, supplier, notes; submit |
| `pending_approval` | Staff submit; **superuser approve** | Cost refreshed from `Product.cost` on submit |
| `approved` | Staff receive | `unit_cost` frozen at approve; partial receipts OK |
| `cancelled` | Staff | Draft, pending, or approved **with zero receipts** |

- No over-receive. No receipt void in this slice.
- New products still start **inactive** (Genesis) with stock **0**.
- `create_product` always creates stock **0**; `apply_stock_change` is the only quantity write.

### 4.3 Product form vs Prices drawer

- **Do not** add cost/wholesale on the main product create/edit drawer.
- **Stock** on the product form becomes **read-only** with a hint pointing to receipts / Prices drawer.
- Grid keeps one **Price** column (sell).

### 4.4 Explicitly out of scope

Per-supplier list cost, inflation charts, picking sell/wholesale on a PO, extra approval role flag, over-receive, invoices, branch orders, phone catalogue UX, shared page chrome, staff console polish.

---

## 5. Tech stack chosen — and why

Same constraints as the product console session: **Django 6.1**, **PostgreSQL**, **plain HTML + JavaScript**, no React/Vue, no DRF, business logic in `services.py`.

| Layer | Choice | Why |
|-------|--------|-----|
| New app | `procurement` | Inbound stock is not branch orders; keeps `orders` free for the next phase |
| Models | `PurchaseOrder`, `PurchaseOrderLine`, `GoodsReceipt`, `GoodsReceiptLine` | PO → approve → receipt matches warehouse workflow |
| Stock writes | `products.services.apply_stock_change` | Single ledger entry point; receipts call it with `source_type=receipt` |
| Staff API | `procurement/console_views.py` + `JsonResponse` | Same pattern as product console; thin views |
| Authz | Reuse `products.permissions.staff_required` | Catalogue management = `is_staff`; approve = `is_superuser` in service layer |
| Staff UI | `/manage/procurement/` + `procurement.js` + `procurement_i18n.js` | Reuse `products/static/products/css/console.css`; EN / pt-PT; shared `cc-lang` / `cc-theme` |
| Nav | Products \| Purchases on both staff pages | One mental model for warehouse staff |
| Logging | `centcompras.procurement` → `logs/procurement.log` | Matches `logging_utils` pattern |
| Tests | `procurement/tests.py` + updated `products/tests.py` | Service flow, API permissions, stock ledger |

PostgreSQL row locks: `select_for_update(of=("self",))` on `PurchaseOrder` when editing/approving/receiving, so nullable `approved_by` joins do not break `FOR UPDATE` on PostgreSQL.

---

## 6. What was built

### 6.1 Products app changes (same slice)

| Change | Detail |
|--------|--------|
| **Fields** | `Product.cost`, `Product.wholesale` (default 0); `price` = sell |
| **Migration** | `products/0006_product_cost_wholesale_stockmovement.py` |
| **StockMovement** | `product`, signed `quantity`, `reason`, `source_type` (`receipt` / `adjustment` / `order`), `source_id`, `user`, `created_at` |
| **Services** | `apply_stock_change`; `update_product_prices`; `stock` removed from `UPDATABLE_FIELDS`; `create_product` always stock 0 |
| **Console** | Prices toolbar button + drawer; `GET/PATCH /api/manage/products/prices/` |
| **Admin** | `cost`, `wholesale` on form; `stock` readonly |
| **CLI** | `add_product` — `price` positional; optional `--stock` (ledger), `--cost`, `--wholesale` |
| **Seed** | `dev_prices_from_sell()` (cost 60%, wholesale 85% of sell); stock via `apply_stock_change`; backfill cost/wholesale on existing rows when zero |

### 6.2 Procurement models

| Model | Role |
|-------|------|
| `PurchaseOrder` | `supplier`, `status`, `created_by`, `approved_by`, `approved_at`, `notes`, timestamps |
| `PurchaseOrderLine` | `product`, `quantity_ordered`, `unit_cost` (snapshot); unique per PO + product |
| `GoodsReceipt` | Header per receive action on an approved PO |
| `GoodsReceiptLine` | `po_line`, `quantity_received` |

FK policy: `PROTECT` on supplier, product, PO on receipt; `CASCADE` on PO lines when PO lines are replaced in draft.

### 6.3 Procurement services (`procurement/services.py`)

| Function | Role |
|----------|------|
| `create_purchase_order` | Draft PO for active supplier |
| `set_purchase_order_lines` | Draft/pending only; copies `Product.cost` to `unit_cost`; rejects products with cost ≤ 0 |
| `submit_purchase_order` | Draft → `pending_approval`; refreshes line costs |
| `approve_purchase_order` | Superuser only; freezes `unit_cost`; sets `approved_by` / `approved_at` |
| `cancel_purchase_order` | Rules per status; no cancel if approved + receipts exist |
| `create_goods_receipt` | Approved only; validates outstanding qty; calls `apply_stock_change` per line |
| `get_purchase_orders` | List/detail queryset with prefetch |
| `line_quantity_received` / `line_quantity_outstanding` | Helpers for UI and validation |

All mutating functions use `@transaction.atomic`.

### 6.4 Staff JSON API (mounted under `/api/`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/manage/purchase-orders/` | List orders + capability flags per user |
| POST | `/api/manage/purchase-orders/` | Create PO (`supplier_id`, optional `notes`, optional `lines`) |
| GET/PATCH | `/api/manage/purchase-orders/<id>/` | Detail; PATCH `supplier_id`, `notes`, `lines` when editable |
| POST | `/api/manage/purchase-orders/<id>/submit/` | Draft → pending |
| POST | `/api/manage/purchase-orders/<id>/approve/` | Superuser only |
| POST | `/api/manage/purchase-orders/<id>/cancel/` | Cancel per rules |
| POST | `/api/manage/purchase-orders/<id>/receive/` | Body: `lines: [{ po_line_id, quantity_received }]` |
| GET | `/api/manage/purchase-orders/catalog/` | Active suppliers + products (with `cost`) for dropdowns |

Product staff API addition:

| Method | Path | Purpose |
|--------|------|---------|
| GET/PATCH | `/api/manage/products/prices/` | Bulk list / update cost, sell, wholesale |

### 6.5 Staff pages

| URL | Name | Assets |
|-----|------|--------|
| `/manage/procurement/` | `procurement_console` | `procurement_console.html`, `procurement.js`, `procurement_i18n.js`, shared `console.css`, shared `console_i18n.js` (nav strings) |

Behaviour: status filter, order list, drawer for create/edit, line table (product select, qty, read-only unit cost, received/outstanding), submit / approve / cancel / receive dialog.

### 6.6 Files added (procurement)

| Path | Responsibility |
|------|----------------|
| `procurement/models.py` | PO, lines, receipts |
| `procurement/services.py` | Business rules + stock integration |
| `procurement/console_views.py` | Page + JSON API |
| `procurement/urls.py`, `procurement/web_urls.py` | Routes |
| `procurement/migrations/0001_initial.py` | Schema |
| `procurement/templates/procurement/procurement_console.html` | Page shell |
| `procurement/static/procurement/js/procurement.js` | UI logic |
| `procurement/static/procurement/js/procurement_i18n.js` | EN / pt-PT strings |
| `procurement/tests.py` | Service + API tests |

### 6.7 Config and docs

- `config/settings.example.py` — `"procurement"` in `INSTALLED_APPS`
- `config/urls.py` — include `procurement.urls` and `procurement.web_urls`
- `README.md`, `AGENTS.md`, `.cursor/rules/` — handoff updated; orders marked next phase
- `branches/management/commands/seed_dev_data.py` — cost/wholesale, ledger stock, procurement hints in output

**Local upgrade:** add `"procurement"` to `INSTALLED_APPS` in `config/settings.py` if not already present, then `migrate`.

---

## 7. Data flow (keep this picture)

```text
Prices drawer (/manage/products/)
    → PATCH /api/manage/products/prices/
        → update_product_prices → Product.cost / price / wholesale

Draft PO (/manage/procurement/)
    → POST/PATCH /api/manage/purchase-orders/…
        → procurement/services.py
            → PurchaseOrder + PurchaseOrderLine (unit_cost from Product.cost)

Superuser approve
    → POST …/approve/
        → freeze PurchaseOrderLine.unit_cost  (purchase-price history)

Goods receipt
    → POST …/receive/
        → GoodsReceipt + GoodsReceiptLine
            → apply_stock_change (products/services.py)
                → StockMovement + Product.stock
```

```text
Branch phone catalogue (unchanged)
    → GET /api/products/  (active only; stock/price strings)
        → IndexedDB cache if offline
```

Purchase-price history for analytics is **approved PO lines**, not `ProductChangeLog` price edits.

---

## 8. Bugs and fixes during the session

### 8.1 `select_for_update` with nullable `approved_by`

**Symptom:** Internal Server Error on PO create/update when setting lines — PostgreSQL: `FOR UPDATE cannot be applied to the nullable side of an outer join`.

**Cause:** `_get_order(for_update=True)` used `select_related("approved_by")` with `select_for_update()` on one queryset.

**Fix (first):** Separate lock query — but result was discarded; second query fetched without holding the locked instance (confusing, wasteful).

**Fix (final):** Single queryset with `select_for_update(of=("self",))` — locks only `PurchaseOrder` row; `select_related` on nullable FKs still works.

### 8.2 Procurement JS ↔ API payload mismatches

- Detail GET returns `{ "order": … }` — JS must unwrap.
- Receive body uses `po_line_id` and `quantity_received` (not `line_id` / `quantity`).
- Create POST returns `{ "order": … }` — save flow must read `order.id`.

### 8.3 Product tests and seed after stock ledger

- `create_product` no longer accepts `stock`; tests use `apply_stock_change` in helpers.
- Console API tests removed `stock` from create payloads.
- `get_catalog_updated_at` test uses ledger instead of `update_product(..., stock=…)`.

### 8.4 `deactivate_product` merge accident

Brief bad merge left `deactivate_product` body orphaned after `apply_stock_change` insert — function header restored.

### 8.5 New product drawer missing default reorder

`openDrawer(null)` omitted `field-reorder` default `"0"` — restored.

---

## 9. How to run and practise

```bash
source .venv/bin/activate    # or: .venv/bin/python …
python manage.py migrate
./scripts/seed_dev_data.sh
python manage.py createsuperuser   # for PO approval (optional but recommended)
python manage.py runserver
```

Use **one** host: `http://127.0.0.1:8000` **or** `http://localhost:8000`, not both.

| Who | URL | Expect |
|-----|-----|--------|
| `warehouse@centcompras.dev` | `/manage/products/` | Products; Prices drawer; stock read-only |
| Same | `/manage/procurement/` | Draft PO, submit |
| Same | Approve button | **Hidden / 403** — not superuser |
| Superuser (+ `is_staff` for catalogue) | `/manage/procurement/` | Approve → Receive |
| Superuser | Approve → Receive on PO | `Product.stock` increases; `StockMovement` row |
| Branch user | `/manage/procurement/` | 403 |

Password for seeded users: `devpass123`.

**Practise flow:**

1. Set costs in **Prices** drawer (or rely on seed: cost ≈ 60% of sell).
2. **Purchases** → New PO → pick supplier, add lines (qty only), Save, Submit.
3. Log in as **superuser** → Open PO → Approve.
4. As warehouse staff → Receive (partial qty OK) → confirm stock on product row.

Tests:

```bash
.venv/bin/python manage.py test products procurement
```

---

## 10. i18n and theme

- Procurement page shares `localStorage["cc-lang"]` and `localStorage["cc-theme"]` with the product console.
- Nav strings (`navProducts`, `navPurchases`) live in `console_i18n.js`.
- Procurement-specific strings in `procurement_i18n.js`.
- API errors often English; approve denial uses `code: "approval_forbidden"` for translated UI text.

Staff consoles remain **online-only** (not in Service Worker shell).

---

## 11. User roles (procurement-specific)

| Role | Draft / submit PO | Approve PO | Receive goods | Edit catalogue prices |
|------|-------------------|------------|---------------|------------------------|
| Warehouse staff (`is_staff`) | Yes | No | Yes (on approved PO) | Yes |
| Superuser | Yes (if also staff) | Yes | Yes | Yes (if also staff) |
| Branch user | No | No | No | No |

`is_superuser` without `is_staff` can approve POs but cannot open `/manage/` unless granted staff.

---

## 12. What this session did **not** do

- `orders` app, branch cart, offline order queue.
- Per-supplier cost list, inflation charts, PO line sell/wholesale picker.
- Receipt void, over-receive, extra approval role flag.
- Branch phone catalogue UX; shared page chrome; console polish (history diffs, default filters).
- Integration tests for full auth → branch → catalogue → procurement chain.
- Google OAuth, production deployment.

---

## 13. Suggested next steps

1. **Branch orders** — design business rules (cart shape, stock decrement timing, cancel policy), then implement `orders/` per `docs/warehouse-tenancy-setup.md` (not the `item_name` stub).
2. Optional: sample **approved PO + receipt** in `seed_dev_data` for demo without manual superuser flow.
3. Optional: procurement audit log (who approved, who received) — PO header already stores `created_by`, `approved_by`, `received_by` on receipts.
4. Staff console polish session (shared with product console backlog).
5. `StockMovement.SourceType.ORDER` reserved for when outbound branch orders decrement stock.

---

## 14. Mental model — stock and prices

| Concept | Stored where | Edited how |
|---------|--------------|------------|
| Sell price | `Product.price` | Prices drawer |
| Cost (list) | `Product.cost` | Prices drawer; PO lines copy while draft |
| Wholesale | `Product.wholesale` | Prices drawer |
| Purchase price (history) | `PurchaseOrderLine.unit_cost` after approve | Frozen; not edited on PO after approve |
| On-hand quantity | `Product.stock` | **Only** `apply_stock_change` (receipts, seed, CLI `--stock`) |
| Movement audit | `StockMovement` | Written by `apply_stock_change` |

Changing `Product.cost` after approve does **not** rewrite approved PO lines.

---

## 15. Pointers in the repo

- This file: `docs/procurement-session-2026-08-18.md`
- Plan (reference only; do not edit as handoff): `.cursor/plans/procurement_po_receipts_2256ce9a.plan.md`
- Product console session (UI patterns): `docs/product-console-session-2026-08-18.md`
- Project status: `README.md` → “Project status (handoff)”
- Agent brief: `AGENTS.md`
- Tenancy + order sketch (next phase): `docs/warehouse-tenancy-setup.md`
- Migrations: `products/0006`, `procurement/0001`
