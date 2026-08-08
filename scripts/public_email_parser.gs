/**
 * Google Apps Script — Public.com Trade Email Parser
 * ====================================================
 * Watches bobford00@gmail.com inbox for Public.com trade notification emails
 * from "The Grok Portfolio" and "Wolff's Flagship Fund", parses the trades,
 * and forwards them to the Apes Together admin API as bot trades.
 *
 * SETUP:
 * 1. Go to https://script.google.com while logged in as bobford00@gmail.com
 * 2. Create a new project, paste this code
 * 3. Set Script Properties (Project Settings → Script Properties):
 *    - CRON_SECRET: your cron secret (separate from admin API key)
 *    - API_BASE_URL: https://apestogether.ai/api/mobile
 *    - GROK_BOT_USERNAME: the Grok bot's DB *username* (NOT its display name)
 *    - WOLFF_BOT_USERNAME: the Wolff bot's DB *username* (NOT its display
 *      name) — e.g. CoastHillBear, not "Wolff's Flagship Fund". The API looks
 *      bots up by User.username; display names 404.
 * 4. Run setupTrigger() once to create the time-based trigger
 * 5. The script will check for new emails every 5 minutes
 */

// ── Configuration ──────────────────────────────────────────────────────────

function getConfig() {
  const props = PropertiesService.getScriptProperties();
  return {
    CRON_SECRET: props.getProperty('CRON_SECRET'),
    API_BASE_URL: props.getProperty('API_BASE_URL') || 'https://apestogether.ai/api/mobile',
    GROK_BOT_USERNAME: props.getProperty('GROK_BOT_USERNAME'),
    WOLFF_BOT_USERNAME: props.getProperty('WOLFF_BOT_USERNAME'),
  };
}

// ── Main Entry Point ───────────────────────────────────────────────────────

function checkForTradeEmails() {
  const config = getConfig();
  if (!config.CRON_SECRET) {
    Logger.log('ERROR: CRON_SECRET not configured');
    return;
  }

  // Load set of already-processed message IDs from ScriptProperties
  // This makes us independent of read/unread status (emails may be auto-read
  // by another Gmail client, phone, or preview pane).
  const props = PropertiesService.getScriptProperties();
  const processedJson = props.getProperty('PROCESSED_MESSAGE_IDS') || '[]';
  let processedArray = [];
  try { processedArray = JSON.parse(processedJson); } catch (e) { processedArray = []; }
  const alreadyProcessed = new Set(processedArray);

  // Search for Public.com trade emails from the last 2 days (covers weekends)
  // No is:unread filter — we track processed IDs ourselves
  const queries = [
    'from:mail.public.com subject:"Your trade executed" newer_than:2d',
    'from:mail.public.com subject:"trade" newer_than:2d',
    'from:mail.public.com subject:"bought" newer_than:2d',
    'from:mail.public.com subject:"sold" newer_than:2d',
    'from:mail.public.com subject:"executed" newer_than:2d',
    'from:mail.public.com subject:"order" newer_than:2d',
    'from:mail.public.com subject:"rebalanced" newer_than:2d',
  ];

  let processedCount = 0;
  const seenIds = new Set(); // Avoid processing same message from multiple query matches
  const newlyProcessed = [];

  for (const query of queries) {
    const threads = GmailApp.search(query, 0, 20);

    for (const thread of threads) {
      const messages = thread.getMessages();
      for (const message of messages) {
        const msgId = message.getId();
        if (alreadyProcessed.has(msgId) || seenIds.has(msgId)) continue;
        seenIds.add(msgId);

        // Thread-level search returns EVERY message in a matching thread —
        // including your own forwards/replies of a trade confirmation, which
        // have new message IDs the dedupe sets can't catch (2026-07-17: a
        // "Fwd: Your trade executed" was re-ingested as a new MBGL trade).
        // Only parse messages actually SENT BY Public.
        const sender = String(message.getFrom() || '');
        const subj = String(message.getSubject() || '');
        if (!/[@.]public\.com/i.test(sender) || /^\s*(fwd?|re)\s*:/i.test(subj)) {
          Logger.log(`Skipping non-Public/forwarded message: "${subj}" from ${sender}`);
          message.markRead();
          newlyProcessed.push(msgId);
          continue;
        }

        try {
          const result = processTradeEmail(message, config);
          if (result) {
            processedCount++;
            Logger.log(`Processed: ${message.getSubject()} → ${result.trades_executed} trades (auto-routed to ${result.bot_username})`);
          }
        } catch (e) {
          Logger.log(`ERROR processing "${message.getSubject()}": ${e.message}`);
        }
        // Mark as read for inbox cleanliness
        message.markRead();
        newlyProcessed.push(msgId);
      }
    }
  }

  // Persist updated processed IDs (keep last 500 to avoid property size limits)
  if (newlyProcessed.length > 0) {
    const updated = processedArray.concat(newlyProcessed).slice(-500);
    props.setProperty('PROCESSED_MESSAGE_IDS', JSON.stringify(updated));
  }

  Logger.log(`Processed ${processedCount} trade emails (${newlyProcessed.length} new, ${alreadyProcessed.size} previously seen)`);

  // Retry any pending trades that couldn't be auto-routed earlier
  // (new stock tickers that didn't match any bot at the time)
  try {
    const retryUrl = config.API_BASE_URL + '/admin/bot/process-pending-trades';
    const retryResp = UrlFetchApp.fetch(retryUrl, {
      method: 'post',
      contentType: 'application/json',
      headers: { 'X-Cron-Secret': config.CRON_SECRET },
      payload: JSON.stringify({}),
      muteHttpExceptions: true,
    });
    const retryResult = JSON.parse(retryResp.getContentText());
    if (retryResult.routed > 0 || retryResult.expired > 0) {
      Logger.log(`Pending trades: ${retryResult.routed} routed, ${retryResult.expired} expired, ${retryResult.still_pending} still pending`);
    }
  } catch (e) {
    Logger.log(`Pending trade retry error: ${e.message}`);
  }
}

