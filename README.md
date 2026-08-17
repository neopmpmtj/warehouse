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

No React, Vue, or similar frontend framework.

---

## What works today

### Product catalogue (server)

- `Product` model: `description`, `stock` (decimal, supports fractions), `price` (USD, `DecimalField`).
- Reusable service layer in `products/services.py` (`create_product`, `get_products`).
- CLI command to insert products:

  ```bash
  python manage.py add_product "Cement 50kg" 100 12.95
  ```

- JSON API:

  ```text
  GET /api/products/
  ```

### Product catalogue (browser)

- Product list page at `/`.
- Fetches catalogue from the API when online, saves to IndexedDB, renders a table.
- On API failure, falls back to the last cached catalogue in IndexedDB.
- Service Worker caches the application shell so the page and scripts load offline.
- Retries when connectivity returns (`online` event) and every 30 seconds while the app is open.

### URL layout

| Path | Purpose |
|------|---------|
| `/` | Product list page |
| `/api/products/` | Catalogue JSON API |
| `/service-worker.js` | Service Worker (served from root for correct scope) |
| `/admin/` | Django admin (not yet configured for products) |

---

## Project structure

```text
warehouse/
├── manage.py
├── config/                 # Django project (urls, wsgi, asgi)
│   └── settings.py         # gitignored — create locally (see Setup)
├── docs/
│   └── warehouse-tenancy-setup.md   # planned multi-tenancy design notes
└── products/               # catalogue app
    ├── models.py
    ├── services.py
    ├── views.py
    ├── urls.py             # API routes under /api/
    ├── web_urls.py         # page routes
    ├── management/commands/add_product.py
    ├── templates/products/
    ├── static/products/js/
    └── README.md           # detailed build log and implementation notes
```

The `products/README.md` file is a step-by-step record of how the catalogue and offline layer were built. Use it when you need file-level detail, data-flow diagrams, or testing instructions.

---

## Setup

### 1. Virtual environment and dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. PostgreSQL

Create the database (adjust credentials for your environment):

```sql
CREATE DATABASE centcompras_db;
```

### 3. Django settings

`config/settings.py` is gitignored because it may contain database credentials. Create it locally with at least:

- `DATABASES` pointing at `centcompras_db`
- `"products"` in `INSTALLED_APPS`

See `products/README.md` (section 6) for a full example configuration.

### 4. Migrate and run

```bash
python manage.py migrate
python manage.py runserver
```

Open `http://localhost:8000/` (stick to one hostname during testing — Service Workers are origin-specific).

Add sample products:

```bash
python manage.py add_product "Steel Pipe 20mm" 50 8.75
```

---

## Architecture (current)

```text
PostgreSQL
    ↑
Product model
    ↑
services.py
    ↑           ↑
add_product   API view → GET /api/products/
CLI               ↑
            product_list.js
              ↑         ↓
       displayProducts  saveProducts → IndexedDB

Service Worker → caches HTML + JS (app shell, offline page load)
```

---

## Further reading

- [`products/README.md`](products/README.md) — detailed catalogue MVP documentation, offline behaviour, and testing checklist.
- [`docs/warehouse-tenancy-setup.md`](docs/warehouse-tenancy-setup.md) — design notes for future multi-tenancy (branches, roles, orders). **Not implemented yet.**

---

## What is explicitly not built yet

The following do **not** exist in this repository today. Do not assume they are available:

- User authentication (email login, sessions, etc.)
- Branches / multi-tenancy (per-branch data isolation)
- Role-based permissions (Admin, Manager, User per branch)
- Customers
- Orders (create, edit, delete)
- Shopping cart
- Offline order queue in IndexedDB
- Order synchronization when connectivity returns
- Idempotent order submission (client-side order IDs to prevent duplicates on retry)
- Product editing or creation from the phone or public web UI
- Django admin registration for products
- Stock reservation or conflict handling
- Multi-user / cross-branch permission model
- Production deployment and HTTPS
- PWA manifest / install prompt

The planned next major phase is the **ordering workflow**: branch users create orders online or queue them offline, then sync to the central warehouse with duplicate-safe retries.
