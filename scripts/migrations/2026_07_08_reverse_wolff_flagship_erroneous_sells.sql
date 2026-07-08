-- ============================================================================
-- 2026-07-08 — Reverse 4 erroneous copy-trade SELLs on Wolff's Flagship Fund
-- ============================================================================
-- Context: email-copy trading was paused, a personal-brokerage liquidation was
-- performed, then unpaused. On unpause the GAS parser re-POSTed the trade
-- emails received during the pause (there is no server-side email_message_id
-- idempotency yet), and 4 unique-holder sells hit the sell_anchor fast path in
-- bot_email_trade before it was re-paused:
--
--   txn 1151  META  sell 1.924822   @ 615.58      2026-07-08 19:43:18Z
--   txn 1152  GRAB  sell 166.166096 @ 3.835       2026-07-08 19:43:32Z
--   txn 1153  SPGI  sell 1.777899   @ 443.46      2026-07-08 19:43:32Z
--   txn 1154  NOW   sell 6.988398   @ 107.9015    2026-07-08 19:43:32Z
--
-- These were 100% sells. _execute_single_bot_trade decrements the holding
-- (`stock.quantity -= qty`) and does NOT delete the row (mobile_api.py:6496),
-- so each `stock` row is still present at quantity 0 with its ORIGINAL
-- purchase_price (cost basis) intact. We therefore reverse the sells exactly:
--   1. restore each holding's quantity,
--   2. remove the sale proceeds (qty*price) from the bot's cash_proceeds,
--   3. delete the 4 phantom transactions.
-- No market buy-back: that would refire subscriber push/email alerts, fill at
-- today's price, and corrupt cost basis. max_cash_deployed is untouched — sells
-- never changed it (cash_tracking.py:109), so the state returns to pre-sell.
--
-- SAFE + ATOMIC: aborts with NO changes if the 4 txns aren't all present for a
-- single bot, if any stock row is missing (basis lost — needs manual handling),
-- or if reversing would drive cash_proceeds negative (means cash was already
-- spent after the sells, so STOP and reassess).
--
-- HOW TO RUN (Supabase SQL Editor):
--   Paste + Run the whole file. It commits atomically at the trailing COMMIT.
--   Supabase's results grid only shows the LAST statement, so you'll see the
--   final SELECT (the user row); run the holdings SELECT separately to view it.
--   SAFE TO RE-RUN: if the 4 sells were already reversed/deleted, the txn-count
--   guard raises and the whole transaction aborts — no double-apply.
-- ============================================================================

BEGIN;

DO $$
DECLARE
    v_txn_ids     INT[] := ARRAY[1151, 1152, 1153, 1154];
    v_bot_id      INT;
    v_bot_count   INT;
    v_txn_count   INT;
    v_proceeds    NUMERIC;
    v_cash_before NUMERIC;
    v_cash_after  NUMERIC;
    r             RECORD;
BEGIN
    -- Resolve owning bot (all 4 txns must belong to exactly one user)
    SELECT count(DISTINCT user_id), min(user_id)
      INTO v_bot_count, v_bot_id
      FROM stock_transaction
     WHERE id = ANY(v_txn_ids);
    IF v_bot_count <> 1 THEN
        RAISE EXCEPTION 'Expected 4 txns owned by exactly 1 bot, found % distinct owner(s)', v_bot_count;
    END IF;

    -- All 4 must exist, be SELLs, on this bot
    SELECT count(*) INTO v_txn_count
      FROM stock_transaction
     WHERE id = ANY(v_txn_ids) AND user_id = v_bot_id AND transaction_type = 'sell';
    IF v_txn_count <> 4 THEN
        RAISE EXCEPTION 'Expected 4 matching SELL txns for bot %, found %', v_bot_id, v_txn_count;
    END IF;

    -- Proceeds to remove from cash_proceeds
    SELECT COALESCE(SUM(quantity * price), 0) INTO v_proceeds
      FROM stock_transaction WHERE id = ANY(v_txn_ids);

    SELECT cash_proceeds INTO v_cash_before FROM "user" WHERE id = v_bot_id;
    v_cash_after := v_cash_before - v_proceeds;
    IF v_cash_after < 0 THEN
        RAISE EXCEPTION 'Reversal would make cash_proceeds negative (% - % = %) — cash was spent after the sells; STOP and reassess',
            v_cash_before, v_proceeds, v_cash_after;
    END IF;

    -- Restore each holding (row must exist; a 100% sell left it at qty 0)
    FOR r IN SELECT ticker, quantity FROM stock_transaction WHERE id = ANY(v_txn_ids) LOOP
        UPDATE stock SET quantity = quantity + r.quantity
         WHERE user_id = v_bot_id AND ticker = r.ticker;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'No stock row for bot % ticker % — original cost basis is gone, cannot safely restore', v_bot_id, r.ticker;
        END IF;
    END LOOP;

    -- Reverse cash + delete the phantom sells
    UPDATE "user" SET cash_proceeds = v_cash_after WHERE id = v_bot_id;
    DELETE FROM stock_transaction WHERE id = ANY(v_txn_ids);

    RAISE NOTICE 'OK bot %: restored 4 holdings; cash_proceeds % -> % (removed %); deleted txns %',
        v_bot_id, v_cash_before, v_cash_after, v_proceeds, v_txn_ids;
END $$;

-- ── Verification (runs inside the open transaction, BEFORE you COMMIT) ───────
-- Holdings should be back to positive quantity with unchanged purchase_price:
SELECT id, ticker, quantity, purchase_price
  FROM stock
 WHERE user_id = (SELECT id FROM "user"
                   WHERE display_name ILIKE '%wolff%flagship%' OR username ILIKE '%wolff%'
                   LIMIT 1)
   AND ticker IN ('META','GRAB','SPGI','NOW')
 ORDER BY ticker;

-- cash_proceeds should be reduced by the summed proceeds (~3,364.62):
SELECT id, username, display_name, cash_proceeds, max_cash_deployed
  FROM "user"
 WHERE display_name ILIKE '%wolff%flagship%' OR username ILIKE '%wolff%';

-- Commit atomically (Supabase runs the whole batch in one transaction).
-- If the DO block raised above, this transaction is already aborted and
-- COMMIT is a harmless no-op — nothing is applied.
COMMIT;
