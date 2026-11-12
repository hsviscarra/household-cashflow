# ADR-083: Sign in with Google

Status: accepted (0.92.0, Nov 2026)

Hernan asked for a username and password on the web. The options were Google sign-in, email and
password through Microsoft Entra External ID, or passwords kept by the app. He chose Google: both
of them have Gmail, there is no new password, and no password ever reaches the app.

- Container Apps' sign-in gets a second provider, `google`, with the client secret in the
  Container App secret `google-provider-secret`. `globalValidation.redirectToProvider` becomes
  `google`, so the app's address goes to Google; Microsoft stays at `/.auth/login/aad`.
- Nothing changes in the app: the sign-in still passes the email in
  `X-MS-CLIENT-PRINCIPAL-NAME`, and the allow-list (`ALLOWED_EMAILS`) decides who gets in.
- `infra/azure/setup-google-signin.sh` does it on the running app (it reads the current sign-in
  configuration, adds Google and writes it back; it can add addresses to `ALLOWED_EMAILS`).
  `main.bicep` takes `googleClientId` and `googleClientSecret` so a fresh setup can include it.
- The Google client is created by hand in Google's console (docs/runbooks/google-sign-in.md):
  it needs Hernan's Google account, and Claude doesn't sign in for him.

Not chosen: passwords in the app (it would hold password hashes for financial data and need
reset and lockout), and Entra External ID (more setup for the same result).
