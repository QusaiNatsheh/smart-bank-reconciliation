# LinkedIn posts: Smart Bank Reconciliation (drafts)

Drafts for review before posting. Replace `<repo link>` with the GitHub URL once the repository is public.
Attach the suggested image or video to each post.

---

## Post 1: the problem

**Attach:** `docs/screenshots/01_bank_lines.png` (or the architecture diagram from the README)

Why is bank reconciliation still so manual in 2026?

Because real bank lines look like this:

دفعة NIV/2026/00960 + فاتورة 997 REF75495

- A typo in the invoice number ("NIV" instead of "INV").
- A second invoice written in Arabic ("invoice 997").
- One transfer paying two invoices.
- The payer printed as "شركة العمري للطباعة والنشر", while the invoice says "Al Omari Printing and Publishing Co.".

Rules that match on reference and amount handle the clean cases. Accountants in Jordan and Saudi Arabia spend
their time on everything else: missing references, partial payments, grouped payments, bank fees, and names that
switch between Arabic, English and several Latin spellings of the same Arabic name.

So I built a learned matcher for Odoo 20 as a portfolio project:
→ it ranks the most likely invoice, or group of invoices, for each bank line
→ it shows a confidence score and the reasons in plain words
→ the accountant accepts or rejects, and that feedback is kept for retraining

Next post: how it compares with hand-written matching rules, with numbers.

#Odoo #Accounting #MachineLearning #Jordan #SaudiArabia

---

## Post 2: the results

**Attach:** a screenshot of the results table from the README

I compared a learned ranking model with hand-written matching rules on bank reconciliation. Here is what came out.

The setup:
- 1,700 bank lines from the last 4 of 24 months (never seen in training)
- synthetic data with realistic noise: typos, missing references, partial and grouped payments, bank fees, and
  Arabic and English names

Right invoice(s) suggested first:
• Hand-written rules: 92.9%
• LightGBM ranking model: 96.6%

Where the gap is biggest:
• Partial payments: 80.4% → 90.9%
• Grouped payments (one transfer, several invoices): 98.9% → 100%

When the model is confident (score of 0.8 or more), it is right 98.9% of the time, and that covers 88% of all
lines. So an accountant can review the confident ones quickly and spend real time on the rest.

The part that made the biggest difference was not the model. It was name matching across scripts: normalising
Arabic letter variants, and comparing a consonant "skeleton", so that النور, Al-Nour and Alnoor count as the same
name.

Honest limits: the data is synthetic, so real-world accuracy will be lower and has to be measured on real
statements. And the comparison is against my own rule set, not Odoo Enterprise's reconciliation models.

Code and full results: <repo link>

#MachineLearning #Odoo #Accounting #LightGBM

---

## Post 3: the demo

**Attach:** a 30-second screen recording, or `docs/screenshots/demo.gif`

30 seconds: from a messy bank line to a reconciled payment in Odoo 20.

1. Click "Suggest Matches" on the line.
2. The model proposes the two invoices this transfer pays, even though one reference has a typo and the other is
   written in Arabic.
3. Each suggestion shows why: the reference mentions the invoice number, the amount fits, the payer name matches.
4. Accept: the bank line is reconciled with both invoices, and the decision is logged for retraining.

Nothing is posted automatically. A person accepts every match.

Built with Odoo 20 Community, FastAPI, LightGBM and MLflow. It runs with one `make demo`.

<repo link>

#Odoo #Automation #Accounting #Python
