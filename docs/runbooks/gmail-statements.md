# Statements by email (Gmail)

Bank statements emailed to Gmail reach the app by themselves once a day, at about 6 am. They're
read and wait on the **Import** page for your approval (F20, ADR-020). The Import page shows who
sent each one as `gmail (<sender>)`.

| Bank | Sender | Statements |
|---|---|---|
| Banco Pichincha | documentoselectronicos@pichincha.com | Savings account and credit card (invoices are skipped) |
| PacifiCard | estadodecuenta@pacificard.ec | Mastercard Black |
| Diners Club | info@efacturacioninterdin.com | Diners Club |
| Produbanco | bancaenlinea@produbanco.com | Visa ending 5997 (the savings account isn't emailed) |

Bank of America and Capital One come next (issue #60).

The same script also sends every **electronic invoice XML**, from any vendor, for the Purchases
page (docs/runbooks/invoices.md).

## Set it up (once)

1. **Turn on the inbox.** From the repo root, signed in to Azure:

   ```bash
   az login
   ./infra/azure/setup-inbox.sh
   ```

   At the end it prints `APP_URL` and `INBOX_TOKEN`.

2. **Create the script.**
   1. Signed in to Gmail as hsviscarra@gmail.com, open https://script.google.com and choose
      **New project**.
   2. Name it "household-cashflow statements".
   3. Replace the contents of `Code.gs` with this repo's `infra/gmail/Code.gs`.
   4. In **Project Settings**, tick "Show appsscript.json", and replace that file with this
      repo's `infra/gmail/appsscript.json`.
   5. Still in **Project Settings → Script properties**, add `APP_URL` and `INBOX_TOKEN` with
      the two values from step 1.

3. **Start it.** In the editor, choose the function `setup` and **Run**. Google asks you to
   allow access to your Gmail and to external requests: it's your own script, so choose
   *Advanced → Go to household-cashflow statements* and allow. `setup` creates the daily trigger
   and runs once. The **Execution log** shows what it sent.

4. **Load the backlog (optional).**
   1. Add a script property `BACKFILL_FROM`, for example `2026/01/01`.
   2. Run `backfill`. Each run sends up to 25 files. Run it again until the log no longer says
      "More left".
   3. Approve the batches on the Import page, oldest first, so the continuity checks line up.

## What the labels mean

- **cashflow-imported:** sent. Either it was read and waits for approval, or it was already in
  the app.
- **cashflow-check:** sent, but it needs you on the Import page (choose its account, or a
  statement that couldn't be read), or the app refused the file. To send one again, remove the
  label.
- **No label yet:** not sent yet, or the app couldn't answer. The next day's run tries again.
  A run stops starting new files after 4.5 minutes (Google allows 6); the log then says "More
  left", and the next run, or running it again, continues.

A statement is read right after the app answers, so it can take a minute or two (several for a
PacifiCard, which needs text recognition) to appear on the Import page.

## When statements arrive

From the 2026 emails, roughly once a month each:

| Statement | Usually arrives |
|---|---|
| Diners Club | 4th to 6th |
| Banco Pichincha card | 15th or 16th |
| Banco Pichincha account | 13th to 22nd, varies |
| PacifiCard | 24th to 26th |
| Produbanco Visa | 1st to 3rd (cut-off on the last day of the month) |

Some months have no email at all: Pichincha's card in July, September and October, and its
account in January, April and July. Those months need a manual upload; the month-status page
shows what's missing. To check sooner than the next morning, run `run` in the editor.

## Add a bank

Add a line to `SOURCES` in `Code.gs`, both in the repo and in the script editor, with the bank's
sender and a subject word that skips its other emails:

```js
{ bank: 'Capital One', query: 'from:<sender> subject:statement' },
```

## Replace the token

```bash
ROTATE=1 ./infra/azure/setup-inbox.sh
```

Then paste the new `INBOX_TOKEN` into the script's properties.

## Transfer notices (0.38.0)

The same script also sends the banks' transfer notices (Produbanco "Transferencia enviada /
recibida / acreditada", Pichincha "NOTIFICACION BANCO PICHINCHA") to `/api/inbox/transfer`, with
the same token. The app keeps only the date, amount, account, the other party's name, the
description typed at the bank and the bank's reference, as a transfer note (People & Transfers
page); the email text isn't stored. Notices for accounts that aren't the household's (a copy
for a relative's account) and transfers between the household's own accounts are skipped. Each
notice is labeled `cashflow-imported` once the app has answered.

To turn it on, paste the new `infra/gmail/Code.gs` over the script's code and save; the daily
trigger stays. To bring in older notices, run `backfill()` (it reads from `BACKFILL_FROM`).

## Turn it off

- In the script editor, open **Triggers** and delete the `run` trigger.
- To close the endpoint too, remove `INBOX_TOKEN` from the Container App. `/api/inbox` then
  answers 404.

## Locally

Set `INBOX_TOKEN` in `.env` and run `docker compose up --build`. Then post a file:

```bash
curl -H "Authorization: Bearer $INBOX_TOKEN" -F file=@statement.pdf -F sender=me \
  http://localhost:8000/api/inbox
```
