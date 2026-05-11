package com.apestogether.app.ui.screens.onboarding

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AddCircle
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.models.AddStocksRequest
import com.apestogether.app.data.models.StockEntry
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject

/**
 * "Add Your Stocks" screen. Direct port of iOS [AddStocksView].
 *
 * Two entry points:
 *  1. Onboarding — after [EarnNudgeScreen] when the user opts to
 *     "Add Your Stocks". `showSkip = true`, `headline = "Add Your Stocks"`.
 *  2. From the empty state on the MyPortfolio tab. Same defaults.
 *
 * Both flows POST to `/portfolio/stocks` (see
 * [ApiService.addStocks]) with a list of `{ticker, quantity}` pairs and
 * close themselves on success.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddStocksScreen(
    onComplete: () -> Unit,
    headline: String = "Add Your Stocks",
    subheadline: String = "Share your trades and earn from every subscriber",
    showSkip: Boolean = true,
    showBack: Boolean = false,
    onBack: () -> Unit = {},
) {
    val viewModel: AddStocksViewModel = hiltViewModel()
    val entries by viewModel.entries.collectAsState()
    val isSubmitting by viewModel.isSubmitting.collectAsState()
    val errorMessage by viewModel.error.collectAsState()
    val successCount by viewModel.successCount.collectAsState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(AppBackground),
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            if (showBack) {
                TopAppBar(
                    title = {},
                    navigationIcon = {
                        IconButton(onClick = onBack) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                                contentDescription = "Back",
                                tint = TextSecondary,
                            )
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = AppBackground,
                    ),
                )
            }

            // Header
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = if (showBack) 0.dp else 24.dp)
                    .padding(horizontal = 24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = headline,
                    color = TextPrimary,
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = subheadline,
                    color = TextSecondary,
                    fontSize = 14.sp,
                    textAlign = TextAlign.Center,
                )
            }

            // Stock-entry rows (scrollable)
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp)
                    .padding(top = 24.dp, bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                entries.forEach { draft ->
                    StockEntryRow(
                        draft = draft,
                        onTickerChange = { viewModel.updateTicker(draft.id, it) },
                        onQuantityChange = { viewModel.updateQuantity(draft.id, it) },
                        onDelete = if (entries.size > 1) {
                            { viewModel.removeEntry(draft.id) }
                        } else null,
                    )
                }

                // "Add another stock" button — dashed-style outline.
                Button(
                    onClick = { viewModel.addEntry() },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color.Transparent,
                        contentColor = PrimaryAccent,
                    ),
                    border = BorderStroke(1.dp, PrimaryAccent.copy(alpha = 0.3f)),
                    contentPadding = PaddingValues(vertical = 14.dp),
                ) {
                    Icon(
                        imageVector = Icons.Default.AddCircle,
                        contentDescription = null,
                        tint = PrimaryAccent,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "Add another stock",
                        color = PrimaryAccent,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }

            // Error message
            if (!errorMessage.isNullOrBlank()) {
                Text(
                    text = errorMessage.orEmpty(),
                    color = Losses,
                    fontSize = 12.sp,
                    modifier = Modifier
                        .padding(horizontal = 20.dp)
                        .padding(bottom = 8.dp),
                )
            }

            // Bottom CTAs
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 40.dp)
                    .padding(bottom = 40.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                val canSubmit = viewModel.hasValidEntries() && !isSubmitting
                Button(
                    onClick = { viewModel.submit() },
                    enabled = canSubmit,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(54.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = PrimaryAccent,
                        disabledContainerColor = PrimaryAccent.copy(alpha = 0.4f),
                    ),
                ) {
                    if (isSubmitting) {
                        CircularProgressIndicator(
                            color = AppBackground,
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(20.dp),
                        )
                    } else {
                        Text(
                            "Save Stocks",
                            color = AppBackground,
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }

                if (showSkip) {
                    TextButton(onClick = onComplete) {
                        Text(
                            "I'll do this later",
                            color = TextSecondary,
                            fontSize = 14.sp,
                        )
                    }
                }
            }
        }
    }

    // Success alert
    val count = successCount
    if (count != null) {
        AlertDialog(
            onDismissRequest = {
                viewModel.clearSuccess()
                onComplete()
            },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.clearSuccess()
                    onComplete()
                }) {
                    Text("Continue", color = PrimaryAccent, fontWeight = FontWeight.Bold)
                }
            },
            title = { Text("Stocks Added!", color = TextPrimary, fontWeight = FontWeight.Bold) },
            text = {
                Text(
                    "$count stock${if (count == 1) "" else "s"} added to your portfolio.",
                    color = TextSecondary,
                )
            },
            containerColor = CardBackground,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StockEntryRow(
    draft: StockDraft,
    onTickerChange: (String) -> Unit,
    onQuantityChange: (String) -> Unit,
    onDelete: (() -> Unit)?,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        OutlinedTextField(
            value = draft.ticker,
            onValueChange = { onTickerChange(it.uppercase()) },
            singleLine = true,
            placeholder = { Text("AAPL", color = TextMuted) },
            textStyle = TextStyle(
                color = TextPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
            ),
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = CardBackground,
                unfocusedContainerColor = CardBackground,
                disabledContainerColor = CardBackground,
                focusedBorderColor = PrimaryAccent,
                unfocusedBorderColor = CardBorder,
                cursorColor = PrimaryAccent,
            ),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.weight(1f),
        )

        OutlinedTextField(
            value = draft.quantity,
            onValueChange = onQuantityChange,
            singleLine = true,
            placeholder = { Text("Shares", color = TextMuted) },
            textStyle = TextStyle(
                color = TextPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
            ),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = CardBackground,
                unfocusedContainerColor = CardBackground,
                disabledContainerColor = CardBackground,
                focusedBorderColor = PrimaryAccent,
                unfocusedBorderColor = CardBorder,
                cursorColor = PrimaryAccent,
            ),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.width(110.dp),
        )

        if (onDelete != null) {
            IconButton(onClick = onDelete) {
                Icon(
                    imageVector = Icons.Default.Cancel,
                    contentDescription = "Remove",
                    tint = TextMuted,
                )
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// State + ViewModel
// ─────────────────────────────────────────────────────────────────────────

data class StockDraft(
    val id: String = UUID.randomUUID().toString(),
    val ticker: String = "",
    val quantity: String = "",
)

@HiltViewModel
class AddStocksViewModel @Inject constructor(
    private val apiService: ApiService,
) : ViewModel() {

    private val _entries = MutableStateFlow(listOf(StockDraft()))
    val entries: StateFlow<List<StockDraft>> = _entries.asStateFlow()

    private val _isSubmitting = MutableStateFlow(false)
    val isSubmitting: StateFlow<Boolean> = _isSubmitting.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _successCount = MutableStateFlow<Int?>(null)
    val successCount: StateFlow<Int?> = _successCount.asStateFlow()

    fun addEntry() {
        _entries.value = _entries.value + StockDraft()
    }

    fun removeEntry(id: String) {
        _entries.value = _entries.value.filterNot { it.id == id }
            .ifEmpty { listOf(StockDraft()) }
    }

    fun updateTicker(id: String, ticker: String) {
        _entries.value = _entries.value.map {
            if (it.id == id) it.copy(ticker = ticker) else it
        }
    }

    fun updateQuantity(id: String, quantity: String) {
        // Allow only digits + at most one decimal point.
        val sanitized = quantity.filter { it.isDigit() || it == '.' }
            .let { s ->
                val firstDot = s.indexOf('.')
                if (firstDot < 0) s
                else s.substring(0, firstDot + 1) +
                    s.substring(firstDot + 1).replace(".", "")
            }
        _entries.value = _entries.value.map {
            if (it.id == id) it.copy(quantity = sanitized) else it
        }
    }

    fun hasValidEntries(): Boolean = _entries.value.any {
        it.ticker.trim().isNotEmpty() && it.quantity.trim().isNotEmpty()
    }

    fun submit() {
        viewModelScope.launch {
            _isSubmitting.value = true
            _error.value = null

            val valid = _entries.value.mapNotNull { draft ->
                val ticker = draft.ticker.trim().uppercase()
                val qty = draft.quantity.trim().toDoubleOrNull()
                if (ticker.isNotEmpty() && qty != null && qty > 0) {
                    StockEntry(ticker = ticker, quantity = qty)
                } else null
            }

            if (valid.isEmpty()) {
                _error.value = "Please enter at least one valid ticker + share quantity."
                _isSubmitting.value = false
                return@launch
            }

            runCatching { apiService.addStocks(AddStocksRequest(stocks = valid)) }
                .onSuccess { resp ->
                    if (resp.success) {
                        _successCount.value = resp.addedCount
                    } else {
                        _error.value = resp.errors?.firstOrNull()
                            ?: "Server rejected the submission."
                    }
                }
                .onFailure { e ->
                    _error.value = e.message ?: "Couldn't reach the server. Try again."
                }

            _isSubmitting.value = false
        }
    }

    fun clearSuccess() {
        _successCount.value = null
    }
}
