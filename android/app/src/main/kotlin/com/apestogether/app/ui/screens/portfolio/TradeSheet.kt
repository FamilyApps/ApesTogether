package com.apestogether.app.ui.screens.portfolio

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.apestogether.app.data.models.Holding
import com.apestogether.app.ui.components.findActivity
import com.apestogether.app.util.ReviewPrompter
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Gains
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.floor

/**
 * Buy / Sell trade flow. Compose port of iOS `TradeSheetView.swift`.
 *
 * Used by the owner of a portfolio to record a trade. The execution price is
 * authoritative server-side (`/portfolio/trade` ignores any client price), so
 * the price shown here is for the estimated-total display only.
 *
 * Two entry shapes:
 *  - **General buy** ([tickerEditable] = true): a ticker input is shown, the
 *    Buy/Sell toggle is hidden (you can't sell a ticker we don't know you hold).
 *  - **Specific holding** ([tickerEditable] = false): ticker is fixed, a Buy/Sell
 *    toggle is shown, and [heldQuantity] drives sell validation + the % buttons.
 */
enum class TradeType(val display: String) { BUY("Buy"), SELL("Sell") }

sealed interface TradeOutcome {
    /** [pending] = true when the trade was queued after-hours to settle at open. */
    data class Success(val pending: Boolean) : TradeOutcome
    data class Error(val message: String) : TradeOutcome
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TradeSheet(
    initialTicker: String,
    initialType: TradeType,
    tickerEditable: Boolean,
    heldQuantity: Double,
    onFetchPrice: suspend (String) -> Double?,
    onSubmit: suspend (ticker: String, qty: Double, type: TradeType) -> TradeOutcome,
    onDismiss: () -> Unit,
    onTraded: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    var type by remember { mutableStateOf(initialType) }
    var ticker by remember { mutableStateOf(initialTicker) }
    var quantity by remember { mutableStateOf("") }
    var price by remember { mutableStateOf(0.0) }
    var loadingPrice by remember { mutableStateOf(false) }
    var submitting by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var success by remember { mutableStateOf(false) }
    var pending by remember { mutableStateOf(false) }

    // Auto-fetch the market price whenever the ticker changes. Debounce when the
    // user is typing a new ticker so we don't fire a request per keystroke.
    LaunchedEffect(ticker) {
        val t = ticker.trim()
        if (t.isEmpty()) {
            price = 0.0
            loadingPrice = false
            return@LaunchedEffect
        }
        if (tickerEditable) delay(450)
        loadingPrice = true
        price = onFetchPrice(t) ?: 0.0
        loadingPrice = false
    }

    val accent = if (type == TradeType.BUY) Gains else Losses
    val qtyValue = quantity.toDoubleOrNull() ?: 0.0
    val canSubmit = ticker.trim().isNotEmpty() && qtyValue > 0 && price > 0 && !submitting && !success

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = AppBackground,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(
                modifier = Modifier
                    .size(56.dp)
                    .clip(CircleShape)
                    .background(accent.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (type == TradeType.BUY) Icons.Default.Add else Icons.Default.Remove,
                    contentDescription = null,
                    tint = accent,
                )
            }
            Spacer(Modifier.height(8.dp))
            Text(
                text = if (ticker.isBlank()) type.display else "${type.display} ${ticker.uppercase()}",
                color = TextPrimary,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
            )
            if (type == TradeType.SELL && heldQuantity > 0) {
                Text("${formatShares(heldQuantity)} shares available", color = TextMuted, fontSize = 12.sp)
            }
            Spacer(Modifier.height(20.dp))

            // Buy/Sell toggle — only for a specific held ticker.
            if (!tickerEditable) {
                SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                    SegmentedButton(
                        selected = type == TradeType.BUY,
                        onClick = { type = TradeType.BUY; error = null },
                        shape = SegmentedButtonDefaults.itemShape(index = 0, count = 2),
                    ) { Text("Buy") }
                    SegmentedButton(
                        selected = type == TradeType.SELL,
                        onClick = { type = TradeType.SELL; error = null },
                        shape = SegmentedButtonDefaults.itemShape(index = 1, count = 2),
                    ) { Text("Sell") }
                }
                Spacer(Modifier.height(16.dp))
            }

