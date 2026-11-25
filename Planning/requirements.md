# Vusi Sithole

Student number: VS26060020556

## 1. Purpose and users

Bay Market is a local multi-vendor shop. Vendors manage their own stores and
products. Buyers browse products across stores, keep a cart while browsing,
check out and leave reviews. The application uses rand for all prices.
Checkout records an order and invoice; no real card payment or payment gateway
is claimed because payment processing is outside this brief.

## 2. Functional requirements

Users can register as buyers or vendors, log in and log out. Both roles can
browse stores and products. Vendors can create, view, update and delete only
their own stores and products. A buyer can add quantities to a session cart,
remove lines, inspect the current total and confirm checkout. Checkout saves
an order, decrements inventory, builds an invoice, clears the cart and emails
the invoice. Buyers can view their own invoices after checkout. A failed email
must not cause the buyer to repeat a purchase.

Buyers can review a product before or after purchase. Purchase verification
comes from stored order lines, not from a checkbox supplied by the reviewer.
Users can request an emailed password-reset link. The random secret is stored
only as a digest, expires after 15 minutes and can be used once.

## 3. Interface plan

The catalogue shows product names, store names, prices and availability, with
links to product details. Navigation provides the catalogue, stores, cart and
account actions. Vendor navigation adds My stores and Create store. The
product page groups description, stock, quantity input and reviews. Each edit
screen has labelled fields, nearby validation errors, Save and Cancel. A
separate confirmation screen names the store or product before deletion.

The cart lists product, quantity, current price and subtotal, followed by its
computed total and one checkout action. The invoice uses frozen purchase
prices. On a phone, navigation folds into a compact menu and content becomes
a single column. Empty lists explain what the user can do next; they do not
invent sample customers or reviews. Browser checks will cover 1440, 768 and
390 pixel widths, keyboard focus and validation errors.

## 4. Security and access control

Django hashes passwords and applies its password validators. Forms use CSRF
tokens, and mutation endpoints accept POST only. Logout also uses POST.
Buyer and vendor groups receive explicit model permissions after migrations.
Views enforce both role permissions and object ownership; knowing an ID never
grants access to another vendor's shop or another buyer's invoice.

Store ownership and review authorship are assigned from the authenticated
account, not request fields. Notes and reviews are escaped by templates.
Prices use Decimal rather than floating-point arithmetic. Secrets and SMTP
credentials must come from environment variables for a deployed service.
Local coursework email uses the console backend; it does not send real mail.

## 5. Failure and recovery

Invalid forms redisplay the entered values with clear errors. Unknown IDs
return 404 and unauthorized actions return 403 or redirect to login. Empty,
invalid and overstock carts cannot be checked out. A transaction rolls back
the whole order if any cart line fails. Row locks and conditional stock
updates prevent negative inventory; a checkout UUID prevents repeated form
submissions from charging inventory twice.

Invoice lines retain names and prices after listing changes. Removing a
listing does not delete order evidence. If sending an invoice fails, the
order remains visible and the unsent email can be retried. A real deployment
would use a durable email job queue, monitoring and database backups.
Database or mail failures must not be reported as successful deliveries.

## 6. Non-functional requirements and verification

The application follows Django's MVT architecture, separates business services
from views, validates input, and uses normalized relational tables. Shared
templates and static CSS keep presentation separate from Python logic.
Class/function/test docstrings explain contracts, and comments explain
security and transaction choices. Settings use blank lines between logical
blocks. Automated tests cover role restrictions, ownership, checkout,
invoices, reviews and reset links. Migrations and browser tests are required
before the work is marked ready for submission.