// ── Email Parsing ──────────────────────────────────────────────────────────

function processTradeEmail(message, config) {
  const subject = message.getSubject();
  const body = message.getPlainBody();
  const htmlBody = message.getBody();

  // Skip dividend emails — dividends are tracked automatically via AlphaVantage API
  if (/dividend/i.test(subject)) {
    Logger.log(`Skipping dividend email: "${subject}"`);
    return null;
  }

  // Parse trades from the email body
  const trades = parseTradesFromEmail(body, htmlBody);

  if (trades.length === 0) {
    Logger.log(`No trades found in email: "${subject}"`);
    return null;
  }

  // Use 'auto' — the API will match traded tickers against each bot's
  // current holdings and route to the bot with the most overlap.
  // This works because Grok and Wolff hold entirely different stocks.
  const botUsername = 'auto';
  const source = 'public_email';

  Logger.log(`Found ${trades.length} trades, sending for auto-detection: ${JSON.stringify(trades.map(t => t.ticker))}`);

  // Capture the email's *received* timestamp + Gmail message ID so the
  // backend can cluster trades that arrived together (regardless of
  // when this 5-minute GAS poll happens to fire) and use sells as
  // routing anchors when ticker-overlap is ambiguous.
  const receivedAtIso = message.getDate().toISOString();
  const messageId = message.getId();

  // Submit trades to the API (auto-detection will route to correct bot)
  return submitTrades(config, botUsername, trades, source, body, subject, receivedAtIso, messageId);
}

