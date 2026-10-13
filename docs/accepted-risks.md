# Accepted Risks

## Retry-After versus fetch sleep budget

A Binance `Retry-After` value from 31 through 60 seconds exceeds the project's 30-second per-fetch sleep budget. The fetch therefore fails closed and persists a cooldown instead of sleeping past the budget. The cooldown trigger minimum is 600 seconds, so the resulting cooldown can be longer than the supplied Retry-After. This is an intentionally conservative rate-limit/IP-protection policy and requires reviewer acceptance before freeze.

## Evidence availability

Offline, CI, and live evidence are separate evidence classes. Missing live evidence keeps Milestone 1 BLOCKED; it is not converted into a pass by a reviewer disposition.

## Cooldown scope across checkouts

Cooldown state is stored in the project data directory and is therefore shared only by processes using the same checkout/data directory. Two separate checkouts running from the same IP do not share cooldown state. This is accepted because cross-checkout shared state would require an external coordination mechanism; the application remains fail-closed within each checkout.
