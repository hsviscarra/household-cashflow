# Statements by email (Gmail)

Bank statements emailed to Gmail reach the app by themselves every hour. They're read and wait on
the **Import** page for your approval (F20, ADR-020). The Import page shows who sent each one as
`gmail (<sender>)`.

| Bank | Sender | Statements |
|---|---|---|
| Banco Pichincha | documentoselectronicos@pichincha.com | Savings account and credit card (invoices are skipped) |
| PacifiCard | estadodecuenta@pacificard.ec | Mastercard Black |
| Diners Club | info@efacturacioninterdin.com | Diners Club |

Bank of America and Capital One come next (issue #60).

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
   *Advanced → Go to household-cashflow statements* and allow. `setup` creates the hourly trigger
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
- **No label yet:** not sent, or the app was asleep (it scales to zero). The next hourly run tries
  again.

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