function parseTradesFromEmail(plainBody, htmlBody) {
  const trades = [];
  const text = plainBody || htmlBody || '';

  let match;

  // Pattern 0a: Public.com HTML/rich format — "You sold $132.99 of GRAB" + "Quantity: 36.0398 shares"
  // Price is NOT sent — the API will fetch current price from AlphaVantage.
  const summaryPattern = /You\s+(bought|sold)\s+\$[\d,.]+\s+of\s+([A-Z]{1,5}(?:\.[A-Z]{1,2})?)/gi;
  while ((match = summaryPattern.exec(text)) !== null) {
    const action = match[1].toLowerCase() === 'bought' ? 'buy' : 'sell';
    const ticker = match[2].toUpperCase();
    const qtyMatch = text.substring(match.index).match(/Quantity:\s*([\d,.]+)\s*shares?/i);
    const quantity = qtyMatch ? parseFloat(qtyMatch[1].replace(',', '')) : 1;
    if (!trades.some(t => t.ticker === ticker && t.action === action)) {
      trades.push({ action, ticker, quantity });
    }
  }

  // Pattern 0b: Public.com plain text format — "You\nsold\nGRAB at\n$3.69 per share"
  // getPlainBody() strips HTML and produces this multiline format
  const plainPublicPattern = /You\s+(bought|sold)\s+([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s+at\s+\$?[\d,.]+\s+per\s+share/gi;
  while ((match = plainPublicPattern.exec(text)) !== null) {
    const action = match[1].toLowerCase() === 'bought' ? 'buy' : 'sell';
    const ticker = match[2].toUpperCase();
    if (!trades.some(t => t.ticker === ticker && t.action === action)) {
      const qtyMatch = text.substring(match.index).match(/Quantity:\s*([\d,.]+)\s*shares?/i);
      const quantity = qtyMatch ? parseFloat(qtyMatch[1].replace(',', '')) : 1;
      trades.push({ action, ticker, quantity });
    }
  }

  // Pattern 1: "Bought 10 shares of AAPL at $150.00"
  const boughtPattern = /(?:bought|purchased)\s+(\d+(?:\.\d+)?)\s+shares?\s+(?:of\s+)?([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s+(?:at\s+)?\$?([\d,.]+)/gi;
  while ((match = boughtPattern.exec(text)) !== null) {
    trades.push({
      action: 'buy',
      ticker: match[2].toUpperCase(),
      quantity: parseFloat(match[1]),
      price: parseFloat(match[3].replace(',', ''))
    });
  }

  // Pattern 2: "Sold 10 shares of AAPL at $150.00"
  const soldPattern = /(?:sold|selling)\s+(\d+(?:\.\d+)?)\s+shares?\s+(?:of\s+)?([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s+(?:at\s+)?\$?([\d,.]+)/gi;
  while ((match = soldPattern.exec(text)) !== null) {
    trades.push({
      action: 'sell',
      ticker: match[2].toUpperCase(),
      quantity: parseFloat(match[1]),
      price: parseFloat(match[3].replace(',', ''))
    });
  }

  // Pattern 3: "BUY AAPL 10 @ $150" or "SELL AAPL 10 @ $150"
  const shortPattern = /(buy|sell)\s+([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s+(\d+(?:\.\d+)?)\s*(?:@|at)\s*\$?([\d,.]+)/gi;
  while ((match = shortPattern.exec(text)) !== null) {
    // Avoid duplicates
    const ticker = match[2].toUpperCase();
    if (!trades.some(t => t.ticker === ticker && t.action === match[1].toLowerCase())) {
      trades.push({
        action: match[1].toLowerCase(),
        ticker: ticker,
        quantity: parseFloat(match[3]),
        price: parseFloat(match[4].replace(',', ''))
      });
    }
  }

  // Pattern 4: Table format — "AAPL | Buy | 10 | $150.00" (common in rebalance emails)
  const tablePattern = /([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s*\|\s*(buy|sell|bought|sold)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*\$?([\d,.]+)/gi;
  while ((match = tablePattern.exec(text)) !== null) {
    const ticker = match[1].toUpperCase();
    const action = /buy|bought/i.test(match[2]) ? 'buy' : 'sell';
    if (!trades.some(t => t.ticker === ticker && t.action === action)) {
      trades.push({
        action: action,
        ticker: ticker,
        quantity: parseFloat(match[3]),
        price: parseFloat(match[4].replace(',', ''))
      });
    }
  }

  // Pattern 5: Simple ticker mention with action — "Added AAPL" / "Removed MSFT"
  // (No quantity/price — API will fetch current price, default 1 share)
  const addedPattern = /(?:added|adding|new position:?)\s+([A-Z]{1,5}(?:\.[A-Z]{1,2})?)/gi;
  while ((match = addedPattern.exec(text)) !== null) {
    const ticker = match[1].toUpperCase();
    if (!trades.some(t => t.ticker === ticker)) {
      trades.push({
        action: 'buy',
        ticker: ticker,
        quantity: 1
        // price omitted — API will fetch current
      });
    }
  }

  const removedPattern = /(?:removed|removing|exited|closed position:?)\s+([A-Z]{1,5}(?:\.[A-Z]{1,2})?)/gi;
  while ((match = removedPattern.exec(text)) !== null) {
    const ticker = match[1].toUpperCase();
    if (!trades.some(t => t.ticker === ticker)) {
      trades.push({
        action: 'sell',
        ticker: ticker,
        quantity: 1
      });
    }
  }

  return trades;
}

// ── API Submission ─────────────────────────────────────────────────────────

function submitTrades(config, botUsername, trades, source, rawEmail, emailSubject, emailReceivedAtIso, emailMessageId) {
  const url = `${config.API_BASE_URL}/admin/bot/email-trade`;

  const payload = {
    bot_username: botUsername,
    trades: trades,
    source: source,
    notes: rawEmail.substring(0, 500), // Truncate for storage
    email_subject: emailSubject || '',
    email_received_at: emailReceivedAtIso || null,
    email_message_id: emailMessageId || null
  };

  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'X-Cron-Secret': config.CRON_SECRET
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(url, options);
  const status = response.getResponseCode();
  const body = JSON.parse(response.getContentText());

  if (status === 200 && body.success) {
    if (body.status === 'deferred') {
      Logger.log(`API Deferred: ${body.message} (batch=${body.batch_id})`);
    } else {
      Logger.log(`API Success: ${body.trades_executed}/${body.trades_submitted} trades executed for ${body.bot_username}`);
      if (body.results) {
        for (const r of body.results) {
          if (r.error) Logger.log(`  ERROR ${r.ticker}: ${r.error}`);
          else Logger.log(`  OK ${r.ticker}: ${r.action} ${r.quantity} @ $${r.price}`);
        }
      }
    }
    return body;
  } else {
    Logger.log(`API Error (${status}): ${JSON.stringify(body)}`);
    return null;
  }
}

// ── Setup ──────────────────────────────────────────────────────────────────

/**
 * Run this function ONCE to set up the time-based trigger.
 * It will check for new trade emails every 5 minutes.
 */
function setupTrigger() {
  // Remove existing triggers
  const triggers = ScriptApp.getProjectTriggers();
  for (const trigger of triggers) {
    if (trigger.getHandlerFunction() === 'checkForTradeEmails') {
      ScriptApp.deleteTrigger(trigger);
    }
  }

  // Create new trigger — every 5 minutes
  ScriptApp.newTrigger('checkForTradeEmails')
    .timeBased()
    .everyMinutes(5)
    .create();

  Logger.log('Trigger created: checkForTradeEmails every 5 minutes');
}

/**
 * Test function — manually process the most recent matching email
 */
function testParseLatestEmail() {
  const config = getConfig();
  const threads = GmailApp.search('from:mail.public.com subject:"Your trade executed"', 0, 3);
  if (threads.length > 0) {
    for (const thread of threads) {
      const message = thread.getMessages()[0];
      Logger.log(`--- Email ---`);
      Logger.log(`From: ${message.getFrom()}`);
      Logger.log(`Subject: ${message.getSubject()}`);
      Logger.log(`Body preview: ${message.getPlainBody().substring(0, 500)}`);
      const trades = parseTradesFromEmail(message.getPlainBody(), message.getBody());
      Logger.log(`Parsed trades: ${JSON.stringify(trades, null, 2)}`);
    }
  } else {
    Logger.log('No matching emails found — check from:mail.public.com');
  }
}

/**
 * Re-process today's trade emails (even already-read ones) for debugging.
 * Marks them unread first so the main function can pick them up.
 */
function reprocessTodaysTrades() {
  const threads = GmailApp.search('from:mail.public.com subject:"Your trade executed" newer_than:1d', 0, 20);
  Logger.log(`Found ${threads.length} threads from today`);
  let unmarked = 0;
  for (const thread of threads) {
    for (const msg of thread.getMessages()) {
      if (!msg.isUnread()) {
        msg.markUnread();
        unmarked++;
      }
    }
  }
  Logger.log(`Marked ${unmarked} messages as unread — run checkForTradeEmails() next`);
}

/**
 * Reprocess all trade emails since a given date.
 * Change the SINCE_DATE below before running.
 * 
 * This clears the processed-ID list so checkForTradeEmails() will
 * pick up all emails in its 2-day window on the next run.
 * For older emails, this function directly submits them to the API.
 */
function reprocessSince() {
  const SINCE_DATE = '2026/03/28';  // ← Change this date as needed (YYYY/MM/DD)
  const config = getConfig();
  
  if (!config.CRON_SECRET) {
    Logger.log('ERROR: CRON_SECRET not configured');
    return;
  }
  
  // Clear the processed-ID tracker so nothing is skipped
  const props = PropertiesService.getScriptProperties();
  props.deleteProperty('PROCESSED_MESSAGE_IDS');
  Logger.log('Cleared PROCESSED_MESSAGE_IDS');
  
  const queries = [
    `from:mail.public.com subject:"Your trade executed" after:${SINCE_DATE}`,
    `from:mail.public.com subject:"trade" after:${SINCE_DATE}`,
    `from:mail.public.com subject:"bought" after:${SINCE_DATE}`,
    `from:mail.public.com subject:"sold" after:${SINCE_DATE}`,
    `from:mail.public.com subject:"executed" after:${SINCE_DATE}`,
    `from:mail.public.com subject:"order" after:${SINCE_DATE}`,
    `from:mail.public.com subject:"rebalanced" after:${SINCE_DATE}`,
  ];
  
  const seenIds = new Set();
  let submitted = 0;
  let failed = 0;
  const newlyProcessed = [];
  
  for (const query of queries) {
    const threads = GmailApp.search(query, 0, 50);
    for (const thread of threads) {
      for (const msg of thread.getMessages()) {
        const msgId = msg.getId();
        if (seenIds.has(msgId)) continue;
        seenIds.add(msgId);
        
        try {
          const result = processTradeEmail(msg, config);
          if (result) {
            submitted++;
            Logger.log(`Reprocessed: ${msg.getSubject()} (${msg.getDate()}) → ${result.trades_executed} trades`);
          }
        } catch (e) {
          failed++;
          Logger.log(`ERROR reprocessing "${msg.getSubject()}": ${e.message}`);
        }
        msg.markRead();
        newlyProcessed.push(msgId);
      }
    }
  }
  
  // Save all these as processed so the regular trigger doesn't re-submit them
  if (newlyProcessed.length > 0) {
    props.setProperty('PROCESSED_MESSAGE_IDS', JSON.stringify(newlyProcessed.slice(-500)));
  }
  
  Logger.log(`Reprocess complete: ${seenIds.size} emails found, ${submitted} submitted, ${failed} failed`);
}

/**
 * One-shot BACKFILL for trade emails missed during an ingestion outage
 * (e.g. the 2026-08-05 Wolff rebalance, missed while the trigger was dead
 * after a Google password change).
 *
 * Differences from the normal flow — all deliberate:
 *   - Explicit bot (WOLFF_BOT_USERNAME script property), NOT 'auto' routing:
 *     auto-deferred BUYs expire 30 min after email_received_at, so a
 *     days-late replay would land every BUY in the unroutable pile.
 *   - Derives the ACTUAL fill price from the email ("You bought $X of TKR" +
 *     "Quantity: N shares" → price = X/N). The normal parser omits price and
 *     the API fetches the CURRENT price — correct live, wrong days later.
 *   - suppress_notifications: true — no stale "just bought" alerts.
 *   - Timestamps stay historical: email_received_at = message.getDate().
 *
 * USAGE:
 *   1. Set AFTER_DATE / BEFORE_DATE to bracket the missed day(s).
 *   2. Run with DRY_RUN = true and check the log (parsed trades + prices).
 *   3. Set DRY_RUN = false and run again to submit.
 * Server-side message-id dedupe makes re-runs harmless.
 */
function backfillMissedTrades() {
  const DRY_RUN = true;              // ← flip to false after checking the log
  const AFTER_DATE = '2026/08/04';   // Gmail after: (exclusive-ish, day before)
  const BEFORE_DATE = '2026/08/06';  // Gmail before: (day after the outage)

  const config = getConfig();
  if (!config.CRON_SECRET) { Logger.log('ERROR: CRON_SECRET not configured'); return; }
  if (!config.WOLFF_BOT_USERNAME) { Logger.log('ERROR: WOLFF_BOT_USERNAME not configured'); return; }

  const threads = GmailApp.search(
    `from:mail.public.com after:${AFTER_DATE} before:${BEFORE_DATE}`, 0, 50);
  Logger.log(`Found ${threads.length} threads in window`);

  const seenIds = new Set();
  let submitted = 0, skipped = 0, failed = 0;

  for (const thread of threads) {
    for (const msg of thread.getMessages()) {
      const msgId = msg.getId();
      if (seenIds.has(msgId)) continue;
      seenIds.add(msgId);

      const sender = String(msg.getFrom() || '');
      const subject = String(msg.getSubject() || '');
      if (!/[@.]public\.com/i.test(sender) || /^\s*(fwd?|re)\s*:/i.test(subject)
          || /dividend/i.test(subject)) {
        Logger.log(`Skipping: "${subject}" from ${sender}`);
        skipped++;
        continue;
      }

      const body = msg.getPlainBody();
      const trades = parseTradesWithFillPrices(body, msg.getBody());
      if (trades.length === 0) {
        Logger.log(`NO TRADES PARSED: "${subject}" (${msg.getDate()}) — body: ${(body || '').substring(0, 200)}`);
        skipped++;
        continue;
      }

      const missingPrice = trades.filter(t => !t.price);
      Logger.log(`--- "${subject}" (${msg.getDate()}) ---`);
      Logger.log(`  Parsed: ${JSON.stringify(trades)}`);
      if (missingPrice.length > 0) {
        Logger.log(`  WARNING: no fill price derived for ${missingPrice.map(t => t.ticker).join(', ')} — server would use TODAY's price`);
      }
      if (DRY_RUN) continue;

      try {
        const payload = {
          bot_username: config.WOLFF_BOT_USERNAME,
          trades: trades,
          source: 'public_backfill',  // ≤20 chars — stock_transaction.price_source is varchar(20)
          notes: (body || '').substring(0, 500),
          email_subject: subject,
          email_received_at: msg.getDate().toISOString(),
          email_message_id: msgId,
          suppress_notifications: true,
        };
        const resp = UrlFetchApp.fetch(`${config.API_BASE_URL}/admin/bot/email-trade`, {
          method: 'post',
          contentType: 'application/json',
          headers: { 'X-Cron-Secret': config.CRON_SECRET },
          payload: JSON.stringify(payload),
          muteHttpExceptions: true,
        });
        const result = JSON.parse(resp.getContentText());
        if (result.status === 'paused') {
          Logger.log('  ABORTING: email-trade ingestion is PAUSED server-side — unpause and re-run.');
          return;
        }
        if (result.status === 'duplicate') {
          Logger.log('  Already processed server-side; skipped (idempotent).');
          skipped++;
        } else if (resp.getResponseCode() === 200 && result.success) {
          submitted++;
          Logger.log(`  Submitted: ${result.trades_executed}/${result.trades_submitted} executed`);
          if (result.results) {
            for (const r of result.results) {
              if (r.error) Logger.log(`    ERROR ${r.ticker}: ${r.error}`);
              else Logger.log(`    OK ${r.ticker}: ${r.action} ${r.quantity} @ $${r.price}`);
            }
          }
        } else {
          failed++;
          Logger.log(`  API Error (${resp.getResponseCode()}): ${JSON.stringify(result)}`);
        }
      } catch (e) {
        failed++;
        Logger.log(`  ERROR submitting: ${e.message}`);
      }
    }
  }

  Logger.log(`\n=== BACKFILL ${DRY_RUN ? 'DRY RUN' : 'COMPLETE'}: ${seenIds.size} emails, ${submitted} submitted, ${skipped} skipped, ${failed} failed ===`);
}

/**
 * Like parseTradesFromEmail, but derives the fill price for Public's summary
 * format: "You bought $1,234.56 of TKR" + "Quantity: 12.345 shares"
 * → price = 1234.56 / 12.345. Backfill-only; the live path keeps omitting
 * price so trades execute at the moment's market price.
 */
function parseTradesWithFillPrices(plainBody, htmlBody) {
  const trades = [];
  const text = plainBody || htmlBody || '';
  let match;

  // "You bought $X of TKR" ... "Quantity: N shares" → price = X / N
  const summaryPattern = /You\s+(bought|sold)\s+\$([\d,.]+)\s+of\s+([A-Z]{1,5}(?:\.[A-Z]{1,2})?)/gi;
  while ((match = summaryPattern.exec(text)) !== null) {
    const action = match[1].toLowerCase() === 'bought' ? 'buy' : 'sell';
    const amount = parseFloat(match[2].replace(/,/g, ''));
    const ticker = match[3].toUpperCase();
    const qtyMatch = text.substring(match.index).match(/Quantity:\s*([\d,.]+)\s*shares?/i);
    const quantity = qtyMatch ? parseFloat(qtyMatch[1].replace(/,/g, '')) : null;
    if (quantity && !trades.some(t => t.ticker === ticker && t.action === action)) {
      const price = amount > 0 ? Math.round((amount / quantity) * 10000) / 10000 : null;
      trades.push({ action, ticker, quantity, price });
    }
  }

  // "You bought TKR at $X per share" ... "Quantity: N shares" — price explicit
  const perSharePattern = /You\s+(bought|sold)\s+([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s+at\s+\$?([\d,.]+)\s+per\s+share/gi;
  while ((match = perSharePattern.exec(text)) !== null) {
    const action = match[1].toLowerCase() === 'bought' ? 'buy' : 'sell';
    const ticker = match[2].toUpperCase();
    const price = parseFloat(match[3].replace(/,/g, ''));
    if (!trades.some(t => t.ticker === ticker && t.action === action)) {
      const qtyMatch = text.substring(match.index).match(/Quantity:\s*([\d,.]+)\s*shares?/i);
      const quantity = qtyMatch ? parseFloat(qtyMatch[1].replace(/,/g, '')) : 1;
      trades.push({ action, ticker, quantity, price });
    }
  }

  return trades;
}

/**
 * Diagnose: show all trade emails since a date and what the parser extracts.
 * Does NOT submit anything or mark anything — read-only.
 * Change the SINCE_DATE below before running.
 */
function diagnoseTrades() {
  const SINCE_DATE = '2026/03/28';  // ← Change this date as needed
  
  const threads = GmailApp.search(`from:mail.public.com after:${SINCE_DATE}`, 0, 50);
  Logger.log(`Found ${threads.length} threads from mail.public.com since ${SINCE_DATE}`);
  
  let emailCount = 0;
  let parsedCount = 0;
  
  for (const thread of threads) {
    for (const msg of thread.getMessages()) {
      emailCount++;
      const subject = msg.getSubject();
      const date = msg.getDate();
      const body = msg.getPlainBody();
      const htmlBody = msg.getBody();
      const isRead = !msg.isUnread();
      
      const trades = parseTradesFromEmail(body, htmlBody);
      
      Logger.log(`--- Email #${emailCount} ---`);
      Logger.log(`  Date: ${date}`);
      Logger.log(`  Subject: ${subject}`);
      Logger.log(`  Read: ${isRead}`);
      Logger.log(`  Body preview: ${(body || htmlBody || '').substring(0, 300)}`);
      Logger.log(`  Parsed trades: ${trades.length > 0 ? JSON.stringify(trades) : 'NONE'}`);
      
      if (trades.length > 0) parsedCount++;
    }
  }
  
  Logger.log(`\n=== SUMMARY: ${emailCount} emails found, ${parsedCount} had parseable trades ===`);
}
