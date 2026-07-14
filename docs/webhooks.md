# Webhooks

## Stripe

Endpoint:

```text
POST /api/v1/billing/webhook
```

The server verifies `stripe-signature` with `STRIPE_WEBHOOK_SECRET`.

## GitHub

GitHub App webhooks should use `GITHUB_APP_WEBHOOK_SECRET`. Planned events:

- installation created/deleted
- pull request opened/closed
- check suite completed
- push to tracked branch

## Signature Verification

All production webhooks must verify provider signatures before changing database state.
