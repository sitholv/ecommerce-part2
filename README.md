# Bay Market — eCommerce Part 2

Vusi Sithole · VS26060020556

## Clone, install and create MariaDB

Start by cloning the personal portfolio project:

```bash
git clone https://github.com/sitholv/ecommerce-part2.git
cd ecommerce-part2
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
CREATE DATABASE commerce_part2 CHARACTER SET utf8mb4;
CREATE USER 'commerce'@'localhost' IDENTIFIED BY 'CHANGE_THIS_PASSWORD';
GRANT ALL PRIVILEGES ON commerce_part2.* TO 'commerce'@'localhost';
GRANT ALL PRIVILEGES ON test_commerce_part2.* TO 'commerce'@'localhost';
EXIT;
```

If commerce already exists, use its existing password rather than creating
it again. Use a dedicated account on a shared database server.

Back in the shell, match these values to your database and password:

```bash
export DB_NAME=commerce_part2
export DB_USER=commerce
export DB_PASSWORD='YOUR_MATCHING_LOCAL_PASSWORD'
export DB_HOST=127.0.0.1
export DB_PORT=3306
python manage.py migrate
python manage.py runserver 127.0.0.1:8007
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
test_commerce_part2 database, never the development database.

This project retains Part 1's buyer/vendor marketplace and adds an authenticated
JSON API and a live r/Python feed. Use Python 3.12 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8007
```

Register buyer and vendor accounts through the browser. Email uses the console
backend for local demonstration, not real delivery. The cart records purchases
without charging cards. Retry failed invoices with
`python manage.py retry_invoices`. Password-reset links expire after 15 minutes.

## API use

POST a registered username/password to /api/token/ to obtain a token. Send
Authorization: Token followed by that value on protected requests. Never put
tokens in URLs or commit them. Browser session authentication retains CSRF
checks. Use HTTPS outside local development.

The API provides POST /api/stores/, GET /api/vendors/<id>/stores/,
GET/POST /api/stores/<id>/products/ and GET /api/products/<id>/reviews/.
Buyers and vendors can list stores and products. Only vendors can create stores
and products; store ownership is checked on the server. Review retrieval is
restricted to the vendor who owns the product. Invalid input returns 400,
missing authentication 401, a wrong role 403 and an owner-hidden record 404.

## Reddit feed

Visit http://127.0.0.1:8007/reddit/. The helper requests r/Python's public JSON
endpoint using a User-Agent and finite connection/read timeouts. The page
displays returned titles, authors and links. Reddit availability is an external
dependency: timeout, access refusal or invalid JSON produces a clear HTTP 503
message. There are no fabricated fallback posts. Unit tests mock responses;
live-service verification is recorded separately from those tests.

Live check on 14 November 2026: Reddit's public JSON endpoints returned HTTP
403 from this environment. The application displayed its unavailable state;
real post display has not been verified here. The assessor's 24 November
feedback confirms live Reddit access is not required for this task.

To repeat the actual request independently of the browser, run:

```bash
python manage.py check_reddit
```

This calls the same helper as /reddit/ using the guide's exact public URL,
https://www.reddit.com/r/python/.json and its DjangoEcommerceApp/1.0 User-Agent.
There are no credentials or extra query parameters. The helper limits the
display to ten posts after parsing the returned JSON. The command reports
titles, authors and links, or exits with an error. HTTP 403 means
Reddit denied the request; HTTP 429 means a rate limit was reached. The command
does not retry around access restrictions, substitute saved posts or treat an
empty response as proof of successful display.

### Submission note for the reviewer — 24 November 2026

I followed the guide's public JSON URL and User-Agent. The direct request
previously returned HTTP 403 with the message "You've been blocked by network
security." Repeating `python manage.py check_reddit` on 24 November 2026 still
returned HTTP 403, so no live posts were available to display. The response
does not establish the precise reason Reddit blocked this network.

The helper, view, URL and template are implemented. The page reports the
failure instead of showing invented or saved posts. All 34 automated tests
passed, including API permissions and mocked Reddit success/failure cases;
mocked tests do not prove live Reddit access. Live post display is the only
known external limitation from these checks, not a required resubmission fix
under the assessor's latest guidance. Failed and rate-limited requests keep
their clear fallback state without invented posts.

## Verification and design

The HTML flow is in shop/views.py. Each view documents its allowed methods,
template context, redirects and permission failures. shop/models.py explains
record constraints and shop/forms.py explains editable fields and validation.
Checkout and reset transactions are kept separately in shop/services.py.

shop/api.py contains API views, serializers and role checks; shop/api_urls.py
maps the routes. functions/reddit.py handles external HTTP data, while the
reddit_feed view handles its page response. shop/test_api.py explains the
ownership and external-service cases. Mocked responses make these tests
repeatable; they are not evidence that the live Reddit service is reachable.

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test shop
```

The suite includes Part 1 regressions, real token authentication, API ownership,
validation and external-service failure handling. See ../Planning/api_plan.md
and ../Planning/api_sequence.pdf for representations, routes and interactions.
Do not include a database, .venv, caches, private tokens or collected static
files in submission. Production needs a private secret, DEBUG disabled, trusted
hosts, HTTPS, a production server and real email configuration.
