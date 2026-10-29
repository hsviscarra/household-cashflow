# Claude's connection to the data (MCP)

Claude reads the numbers through a read-only login. The one write is `save_portfolio`: it saves
your Interactive Brokers portfolio when you ask (docs/runbooks/ibkr.md).

Lets the Claude desktop app answer questions from the app's live numbers, for example "how did
October compare to September?" (F18, ADR-017).

## How it works

- The app serves an MCP endpoint at `https://<app>/mcp`. Only requests with its bearer token
  (`MCP_TOKEN`) get through. The Microsoft sign-in skips that one path, because the token
  protects it instead.
- Every tool reads the `mart` views through **`cashflow_reader`**, a database login that can
  only `SELECT` from those views. It can't read a table directly or change anything. The app
  creates the login at start-up from `READER_PASSWORD`.
- **Tools:**
  - `months`
  - `cash_flow` (spending or cash view)
  - `compare_months`
  - `spending_by_category`
  - `spending_lines`
  - `top_merchants`
  - `interest_and_fees`
- `balance_sheet`, `loans` and `monthly_report` (0.23.0) read the tables those pages are
  computed from, still with SELECT only.

## Turn it on (once)

From the repo root, signed in to Azure:

```bash
az login
./infra/azure/setup-mcp.sh
```

The script:
1. Stores the two secrets on the Container App (it keeps the existing ones when re-run).
2. Lets `/mcp` past the sign-in.
3. Checks the endpoint answers.
4. Prints the configuration for the Claude desktop app.

## Connect the Claude desktop app

1. Install Node.js once: `brew install node`.
2. In Claude: **Settings → Developer → Edit Config**. That opens
   `~/Library/Application Support/Claude/claude_desktop_config.json`.
3. Add the `household-cashflow` entry the script printed under `"mcpServers"`. It looks like this
   (with your app's address and token):

   ```json
   {
     "mcpServers": {
       "household-cashflow": {
         "command": "npx",
         "args": ["-y", "mcp-remote@0.1", "https://<app>/mcp", "--header", "Authorization:${MCP_AUTH}"],
         "env": { "MCP_AUTH": "Bearer <token>" }
       }
     }
   }
   ```

4. Quit and reopen Claude. In a chat (in the Personal Accountant project, for instance), the
   tools menu shows **household-cashflow**. Ask "How did October compare to September?"

The first question after a quiet while can take up to a minute: the app scales to zero and the
database pauses.

## Keep the token private

The token reads all the household's numbers. It lives only in Azure (a Container App secret) and
in your Claude config file; don't commit it or paste it in chats.

- **Replace it:** run `ROTATE=1 ./infra/azure/setup-mcp.sh`, then update the config.
- **Turn the endpoint off:** remove the `MCP_TOKEN` environment variable from the Container App.
  With no token set, `/mcp` answers 404.

## Locally

Set `MCP_TOKEN` and `READER_PASSWORD` in `.env` and run `docker compose up --build`. The
endpoint is then at `http://localhost:8000/mcp`. Use that URL and token in the config above.
