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
 *    - ADMIN_API_KEY: your admin API key
 *    - API_BASE_URL: https://apestogether.ai/api/mobile
 *    - GROK_BOT_USERNAME: (the randomly generated bot username for Grok Portfolio)
 *    - WOLFF_BOT_USERNAME: (the randomly generated bot username for Wolff's Fund)
 * 4. Run setupTrigger() once to create the time-based trigger
 * 5. The script will check for new emails every 5 minutes
 */

// ── Configuration ──────────────────────────────────────────────────────────

function getConfig() {
  const props = PropertiesService.getScriptProperties();
  return {
    ADMIN_API_KEY: props.getProperty('ADMIN_API_KEY'),
    API_BASE_URL: props.getProperty('API_BASE_URL') || 'https://apestogether.ai/api/mobile',
    GROK_BOT_USERNAME: props.getProperty('GROK_BOT_USERNAME'),
    WOLFF_BOT_USERNAME: props.getProperty('WOLFF_BOT_USERNAME'),
  };
}

// ── Main Entry Point ───────────────────────────────────────────────────────

function checkForTradeEmails() {
  const config = getConfig();
  if (!config.ADMIN_API_KEY) {
    Logger.log('ERROR: ADMIN_API_KEY not configured');
    return;
  }

  // Search for unread Public.com trade notification emails
  // Broad queries — the API auto-detects which bot portfolio each email belongs to
  // by matching traded tickers against each bot's current holdings
  const queries = [
    'from:notifications@public.com subject:"rebalanced" is:unread',
    'from:notifications@public.com subject:"trade" is:unread',
    'from:notifications@public.com subject:"bought" is:unread',
    'from:notifications@public.com subject:"sold" is:unread',
    'from:notifications@public.com subject:"executed" is:unread',
    'from:notifications@public.com subject:"order" is:unread',
  ];

  let processedCount = 0;
  const processedIds = new Set(); // Avoid processing same message from multiple query matches

  for (const query of queries) {
    const threads = GmailApp.search(query, 0, 10);

    for (const thread of threads) {
      const messages = thread.getMessages();
      for (const message of messages) {
        if (message.isUnread() && !processedIds.has(message.getId())) {
          processedIds.add(message.getId());
          try {
            const result = processTradeEmail(message, config);
            if (result) {
              processedCount++;
              Logger.log(`Processed: ${message.getSubject()} → ${result.trades_executed} trades (auto-routed to ${result.bot_username})`);
            }
          } catch (e) {
            Logger.log(`ERROR processing "${message.getSubject()}": ${e.message}`);
          }
          // Mark as read regardless to avoid reprocessing
          message.markRead();
        }
      }
    }
  }

  Logger.log(`Processed ${processedCount} trade emails`);
}

// ── Email Parsing ──────────────────────────────────────────────────────────

function processTradeEmail(message, config) {
  const subject = message.getSubject();
  const body = message.getPlainBody();
  const htmlBody = message.getBody();

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

  // Submit trades to the API (auto-detection will route to correct bot)
  return submitTrades(config, botUsername, trades, source, body);
}

function parseTradesFromEmail(plainBody, htmlBody) {
  const trades = [];
  const text = plainBody || htmlBody || '';

  // Pattern 1: "Bought 10 shares of AAPL at $150.00"
  const boughtPattern = /(?:bought|purchased)\s+(\d+(?:\.\d+)?)\s+shares?\s+(?:of\s+)?([A-Z]{1,5})\s+(?:at\s+)?\$?([\d,.]+)/gi;
  let match;
  while ((match = boughtPattern.exec(text)) !== null) {
    trades.push({
      action: 'buy',
      ticker: match[2].toUpperCase(),
      quantity: parseFloat(match[1]),
      price: parseFloat(match[3].replace(',', ''))
    });
  }

  // Pattern 2: "Sold 10 shares of AAPL at $150.00"
  const soldPattern = /(?:sold|selling)\s+(\d+(?:\.\d+)?)\s+shares?\s+(?:of\s+)?([A-Z]{1,5})\s+(?:at\s+)?\$?([\d,.]+)/gi;
  while ((match = soldPattern.exec(text)) !== null) {
    trades.push({
      action: 'sell',
      ticker: match[2].toUpperCase(),
      quantity: parseFloat(match[1]),
      price: parseFloat(match[3].replace(',', ''))
    });
  }

  // Pattern 3: "BUY AAPL 10 @ $150" or "SELL AAPL 10 @ $150"
  const shortPattern = /(buy|sell)\s+([A-Z]{1,5})\s+(\d+(?:\.\d+)?)\s*(?:@|at)\s*\$?([\d,.]+)/gi;
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
  const tablePattern = /([A-Z]{1,5})\s*\|\s*(buy|sell|bought|sold)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*\$?([\d,.]+)/gi;
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
  const addedPattern = /(?:added|adding|new position:?)\s+([A-Z]{1,5})/gi;
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

  const removedPattern = /(?:removed|removing|exited|closed position:?)\s+([A-Z]{1,5})/gi;
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

function submitTrades(config, botUsername, trades, source, rawEmail) {
  const url = `${config.API_BASE_URL}/admin/bot/email-trade`;

  const payload = {
    bot_username: botUsername,
    trades: trades,
    source: source,
    notes: rawEmail.substring(0, 500) // Truncate for storage
  };

  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'X-Admin-Key': config.ADMIN_API_KEY
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(url, options);
  const status = response.getResponseCode();
  const body = JSON.parse(response.getContentText());

  if (status === 200 && body.success) {
    Logger.log(`API Success: ${body.trades_executed} trades executed for ${botUsername}`);
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
  const threads = GmailApp.search('from:notifications@public.com', 0, 1);
  if (threads.length > 0) {
    const message = threads[0].getMessages()[0];
    Logger.log(`Subject: ${message.getSubject()}`);
    Logger.log(`Body preview: ${message.getPlainBody().substring(0, 500)}`);

    const trades = parseTradesFromEmail(message.getPlainBody(), message.getBody());
    Logger.log(`Parsed trades: ${JSON.stringify(trades, null, 2)}`);
  } else {
    Logger.log('No matching emails found');
  }
}
