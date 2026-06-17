package com.apestogether.app.ui.screens.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.models.W9Request
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.Gains
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
import javax.inject.Inject

/**
 * In-app W-9 collection screen (Layer 1). Mirrors iOS `TaxInfoView`.
 *
 * Why this exists: creators must have a W-9 on file before we can release their
 * payouts (IRS 1099-NEC). The full TIN is forwarded to our accounting partner
 * (Xero) and is never persisted on ApesTogether's servers — see the backend
 * `POST /tax/w9`. On success, any held payouts for this creator are released.
 */

val W9_CLASSIFICATIONS: List<Pair<String, String>> = listOf(
    "individual_sole_prop" to "Individual / sole proprietor / single-member LLC",
    "c_corp" to "C corporation",
    "s_corp" to "S corporation",
    "partnership" to "Partnership",
    "trust" to "Trust / estate",
    "llc_c" to "LLC (taxed as C corp)",
    "llc_s" to "LLC (taxed as S corp)",
    "llc_p" to "LLC (taxed as partnership)",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaxInfoScreen(onClose: () -> Unit) {
    val viewModel: W9ViewModel = hiltViewModel()
    val ui by viewModel.ui.collectAsState()

    LaunchedEffect(Unit) { viewModel.loadStatus() }

    // Form field state lives in the composable; the VM only does load/submit.
    var legalName by remember { mutableStateOf("") }
    var businessName by remember { mutableStateOf("") }
    var classification by remember { mutableStateOf(W9_CLASSIFICATIONS.first().first) }
    var tinType by remember { mutableStateOf("ssn") }
    var tin by remember { mutableStateOf("") }
    var addr1 by remember { mutableStateOf("") }
    var addr2 by remember { mutableStateOf("") }
    var city by remember { mutableStateOf("") }
    var state by remember { mutableStateOf("") }
    var zip by remember { mutableStateOf("") }
    var certified by remember { mutableStateOf(false) }

    LaunchedEffect(ui.legalNamePrefill) {
        if (legalName.isEmpty() && !ui.legalNamePrefill.isNullOrEmpty()) {
            legalName = ui.legalNamePrefill!!
        }
    }

    val tinDigits = tin.filter { it.isDigit() }
    val canSubmit = legalName.isNotBlank() && tinDigits.length == 9 && certified &&
        addr1.isNotBlank() && city.isNotBlank() && state.isNotBlank() && zip.isNotBlank()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Tax Info (W-9)", color = TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onClose) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = TextSecondary)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = AppBackground),
            )
        },
        containerColor = AppBackground,
    ) { padding ->
        when {
            ui.loading -> Column(
                modifier = Modifier.fillMaxSize().padding(padding),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) { CircularProgressIndicator(color = PrimaryAccent) }

            ui.onFile -> Column(
                modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
            ) {
                Icon(Icons.Default.CheckCircle, contentDescription = null, tint = Gains)
                Text("W-9 on File", color = TextPrimary, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                ui.tinLast4?.let { Text("TIN ending in •••$it", color = TextSecondary, fontSize = 14.sp) }
                Text(
                    "Your payouts are cleared for payment. We never store your full SSN/EIN — it's held only by our accounting partner (Xero) for 1099 reporting.",
                    color = TextSecondary, fontSize = 12.sp,
                )
            }

            // We only collect a W-9 once a creator actually has a subscriber and
            // is due a payout — not from everyone.
            !ui.required -> Column(
                modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
            ) {
                Text("No tax info needed yet", color = TextPrimary, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text(
                    "We only collect a W-9 once you have your first paying subscriber and are due a payout. We'll prompt you here when that happens.",
                    color = TextSecondary, fontSize = 14.sp,
                )
            }

            else -> Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                if (ui.heldPayoutTotal > 0) {
                    Text(
                        "$%.2f in payouts is on hold until your W-9 is received.".format(ui.heldPayoutTotal),
                        color = TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    )
                }
                Text(
                    "We need your W-9 before we can pay you — the IRS requires it for creator payouts. Your full TIN is sent securely to our accounting partner (Xero) and is never stored on ApesTogether's servers.",
                    color = TextSecondary, fontSize = 13.sp,
                )

                W9Field("Full legal name (as on your tax return)", legalName) { legalName = it }
                W9Field("Business name (optional)", businessName) { businessName = it }

                Text("Federal tax classification", color = TextSecondary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                ClassificationDropdown(selected = classification, onSelect = { classification = it })

                Text("Taxpayer ID number", color = TextSecondary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                    SegmentedButton(
                        selected = tinType == "ssn",
                        onClick = { tinType = "ssn" },
                        shape = SegmentedButtonDefaults.itemShape(index = 0, count = 2),
                    ) { Text("SSN") }
                    SegmentedButton(
                        selected = tinType == "ein",
                        onClick = { tinType = "ein" },
                        shape = SegmentedButtonDefaults.itemShape(index = 1, count = 2),
                    ) { Text("EIN") }
                }
                W9Field(
                    if (tinType == "ssn") "SSN (9 digits)" else "EIN (9 digits)",
                    tin, KeyboardType.Number,
                ) { tin = it }

                Text("Mailing address", color = TextSecondary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                W9Field("Street address", addr1) { addr1 = it }
                W9Field("Apt / suite (optional)", addr2) { addr2 = it }
                W9Field("City", city) { city = it }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f)) { W9Field("State", state) { state = it } }
                    Column(Modifier.weight(1f)) { W9Field("ZIP", zip, KeyboardType.Number) { zip = it } }
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(checked = certified, onCheckedChange = { certified = it })
                    Spacer(Modifier.height(0.dp))
                    Text(
                        "Under penalties of perjury, I certify the information above is correct and that I am a U.S. person.",
                        color = TextSecondary, fontSize = 12.sp, modifier = Modifier.padding(start = 8.dp),
                    )
                }

                ui.error?.let { Text(it, color = Losses, fontSize = 12.sp) }

                Button(
                    onClick = {
                        viewModel.submit(
                            W9Request(
                                legalName = legalName.trim(),
                                businessName = businessName.trim().ifBlank { null },
                                taxClassification = classification,
                                tinType = tinType,
                                tin = tinDigits,
                                addressLine1 = addr1.trim(),
                                addressLine2 = addr2.trim().ifBlank { null },
                                city = city.trim(),
                                state = state.trim(),
                                postalCode = zip.trim(),
                                country = "US",
                                certified = true,
                            )
                        )
                    },
                    enabled = canSubmit && !ui.submitting,
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent, contentColor = AppBackground),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (ui.submitting) {
                        CircularProgressIndicator(color = AppBackground, modifier = Modifier.height(18.dp))
                        Spacer(Modifier.height(0.dp))
                    }
                    Text(if (ui.submitting) "Submitting…" else "Submit W-9", fontWeight = FontWeight.SemiBold)
                }

                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ClassificationDropdown(selected: String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val label = W9_CLASSIFICATIONS.firstOrNull { it.first == selected }?.second ?: selected
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = label,
            onValueChange = {},
            readOnly = true,
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.fillMaxWidth().menuAnchor(),
        )
        androidx.compose.material3.ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
        ) {
            W9_CLASSIFICATIONS.forEach { (value, text) ->
                DropdownMenuItem(
                    text = { Text(text) },
                    onClick = { onSelect(value); expanded = false },
                )
            }
        }
    }
}

