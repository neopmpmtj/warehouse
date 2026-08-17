# CentCompras — Central Warehouse

A Django web application for a company with a **central warehouse** and **satellite branches**. Branch staff browse the product catalogue from a phone browser and will eventually place orders against central stock — including in areas with poor mobile coverage.

This repository is an early-stage MVP built incrementally: one concept per phase, with clear separation of responsibilities and no unnecessary frameworks.

---

## Project status (handoff)

*Last updated: August 2026 — read this section first when resuming work.*

### Where we stand

The **catalogue module is complete** for the current MVP scope: global products, warehouse-staff management with audit trail, branch read-only browsing (online + offline), and local dev seed data. The **next business phase is orders** — nothing in `orders/` exists yet.

### Completed

| Phase | Status | Notes |
|-------|--------|-------|
| **Product catalogue MVP** | Done | Model, API, offline HTML/JS, Service Worker, IndexedDB — see [`products/README.md`](products/README.md) |
| **Auth & tenancy foundation** | Done | `accounts` (email login), `branches` (Branch, BranchMembership, roles, middleware, picker) |
| **Login-protected catalogue** | Done | `/` and `/api/products/` require session; API returns 401 when logged out |
| **Centralized logging** | Done | `logging_utils` → rotating files in `logs/` |
| **Catalog management & audit** | Done | `Product` lifecycle fields, `ProductChangeLog`, soft delete, staff admin via `products/services.py` |
| **Catalog polish** | Done | `catalog_updated_at` in API + UI; duplicate `internal_code` validation; optional audit `reason`; 7 tests in `products/tests.py` |
| **Dev seed script** | Done | [`scripts/seed_dev_data.sh`](scripts/seed_dev_data.sh) — branches, branch users, **warehouse user**, sample products |
| **Project setup docs** | Done | Root README, `requirements.txt`, `config/settings.example.py`, `AGENTS.md`, `.cursor/` rules |

**Design choices locked in for later phases:**

- `Product` catalogue is **global** (central warehouse) — no `branch_id` on products.
- Orders (future) will be **branch-scoped** with `branch` + `created_by` FKs.
- Dev login: email + password. Production: **Google OAuth** (not implemented yet).
- Users are provisioned in admin or seed script — no public signup.
- **Catalog mutations** = warehouse staff (`is_staff`) only. **Branch roles** = order permissions (future), not catalogue edit.

### User roles (important — practice with these)

| User type | Example (after seed) | Can do today |
|-----------|----------------------|--------------|
| **Warehouse staff** | `warehouse@centcompras.dev` | Add/edit/deactivate products in `/admin/products/`; audit log |
| **Branch admin** | `admin.lisbon@centcompras.dev` | Log in, browse catalogue at `/` (read-only); future: orders in their branch |
| **Branch manager / user** | (create in admin) | Same browse access; different order permissions later |
| **Django superuser** | from `createsuperuser` | Site admin: users, branches, memberships — not the same as warehouse or branch admin unless you grant `is_staff` / memberships |

After `./scripts/seed_dev_data.sh`, all seeded users share password **`devpass123`**.

### Not started / pending

| Area | Priority | Notes |
|------|----------|-------|
| **Orders workflow** | **Next** | Model, API, cart, offline queue, idempotent sync — see [`docs/warehouse-tenancy-setup.md`](docs/warehouse-tenancy-setup.md) §6–7 |
| **Order business rules** | Before coding orders | Multi-line cart vs single line; stock decrement timing; cancel/edit policy — agree in design session first |
| **Tests (accounts/branches)** | Later | `accounts/tests.py`, `branches/tests.py` still stubs; `products/tests.py` has 7 catalog tests |
| **Integration tests** | Later | Full auth → branch middleware → catalogue API → offline flow |
| **Google OAuth** | Production | `django-allauth` or similar |
| **Public signup / password reset** | Later | |
| **Branch switcher in catalogue** | Later | Multi-branch users pick at login only; no in-app switch |
| **Production deployment** | Later | HTTPS, env secrets, PWA manifest |
| **Catalog extras (deferred)** | Later | Categories, LLM/vector search on `description`, bulk import, plain HTML warehouse UI |