            // Ticker input — general buy only.
            if (tickerEditable) {
                FieldLabel("Ticker")
                OutlinedTextField(
                    value = ticker,
                    onValueChange = {
                        ticker = it.uppercase().filter { c -> c.isLetterOrDigit() || c == '.' }.take(10)
                        error = null
                    },
                    singleLine = true,
                    placeholder = { Text("AAPL", color = TextMuted) },
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(16.dp))
            }

            // Market price (auto-fetched).
            FieldLabel("Market Price")
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(CardBackground)
                    .border(
                        1.dp,
                        if (price > 0) PrimaryAccent.copy(alpha = 0.3f) else CardBorder,
                        RoundedCornerShape(12.dp),
                    )
                    .padding(horizontal = 16.dp, vertical = 14.dp),
            ) {
                when {
                    loadingPrice -> Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(modifier = Modifier.size(16.dp), color = PrimaryAccent, strokeWidth = 2.dp)
                        Spacer(Modifier.width(8.dp))
                        Text("Fetching price…", color = TextMuted, fontSize = 14.sp)
                    }
                    price > 0 -> Text(
                        "$" + "%.2f".format(price),
                        color = PrimaryAccent,
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    else -> Text("Price unavailable", color = Losses, fontSize = 14.sp)
                }
            }
            Spacer(Modifier.height(16.dp))

            // Quantity.
            FieldLabel("Quantity")
            OutlinedTextField(
                value = quantity,
                onValueChange = { quantity = sanitizeQty(it); error = null },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                placeholder = { Text("0", color = TextMuted) },
                modifier = Modifier.fillMaxWidth(),
            )

            if (qtyValue > 0 && price > 0) {
                Spacer(Modifier.height(10.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Estimated total", color = TextSecondary, fontSize = 14.sp)
                    Text("$" + "%.2f".format(qtyValue * price), color = TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                }
            }

            // Quick-quantity buttons for selling.
            if (type == TradeType.SELL && heldQuantity > 0) {
                Spacer(Modifier.height(14.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    listOf("25%" to 0.25, "50%" to 0.5, "75%" to 0.75, "All" to 1.0).forEach { (label, pct) ->
                        OutlinedButton(
                            onClick = {
                                val q = floor(heldQuantity * pct)
                                quantity = if (q == floor(q)) q.toLong().toString() else q.toString()
                            },
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(vertical = 8.dp),
                        ) { Text(label, fontSize = 12.sp, color = TextSecondary) }
                    }
                }
            }

            error?.let {
                Spacer(Modifier.height(12.dp))
                Text(it, color = Losses, fontSize = 13.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            }

            Spacer(Modifier.height(20.dp))

            Button(
                onClick = {
                    val q = quantity.toDoubleOrNull()
                    when {
                        q == null || q <= 0 -> error = "Enter a valid quantity"
                        price <= 0 -> error = "Price unavailable. Please try again."
                        type == TradeType.SELL && heldQuantity > 0 && q > heldQuantity ->
                            error = "You only have ${formatShares(heldQuantity)} shares"
                        else -> {
                            error = null
                            submitting = true
                            scope.launch {
                                when (val outcome = onSubmit(ticker.trim().uppercase(), q, type)) {
                                    is TradeOutcome.Success -> {
                                        pending = outcome.pending
                                        success = true
                                        onTraded()
                                        delay(if (pending) 1200 else 800)
                                        sheetState.hide()
                                        onDismiss()
                                        // After the sheet is gone (mirrors iOS's 1s-delayed
                                        // SKStoreReviewController call on the 3rd trade).
                                        context.findActivity()?.let { ReviewPrompter.onSuccessfulTrade(it) }
                                    }
                                    is TradeOutcome.Error -> {
                                        error = outcome.message
                                        submitting = false
                                    }
                                }
                            }
                        }
                    }
                },
                enabled = canSubmit,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = if (success) Gains else accent),
            ) {
                if (submitting && !success) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                }
                Text(
                    text = when {
                        success && pending -> "Queued for open"
                        success -> "Done!"
                        ticker.isBlank() -> type.display
                        else -> "${type.display} ${ticker.uppercase()}"
                    },
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                )
            }

            Spacer(Modifier.height(12.dp))

            TextButton(onClick = { openEmailTrade(context, type, ticker, quantity) }) {
                Icon(Icons.Default.Email, contentDescription = null, tint = PrimaryAccent, modifier = Modifier.size(14.dp))
                Spacer(Modifier.width(6.dp))
                Text(
                    "Submit trades via email",
                    color = PrimaryAccent,
                    fontSize = 13.sp,
                    textDecoration = TextDecoration.Underline,
                )
            }
        }
    }
}