@Composable
private fun W9Field(
    placeholder: String,
    value: String,
    keyboardType: KeyboardType = KeyboardType.Text,
    onValueChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        placeholder = { Text(placeholder, color = TextMuted, fontSize = 13.sp) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        modifier = Modifier.fillMaxWidth(),
    )
}

@HiltViewModel
class W9ViewModel @Inject constructor(
    private val apiService: ApiService,
) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val submitting: Boolean = false,
        val onFile: Boolean = false,
        val required: Boolean = false,
        val tinLast4: String? = null,
        val heldPayoutTotal: Double = 0.0,
        val legalNamePrefill: String? = null,
        val error: String? = null,
    )

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    fun loadStatus() {
        viewModelScope.launch {
            runCatching { apiService.getW9Status() }
                .onSuccess {
                    _ui.value = _ui.value.copy(
                        loading = false,
                        onFile = it.onFile,
                        required = it.required,
                        tinLast4 = it.tinLast4,
                        heldPayoutTotal = it.heldPayoutTotal,
                        legalNamePrefill = it.legalName,
                    )
                }
                .onFailure {
                    _ui.value = _ui.value.copy(loading = false, error = "Couldn't load your tax status. Please try again.")
                }
        }
    }

    fun submit(request: W9Request) {
        _ui.value = _ui.value.copy(submitting = true, error = null)
        viewModelScope.launch {
            runCatching { apiService.submitW9(request) }
                .onSuccess { resp ->
                    _ui.value = if (resp.onFile) {
                        _ui.value.copy(submitting = false, onFile = true, tinLast4 = resp.tinLast4)
                    } else {
                        _ui.value.copy(
                            submitting = false,
                            error = resp.message ?: "Saved, but syncing is still pending. We'll retry automatically.",
                        )
                    }
                }
                .onFailure {
                    _ui.value = _ui.value.copy(
                        submitting = false,
                        error = "Submission failed. Please check your details and try again.",
                    )
                }
        }
    }
}