### Recommended next session

1. Read this section and [User roles](#user-roles-important--practice-with-these) above.
2. Fresh environment: `python manage.py migrate` then `./scripts/seed_dev_data.sh`.
3. Practice: warehouse user → catalog admin; branch user → `/` catalogue; deactivate a product → confirm it disappears from branch API.
4. Read [`docs/warehouse-tenancy-setup.md`](docs/warehouse-tenancy-setup.md) §6–7 and **agree order business rules** before implementing `orders/`.
5. Implement **orders** incrementally: model → services → permissions → API → UI → offline queue.

### Key files (catalog — current module)

```text
products/models.py           Product, ProductChangeLog
products/services.py         create/update/deactivate/reactivate, get_products, get_catalog_updated_at
products/permissions.py      can_manage_catalog (is_staff)
products/admin.py            staff-only product admin + audit inline
products/views.py              GET /api/products/ (active only + catalog_updated_at)
products/tests.py              7 tests — run: python manage.py test products
branches/management/commands/seed_dev_data.py
scripts/seed_dev_data.sh       wrapper: migrate + seed
```

Migrations: `products/0001_initial.py`, `products/0002_productchangelog_reason.py`. Run `migrate` after pull if schema changed.

### Development philosophy

One concept per phase. Reusable `services.py` layer. Plain Django + plain JavaScript. Do not dump a finished application in one step. See [`products/products_docs/aux_instructions.md`](products/products_docs/aux_instructions.md).

---

## Business scenario

- A central warehouse holds the master product catalogue and stock levels.
- Branch users access a lightweight web app (plain HTML + JavaScript) from their phones.
- Users may travel through areas with little or no mobile data, so the client must work **offline** for catalogue browsing (and, in a future phase, for queuing orders).
- PostgreSQL on the server is the **source of truth**. The browser's IndexedDB is a **read-only local cache** of the last successfully downloaded catalogue.

Warehouse staff manage the catalogue in Django admin (`is_staff` users). Branch phone users have **read-only** access via the API and offline cache. The CLI (`add_product`) remains for dev/bootstrap only.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Backend | Python, Django 6.1 |
| Database | PostgreSQL (`centcompras_db`) |
| Frontend | Plain HTML, plain JavaScript |
| Offline | Service Worker (app shell), IndexedDB (catalogue data) |
| Logging | `logging_utils` — console + rotating files in `logs/` |

No React, Vue, or similar frontend framework.

---

## What works today

### Authentication and tenancy

- Custom `User` model (`accounts`) — email login, no username field
- Session login/logout at `/accounts/login/` and `/accounts/logout/`
- `Branch` and `BranchMembership` models (`branches`) — roles per branch: Admin, Manager, User
- Active branch stored in session; branch picker when user belongs to multiple branches
- Permission helpers in `branches/permissions.py` (ready for orders)
- Django admin for users, branches, and memberships
- Catalogue requires login; API returns 401 when unauthenticated

Production will use Google OAuth (not implemented in dev — email/password login only).

### Product catalogue (server)

- `Product` model: optional `internal_code`, `description`, `stock` (decimal), `price` (USD), `is_active` (soft delete), timestamps.
- `ProductChangeLog` — immutable audit trail (user, action, field diffs).
- Service layer in [`products/services.py`](products/services.py): `create_product`, `update_product`, `deactivate_product`, `reactivate_product`, `get_products` (active only by default).
- Warehouse staff manage products in `/admin/` (`products/permissions.py` — `is_staff` only).
- Dev/bootstrap CLI:

  ```bash
  python manage.py add_product "Cement 50kg" 100 12.95
  python manage.py add_product "Steel Pipe" 50 8.75 --internal-code PIPE-20
  ```

- JSON API (authenticated, **active products only**):

  ```text
  GET /api/products/
  ```

  Response includes `catalog_updated_at` (ISO timestamp of the latest active product change) for offline stale-catalogue messaging.

- `ProductChangeLog.reason` — optional staff note on create/update/deactivate/reactivate.
- Duplicate non-empty `internal_code` values are rejected with a clear validation error in admin and services.
- Tests in [`products/tests.py`](products/tests.py) cover service diffs, active filtering, duplicate codes, and API metadata.

### Product catalogue (browser)

- Product list page at `/` (login required).
- Fetches catalogue from the API when online, saves to IndexedDB, renders a table.
- On API failure, falls back to the last cached catalogue in IndexedDB.
- Service Worker caches the application shell so the page and scripts load offline.
- Retries when connectivity returns (`online` event) and every 30 seconds while the app is open.

### URL layout

| Path | Purpose |
|------|---------|
| `/` | Product list page (login required) |
| `/accounts/login/` | Email + password login |
| `/accounts/logout/` | Log out |
| `/branches/select/` | Choose active branch (multi-branch users) |
| `/branches/no-access/` | Shown when user has no branch membership |
| `/api/products/` | Catalogue JSON API (login required) |
| `/service-worker.js` | Service Worker (served from root for correct scope) |
| `/admin/` | Django admin |

---

## Project structure

```text
warehouse/
├── manage.py
├── requirements.txt
├── config/
│   ├── settings.example.py   # copy to settings.py locally
│   ├── urls.py
│   └── ...
├── accounts/                 # custom User, login/logout
├── branches/                 # Branch, BranchMembership, active branch middleware
├── logging_utils/            # centralized logging (console + logs/)
├── AGENTS.md                 # Cursor agent instructions
├── .cursor/                  # Cursor rules and commands
├── docs/
│   └── warehouse-tenancy-setup.md
└── products/                 # catalogue app
    ├── models.py
    ├── services.py
    ├── views.py
    └── ...
```

The `products/README.md` file is a step-by-step record of how the catalogue and offline layer were built.

---

## Setup

First-time setup from a fresh clone. Run all commands from the project root (`warehouse/`).

### 1. Virtual environment and dependencies

```bash
cd warehouse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. PostgreSQL

The app expects database `centcompras_db` and user `postgres` (local dev). Adjust in `config/settings.py` if your setup differs.

Enter PostgreSQL as the `postgres` system user:

```bash
sudo -u postgres psql
```

Create the database:

```sql
CREATE DATABASE centcompras_db;
```

If you need to set or reset the `postgres` user password (must match `config/settings.py`):

```sql
ALTER USER postgres WITH PASSWORD 'your_password_here';
\q
```

### 3. Django settings

`config/settings.py` is gitignored (may contain credentials). Copy the example and edit it:

```bash
cp config/settings.example.py config/settings.py
```

Edit `config/settings.py` — set your real database password:

```python
DATABASES = {
    "default": {
        ...
        "PASSWORD": "your_actual_password",  # same as postgres user above
        ...
    }
}
```

### 4. Migrate and create site admin

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py createsuperuser   # prompts for email + password (not username)
```

`createsuperuser` creates a **site admin** for `/admin/`. That user can manage branches and users but **cannot browse the catalogue** until you also add a `BranchMembership` (step 5).

### 5. Seed test data

**Quick seed (recommended for local learning):**

```bash
chmod +x scripts/seed_dev_data.sh   # first time only
./scripts/seed_dev_data.sh
```

This creates:

| Item | Details |
|------|---------|
| **Branches** | Lisbonbranch, portobranch, vilarealbranch |
| **Branch users** | `admin.lisbon@…`, `admin.porto@…`, `admin.vilareal@…` — **branch admin** role in their branch |
| **Warehouse staff** | `warehouse@centcompras.dev` — manages **catalog** in `/admin/products/` (`is_staff`) |
| **Products** | 3 sample items via `products/services.py` |
| **Password** | `devpass123` for all seeded users (override with `--password`) |

Re-running the script is safe (idempotent). Options: `--skip-products`, `--skip-warehouse`.

**Important:** branch **admin** role is for future **order** permissions per branch. **Catalogue** add/edit/deactivate is **warehouse staff only** (`is_staff`), not branch role.

**Manual seed (via `/admin/`)** — if you prefer to practice admin UI:

Start the dev server:

```bash
python manage.py runserver
```

Open `http://localhost:8000/admin/` and log in with the superuser.

Create records in this order:

| Step | Admin model | What to do |
|------|-------------|------------|
| 1 | **Branches** | Add 2–3 branches (e.g. Lisbon, Porto) |
| 2 | **Users** | Add branch users (email + password) — separate from superuser for realistic testing |
| 3 | **Branch memberships** | Link each user to a branch with a role (admin, manager, or user) |

**Notes:**

- A user with **no** branch membership can log in but sees the “no branch access” page.
- To test the branch picker, give **one user** memberships in **two** branches.

### 6. Add sample products

Products are managed in **`/admin/products/`** by warehouse staff (`is_staff`), or created by the seed script / CLI:

```bash
./scripts/seed_dev_data.sh          # recommended — includes 3 products
python manage.py add_product "Cement 50kg" 100 12.95
```

### 7. Test the application

1. Open `http://localhost:8000/` — you should be redirected to login.
2. Log in as a **branch user** (with at least one membership).
3. One branch → catalogue loads. Multiple branches → branch picker, then catalogue.
4. API (same browser session): `http://localhost:8000/api/products/`

Use **one hostname** consistently (`localhost` **or** `127.0.0.1`, not both) — Service Workers are origin-specific.

### 8. Logging

Application logs are written automatically to `logs/` (gitignored) when the server runs:

| File | Logger name |
|------|-------------|
| `logs/centcompras.log` | General |
| `logs/accounts.log` | `centcompras.accounts` |
| `logs/branches.log` | `centcompras.branches` |
| `logs/products.log` | `centcompras.products` |
| `logs/django.log` | `centcompras.django` (HTTP requests) |

In Python code:

```python
from logging_utils import get_logger

logger = get_logger("centcompras.products")
logger.info("Something happened")
```

Configuration: `logging_utils/logging_config.py`.

### Quick reference (daily dev)

```bash
source .venv/bin/activate
python manage.py runserver
```

First-time or reset DB: steps 1–4 above, then `./scripts/seed_dev_data.sh`.

Practice logins (after seed): `warehouse@centcompras.dev` (catalog admin), `admin.lisbon@centcompras.dev` (branch catalogue), password `devpass123`.

---

## Architecture (current)

```text
PostgreSQL
    ↑
User, Branch, BranchMembership, Product
    ↑
services.py / permissions.py
    ↑
views (login required) → API + HTML
    ↑
product_list.js → IndexedDB

Service Worker → caches HTML + JS (app shell, offline page load)
```

---

## Further reading

- **Start here:** [Project status (handoff)](#project-status-handoff) in this file
- [`products/README.md`](products/README.md) — catalogue MVP build log, offline behaviour, manual testing checklist
- [`docs/warehouse-tenancy-setup.md`](docs/warehouse-tenancy-setup.md) — tenancy design; **§6–7** for Order model (next phase)
- [`AGENTS.md`](AGENTS.md) — concise instructions for AI agents in Cursor
- [`products/products_docs/aux_instructions.md`](products/products_docs/aux_instructions.md) — incremental development pace

---

## What is explicitly not built yet

The following do **not** exist today. The [Project status](#project-status-handoff) table above is the canonical handoff reference.

### Business features

- `orders` app — create, list, edit, delete orders
- Shopping cart
- Customers
- Offline order queue in IndexedDB
- Order synchronization when connectivity returns
- Idempotent order submission (client-side order IDs on retry)
- Stock reservation or conflict handling
- Product creation or editing from branch phone UI or public web forms
- In-app branch switcher (only login-time picker for multi-branch users)

### Auth & production

- Google OAuth (production login — dev uses email + password)
- Public signup
- Password reset flow

### Quality & operations

- **Unit tests** — `products/tests.py` has catalog tests (7); `accounts/tests.py` and `branches/tests.py` still stubs
- **Integration tests** — not started
- Production deployment and HTTPS
- PWA manifest / install prompt

### Planned next major phase

**Ordering workflow:** branch users create orders online or queue them offline, then sync to the central warehouse with duplicate-safe retries. Builds on existing `Branch`, `BranchMembership`, `permissions.py`, and `request.active_branch`.
