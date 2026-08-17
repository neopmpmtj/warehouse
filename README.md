# CentCompras — Central Warehouse

A Django web application for a company with a **central warehouse** and **satellite branches**. Branch staff browse the product catalogue from a phone browser and will eventually place orders against central stock — including in areas with poor mobile coverage.

This repository is an early-stage MVP built incrementally: one concept per phase, with clear separation of responsibilities and no unnecessary frameworks.

---

## Business scenario

- A central warehouse holds the master product catalogue and stock levels.
- Branch users access a lightweight web app (plain HTML + JavaScript) from their phones.
- Users may travel through areas with little or no mobile data, so the client must work **offline** for catalogue browsing (and, in a future phase, for queuing orders).
- PostgreSQL on the server is the **source of truth**. The browser's IndexedDB is a **read-only local cache** of the last successfully downloaded catalogue.

Products are added only via a Django management command — not from the phone or a public web form.

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

- `Product` model: `description`, `stock` (decimal, supports fractions), `price` (USD, `DecimalField`).
- Reusable service layer in `products/services.py` (`create_product`, `get_products`).
- CLI command to insert products:

  ```bash
  python manage.py add_product "Cement 50kg" 100 12.95
  ```

- JSON API (authenticated):

  ```text
  GET /api/products/
  ```

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

### 5. Seed test data (via `/admin/`)

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

### 6. Add sample products (CLI)

Products are not created in admin or on the phone — only via CLI:

```bash
source .venv/bin/activate
python manage.py add_product "Cement 50kg" 100 12.95
python manage.py add_product "Steel Pipe 20mm" 50 8.75
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

First-time only: steps 1–4 above, then admin seed (step 5), then CLI products (step 6).

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

- [`products/README.md`](products/README.md) — detailed catalogue MVP documentation, offline behaviour, and testing checklist.
- [`docs/warehouse-tenancy-setup.md`](docs/warehouse-tenancy-setup.md) — tenancy design reference (orders section is next phase).

---

## What is explicitly not built yet

- Google OAuth (production login — dev uses email + password)
- `Order` model and order views/API
- Customers
- Shopping cart
- Offline order queue in IndexedDB
- Order synchronization when connectivity returns
- Idempotent order submission (client-side order IDs to prevent duplicates on retry)
- Product editing or creation from the phone or public web UI
- Django admin registration for products
- Stock reservation or conflict handling
- Production deployment and HTTPS
- PWA manifest / install prompt

The planned next major phase is the **ordering workflow**: branch users create orders online or queue them offline, then sync to the central warehouse with duplicate-safe retries.
