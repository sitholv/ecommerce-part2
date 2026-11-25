# eCommerce API plan

Vusi Sithole — VS26060020556

## Resource representations

I use JSON for this API because its objects and arrays map directly to store,
product and review records. Prices are decimal strings, avoiding a loss of
precision in clients that use floating-point numbers. Dates use the DRF
timestamp representation. Related resources are identified by database IDs.
Passwords, reset-token digests and private invoices are never serialized here.

XML could represent the same information with nested elements. It would require
an agreed element structure and an XML renderer/parser. The brief allows a
representation choice; this implementation chooses JSON instead of adding an
unused XML dependency. Clients send Content-Type: application/json for JSON
bodies and can request application/json responses.

A store contains id, vendor, name and description. A product contains id, store,
name, description, price and stock. A review contains id, buyer, product,
rating, content, created_at and verified. Verification is computed from actual
order lines and is read-only. A caller cannot choose a different vendor or
store through a forged body field.

## Endpoints and access

POST /api/token/ accepts a registered username and password and returns a DRF
token. Other requests include Authorization: Token followed by that token.
Authenticated browser sessions are also supported and retain CSRF protection.
Production deployments must use HTTPS because a token is a reusable credential.

POST /api/stores/ creates a store for the logged-in vendor. Buyers receive 403.
POST /api/stores/<store_id>/products/ creates a product only when the vendor
owns that store. An owner-scoped lookup returns 404 for another vendor's store.
GET /api/products/<product_id>/reviews/ lets the owning vendor retrieve reviews.

GET /api/vendors/<vendor_id>/stores/ lists that vendor's stores.
GET /api/stores/<store_id>/products/ lists that store's products. Both buyer and
vendor accounts can use these read endpoints. Missing stores return 404. An
existing vendor with no stores returns an empty JSON list.

Successful creation returns 201; successful lists return 200. Invalid fields
return 400. Missing credentials return 401; an authenticated wrong role returns
403. Missing or ownership-hidden resources return 404. No endpoint accepts
listing changes through GET. The sequence diagram shows success and denial
paths through authentication, validation, ownership checks and the database.

## Third-party Reddit integration

The chosen community is r/Python. functions/reddit.py builds a public JSON-feed
request, supplies a descriptive User-Agent and parses post titles, authors and
links. The view passes this data to reddit_feed.html at /reddit/. Only HTTP(S)
links are rendered. The integration has connection/read timeouts and handles
HTTP errors, malformed JSON and unavailable service responses. It does not
invent posts when Reddit cannot be reached. The browser shows an explicit 503
unavailable state in that case.

## Verification and recovery

Automated tests cover anonymous denial, allowed role reads, buyer write denial,
forged owner IDs, cross-vendor product creation, validation and review access.
Mocked feed tests cover success, timeout, malformed data and unsafe URL schemes.
A live browser request must be checked separately; mocked tests alone do not
prove that Reddit is currently reachable. If the live service blocks this
environment, record that limitation instead of claiming a successful response.
