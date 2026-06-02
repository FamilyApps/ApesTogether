# #3 Pending Trades — design & progress

## Problem
After-hours buys hit Holdings instantly at a stale price and are immediately
sellable. Trades submitted while the market is closed should instead show under
**Recent Trades as "Pending"** (no price) until the next market open, when a real
open price is established. Cash-on-hand must be used before new capital.

## Key findings
- **Cash-on-hand-first already works**: `cash_tracking.process_transaction`
  spends `cash_proceeds` before `max_cash_deployed`. No change needed.
- **Existing queue infra**: `models.QueuedEmailTrade` + `services.trading_email.process_queued_trades()`
  already queues after-hours *email* trades and settles them at the open price.
  The market-open cron `/api/cron/market-open` already calls it. Reuse this for app trades.
- **Two buy paths**:
  - `POST /portfolio/trade` (`execute_trade`) — per-ticker Buy/Sell, client sends a price.
  - `POST /portfolio/stocks` (`add_stocks`) — the multi-row "Buy Stocks" sheet AND
    onboarding "Add Your Stocks". Client sends only ticker+qty → price defaults to 0,
    and NO transaction is created (latent bug for the buy button). Must branch on intent.
- **Recent trades surface**: single endpoint `get_portfolio(slug)` builds `recent_trades`
  from the `Transaction` table; serves both owner + subscriber views.
- **Market-hours check**: `timezone_utils.is_market_hours()` (same one the email path uses).

## Plan
### Backend (mobile_api.py) — no schema change (reuse QueuedEmailTrade)
1. [DONE] `execute_trade`: if `not is_market_hours()` → validate sells vs held−queued_sells,
   create `QueuedEmailTrade(status='queued')`, return `{success, pending:true}`.
2. [WIP] `add_stocks`: add `intent` ('buy'|'seed', default seed).
   - intent=='buy' + closed → queue pending buys.
   - intent=='buy' + open → fetch live prices, real buys via process_transaction.
   - intent=='seed' → unchanged immediate behavior.
3. [ ] `get_portfolio`: for owner only, prepend queued trades into `recent_trades`
   with `price:null`, `status:'pending'`, `pending_id`. Tag executed rows `status:'executed'`.
4. [ ] `DELETE /portfolio/pending-trades/<id>`: cancel a queued trade (owner).

### Clients (lockstep — rebuild required)
5. [ ] iOS: `Trade.price`/`TradeDetail.price` optional + `status`; TradeRow renders pending;
   AddStocksView buy context sends `intent:"buy"` + pending messaging; APIService intent param.
6. [ ] Android: `Trade.price` nullable + `status`; TradeRow renders pending.

## Settlement
The existing `/api/cron/market-open` → `process_queued_trades()` fetches the open price,
runs `process_transaction` (cash-first), creates the Transaction, fires subscriber
notifications, and emails a confirmation. App-queued trades flow through this unchanged.

## Deploy note
Backend sends `price:null` for pending recent-trade rows → BOTH client `Trade.price`
must be optional BEFORE relying on it. Rebuild iOS + Android after pulling.
