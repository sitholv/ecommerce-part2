# Bay Market — eCommerce Part 1

Vusi Sithole · VS26060020556

## Clone, install and create MariaDB

Start by cloning the personal portfolio project:

```bash
git clone https://github.com/sitholv/ecommerce-part1.git
cd ecommerce-part1
python3 -m venv .venv
source .venv/bin/activate
sudo apt-get install python3-dev build-essential pkg-config default-libmysqlclient-dev
python -m pip install -r requirements.txt
mariadb -u root -p
```

The apt command is for Ubuntu/WSL. On Windows, activate the environment with
`.venv\Scripts\Activate.ps1`. requirements.txt is beside manage.py.

Before running migrations, enter this SQL in the MariaDB prompt. Replace
CHANGE_THIS_PASSWORD with your own password and keep it out of Git:

```sql
CREATE DATABASE commerce_part1 CHARACTER SET utf8mb4;
CREATE USER 'commerce'@'localhost' IDENTIFIED BY 'CHANGE_THIS_PASSWORD';
GRANT ALL PRIVILEGES ON commerce_part1.* TO 'commerce'@'localhost';
GRANT ALL PRIVILEGES ON test_commerce_part1.* TO 'commerce'@'localhost';
EXIT;
```

If commerce already exists, use its existing password rather than creating
it again. Use a dedicated account on a shared database server.

Back in the shell, match these values to your database and password:

```bash
export DB_NAME=commerce_part1
export DB_USER=commerce
export DB_PASSWORD='YOUR_MATCHING_LOCAL_PASSWORD'
export DB_HOST=127.0.0.1
export DB_PORT=3306
python manage.py migrate
python manage.py runserver 127.0.0.1:8006
```

PowerShell uses `$env:DB_PASSWORD="your-local-password"` and the same syntax
for the other environment variables. Settings do not automatically load .env.
MariaDB is now the default database; no SQLite fallback is enabled.

The optional Part 1 compose.yaml starts an isolated WSL MariaDB for both
parts. Export DB_PASSWORD and DB_ROOT_PASSWORD, run
`docker compose up -d --wait database`, then use DB_PORT=33318 and the matching
DB_NAME. It has its own persistent volume; never delete it to run tests.

## Corrections after review

The cart removes deleted product IDs before checkout. My stores and My invoices
provide owner-scoped navigation and history. Views enforce Django model
permissions as well as roles and ownership. Review verification uses an Exists
annotation, and navigation roles are loaded once per request. Quantity controls
use current stock bounds; sold-out products cannot be added.

EMAIL_BACKEND explicitly selects the console backend. Django 6.1 converts it
to the default mailer; defining MAILERS alongside it is rejected. Both invoice
and reset messages use DEFAULT_FROM_EMAIL. Regression tests actually generate
both kinds of console message. Console email does not deliver real email.

Run `python manage.py test shop` with MariaDB running. Tests use the separate
test_commerce_part1 database, never the development database.

## Run locally

Use Python 3.12 or newer. From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8006
```

Open http://127.0.0.1:8006/. Register a vendor to create stores and products;
register a separate buyer to add products to the cart, check out and review
purchases. No sample accounts, passwords, products or database are included.
MariaDB is the database used for this task. Migrations are included.

Checkout records a purchase; it does not process a card payment. All prices are
South African rand. Order lines preserve the purchased name and price after
listing edits/deletion. Reviews are marked verified from actual order lines,
not from a user-entered checkbox. Vendors cannot change another vendor's stock.

## Email and password reset

The development mail backend prints invoice and reset messages in the server
terminal. It does not deliver real email. Copy the reset link from that output;
it expires after 15 minutes and can only be used once. The browser gives the
same reset-request response for known and unknown addresses.

If invoice delivery fails, the saved order remains available and its delivery
flag stays false. After fixing the configured mail backend, run
`python manage.py retry_invoices` to retry unsent invoices. SMTP delivery is not
an exactly-once protocol across a process crash.

## Code guide

shop/models.py describes the records, field limits and database constraints.
shop/forms.py defines the fields a user may submit. shop/views.py documents
each screen's HTTP methods, template context, redirect and access checks.
shop/services.py handles checkout and reset transactions independently of HTML.

The comments explain decisions such as keeping invoice snapshots, checking
ownership on the server and retaining checkout keys for repeated submissions.
Tests explain the failure each scenario protects against, including CSRF,
stored script content and invalid quantities. Django's test client normally
skips CSRF checking, so the security test explicitly enables it.

## Verify

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test shop
```

Tests include checkout rollback, stock limits, repeat submissions, ownership,
private invoices, purchase verification, CSRF, escaping and reset-token expiry.
The task's planning documents are in ../Planning/. Research answers are supplied
as ../research_answers.pdf.

## Deployment boundary

These are local development settings. Before public deployment, supply a secret
key with DJANGO_SECRET_KEY, disable DEBUG, configure allowed hosts and HTTPS,
set a real mail backend and add login/reset rate limiting. Do not commit local
databases, virtual environments, caches, credentials or collected static files.
