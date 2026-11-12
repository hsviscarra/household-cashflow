# Sign in with Google (ADR-083)

The app sits behind Azure Container Apps' sign-in. Microsoft was the only way in; this adds
Google, so a Gmail account works. Two parts: a Google client (once, in Google's console) and one
script.

## 1. Create the Google client (about 5 minutes)

1. Open <https://console.cloud.google.com/> with your Gmail account. Create a project (top bar
   -> New project), named for example `cashflow`.
2. **APIs & Services -> OAuth consent screen** (Google may call it "Google Auth Platform ->
   Branding"). User type **External**. App name `Cash flow`, your email as support and developer
   contact. No scopes to add. Save.
3. Still there, under **Audience**: either add both Gmail addresses as **Test users** and leave
   it in Testing, or press **Publish app** (no review is needed for sign-in only).
4. **APIs & Services -> Credentials -> Create credentials -> OAuth client ID**. Type **Web
   application**. Under **Authorized redirect URIs** add the line the script prints:

   ```
   ./infra/azure/setup-google-signin.sh
   ```

   It looks like `https://<the app's address>/.auth/login/google/callback`.
5. Create. Keep the window open: it shows the **Client ID** and the **Client secret**.

## 2. Run the script

```
az login
GOOGLE_CLIENT_ID="<the client id>" GOOGLE_EMAILS="you@gmail.com,lauren@gmail.com" \
  ./infra/azure/setup-google-signin.sh
```

It asks for the client secret without showing it. `GOOGLE_EMAILS` are the Gmail addresses allowed
in; leave it out when they are already allowed (the same address you use with Microsoft).

## After

- The app's address now goes to Google. Microsoft still works at
  `/.auth/login/aad?post_login_redirect_uri=/`; `DEFAULT_PROVIDER=azureactivedirectory` on the
  script puts Microsoft back as the one people are sent to.
- An address that isn't allowed sees "This account is not allowed": run the script again with it
  in `GOOGLE_EMAILS`.
- With a custom domain later, add `https://<the domain>/.auth/login/google/callback` to the
  client's redirect URIs.
- The secret lives only in the Container App (`google-provider-secret`), never in the repo.