/**
 * Bottom sheet that lists the owner's holdings so they can pick one to sell.
 * Mirrors iOS `SellPickerSheet`. On select, the parent opens [TradeSheet] in
 * SELL mode for the chosen ticker.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SellPickerSheet(
    holdings: List<Holding>,
    onSelect: (Holding) -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = AppBackground,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
        ) {
            Text("Sell a holding", color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Text("Pick a position to sell", color = TextMuted, fontSize = 13.sp)
            Spacer(Modifier.height(12.dp))
            if (holdings.isEmpty()) {
                Text("You don't have any holdings to sell yet.", color = TextSecondary, fontSize = 14.sp)
            } else {
                holdings.forEach { h ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .clickable { onSelect(h) }
                            .padding(vertical = 12.dp, horizontal = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(
                            modifier = Modifier
                                .size(40.dp)
                                .clip(RoundedCornerShape(8.dp))
                                .background(Losses.copy(alpha = 0.12f)),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(h.ticker.take(2), color = Losses, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(h.ticker, color = TextPrimary, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                            Text("${h.formattedQuantity} shares", color = TextSecondary, fontSize = 12.sp)
                        }
                        Icon(Icons.Default.Remove, contentDescription = null, tint = Losses, modifier = Modifier.size(18.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun FieldLabel(text: String) {
    Text(
        text = text,
        color = TextMuted,
        fontSize = 12.sp,
        fontWeight = FontWeight.SemiBold,
        textAlign = TextAlign.Start,
        modifier = Modifier.fillMaxWidth(),
    )
    Spacer(Modifier.height(6.dp))
}

/** Keep only digits + a single decimal point. Mirrors AddStocks' sanitizer. */
private fun sanitizeQty(input: String): String {
    val filtered = input.filter { it.isDigit() || it == '.' }
    val firstDot = filtered.indexOf('.')
    return if (firstDot < 0) filtered
    else filtered.substring(0, firstDot + 1) + filtered.substring(firstDot + 1).replace(".", "")
}

private fun formatShares(q: Double): String =
    if (q == floor(q) && q >= 1) q.toLong().toString()
    else "%.4f".format(q).trimEnd('0').trimEnd('.')

/**
 * Opens the mail composer pre-filled for the email-to-trade pipeline
 * (`trade@trade.apestogether.ai`). Mirrors iOS `openEmailTrade`.
 */
private fun openEmailTrade(context: Context, type: TradeType, ticker: String, qty: String) {
    val q = qty.ifBlank { "___" }
    val tk = ticker.ifBlank { "TICKER" }.uppercase()
    val subject = "${type.display.uppercase()} $q $tk"
    val body = buildString {
        appendLine("${type.display.uppercase()} $q $tk")
        appendLine()
        appendLine("Tip: Put one trade per line to submit multiple trades at once.")
        appendLine("Example:")
        appendLine("BUY 10 AAPL")
        appendLine("SELL 5 TSLA")
        append("BUY 20 MSFT")
    }
    val uri = Uri.parse(
        "mailto:trade@trade.apestogether.ai" +
            "?subject=" + Uri.encode(subject) +
            "&body=" + Uri.encode(body),
    )
    runCatching { context.startActivity(Intent(Intent.ACTION_SENDTO, uri)) }
}
