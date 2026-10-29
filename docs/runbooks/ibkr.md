# Interactive Brokers portfolio

How the app reads the IBKR portfolio (F22, ADR-019) and how to set it up or renew it.

## How it works

IBKR's **Flex Web Service** is a read-only report service. The app needs no password and no
live session. It asks IBKR to run your Flex Query, then downloads the report: positions, cash and
net asset value as of the last business day.

The app reads it:
- automatically when you open **Debt & Net Worth** and the last read is more than 20 hours old;
- whenever you click **Refresh from IBKR**.

Each read stores two things:
- the day's **positions** (symbol, quantity, price, value in USD, gain);
- the day's **total** as a value of the "Interactive Brokers" investment item. That's what the
  balance sheet, net worth and Claude's `balance_sheet` tool use.

Reading the same day again replaces it.

## Set up (once)

1. **Create the Flex Query** in Client Portal → *Performance & Reports → Flex Queries → Activity
   Flex Query → +*:
   - **Name:** `cashflow-app`.
   - **Sections:** *Net Asset Value (NAV) in Base*, *Open Positions* (option *Summary*) and *Cash
     Report*, each with *Select All*.
   - **Delivery:** format **XML**, period **Last Business Day**.
   - **General:** date format **yyyy-MM-dd**.
   - **Save**, then note the **Query ID**.
2. **Get the token.** Client Portal → *Settings → Flex Web Service*:
   - tick **Flex Web Service Status**;
   - click **Generate New Token** and set **Expire after 1 year**;
   - leave **Valid for IP address** blank, because Azure's outgoing address can change.
3. **Store them in Azure.** From the repo root:

   ```bash
   az login
   ./infra/azure/setup-ibkr.sh
   ```

   The script asks for the Query ID and the token without showing them, and stores both as
   Container App secrets.
4. **Check it:** open **Debt & Net Worth**. The *Investments* section reads the portfolio. Compare
   the total with Client Portal's net liquidation value for the same day.

## Renew the token

Before the token expires (IBKR shows the date), generate a new one and run
`./infra/azure/setup-ibkr.sh` again. If it expires anyway, the page says so: "Token has expired".

## Without the token

Client Portal can run the same Flex Query and download its XML. Use **Upload Flex report (XML)**
on Debt & Net Worth. It's read the same way.

## The old "Stock Market" row

If the workbook's "Stock Market" item is the same IBKR account, pause it on its card (**Edit →
pause**) so it isn't counted twice.
