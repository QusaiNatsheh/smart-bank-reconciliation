=========================
Smart Bank Reconciliation
=========================

Suggests which customer invoice(s) an incoming bank statement line pays. Suggestions come from a
separate ML service (see the repository README) and show a confidence score and plain-language reasons.

Usage
=====

#. Set the service address in *Invoicing / Accounting → Settings → Smart Bank Reconciliation*.
#. Optionally fill *Alternative Name* on customers (for example their Arabic name).
#. Open *Customers → Smart Reconciliation → Bank Lines to Match* and click *Suggest Matches* on a line.
#. *Accept* reconciles the line with the suggested invoices. *Reject* removes the suggestion.
   Both are logged in *Match Feedback* and sent to the service for retraining.

Limitations
===========

* Incoming payments to customer invoices only, in the company currency.
* When a line is smaller than the matched invoices (for example a bank fee), the last invoice stays partly
  open. No write-off is created.

Credits
=======

Author: Qusai Natsheh. License: LGPL-3.
