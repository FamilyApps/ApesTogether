package com.apestogether.app.ui.screens.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.automirrored.filled.Help
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.auth.AuthRepository
import com.apestogether.app.data.models.UpdatePortfolioPreferencesRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Settings screen. Direct port of iOS [SettingsView]. Sections (top → bottom):
 *
 *  - **Account** — read-only email + username.
 *  - **Your Portfolio Link** — personal `apestogether.ai/p/<slug>` URL
 *    with a Copy button that flips to "Copied!" for 2 seconds.
 *  - **Preferences** — "Allow Subscribers" toggle (frontend-only for v1;
 *    matches iOS which doesn't yet round-trip this to the backend).
 *  - **Payments** — Payment History (TODO) + Tax Info (TODO; iOS opens a
 *    W-9 sheet which is deferred to v1.1).
 *  - **Help & Legal** — FAQ (TODO), Terms of Service + Privacy Policy
 *    (open the marketing site in the browser), Contact Support (mailto),
 *    Web Dashboard (https://apestogether.ai).
 *  - **Sign Out** — red bordered button with a confirmation dialog.
 *  - **Delete Account** — muted text button with a destructive
 *    confirmation dialog that calls DELETE /auth/account then signs out.
 *  - **Version footer**.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onSignedOut: () -> Unit,
) {
    val viewModel: SettingsViewModel = hiltViewModel()
    val user by viewModel.currentUser.collectAsState()
    val preferFractional by viewModel.preferFractional.collectAsState()
    val preferFractionalLoaded by viewModel.preferFractionalLoaded.collectAsState()
    val context = LocalContext.current

    var allowSubscribers by remember { mutableStateOf(true) }
    var showSignOutConfirm by remember { mutableStateOf(false) }
    var showDeleteConfirm by remember { mutableStateOf(false) }
    var urlCopied by remember { mutableStateOf(false) }

    val personalURL = remember(user?.portfolioSlug) {
        user?.portfolioSlug?.let { "https://apestogether.ai/p/$it" } ?: "https://apestogether.ai"
    }

    // Auto-revert the "Copied!" label after 2s, matching iOS.
    LaunchedEffect(urlCopied) {
        if (urlCopied) {
            delay(2000)
            urlCopied = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text("Settings", color = TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Close",
                            tint = TextSecondary,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = AppBackground),
            )
        },
        containerColor = AppBackground,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            // ── Account ──
            SettingsSection(title = "Account") {
                user?.let { u ->
                    SettingsRow(label = "Email", value = u.email)
                    Divider()
                    SettingsRow(label = "Username", value = u.username)
                }
            }

            // ── Portfolio Link ──
            SettingsSection(title = "Your Portfolio Link") {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = personalURL,
                        color = PrimaryAccent,
                        fontSize = 12.sp,
                        modifier = Modifier.weight(1f),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    CopyButton(
                        copied = urlCopied,
                        onClick = {
                            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                            clipboard.setPrimaryClip(ClipData.newPlainText("Portfolio URL", personalURL))
                            urlCopied = true
                        }
                    )
                }
            }

            // ── Preferences ──
            SettingsSection(title = "Preferences") {
                ToggleRow(
                    icon = Icons.Default.People,
                    label = "Allow Subscribers",
                    checked = allowSubscribers,
                    onChange = { allowSubscribers = it },
                )
                Divider()
                // Phase D: persists to /settings/portfolio-preferences and
                // controls whether scaled subscriber views show fractional
                // shares (5 decimals) or floor to whole shares.
                ToggleRowWithSubtitle(
                    icon = Icons.Default.PieChart,
                    label = "Show Fractional Shares",
                    subtitle = "In scaled portfolio views",
                    checked = preferFractional,
                    enabled = preferFractionalLoaded,
                    onChange = { viewModel.setPreferFractional(it) },
                )
            }

            // ── Payments ──
            SettingsSection(title = "Payments") {
                NavRow(
                    icon = Icons.Default.History,
                    label = "Payment History",
                    onClick = { /* TODO: payment history screen */ },
                )
                Divider()
                NavRow(
                    icon = Icons.Default.Receipt,
                    label = "Tax Info",
                    onClick = { /* TODO: W-9 / tax info sheet */ },
                )
            }

            // ── Help & Legal ──
            SettingsSection(title = "Help & Legal") {
                NavRow(
                    icon = Icons.AutoMirrored.Filled.Help,
                    label = "FAQ",
                    onClick = { openUrl(context, "https://apestogether.ai/#faq") },
                )
                Divider()
                NavRow(
                    icon = Icons.Default.Description,
                    label = "Terms of Service",
                    onClick = { openUrl(context, "https://apestogether.ai/terms-of-service") },
                )
                Divider()
                NavRow(
                    icon = Icons.Default.Shield,
                    label = "Privacy Policy",
                    onClick = { openUrl(context, "https://apestogether.ai/privacy-policy") },
                )
                Divider()
                NavRow(
                    icon = Icons.Default.Email,
                    label = "Contact Support",
                    onClick = { openMailTo(context, "support@apestogether.ai") },
                )
                Divider()
                NavRow(
                    icon = Icons.Default.Public,
                    label = "Web Dashboard",
                    onClick = { openUrl(context, "https://apestogether.ai") },
                )
            }

            // ── Sign Out ──
            SignOutButton(onClick = { showSignOutConfirm = true })

            // ── Delete Account ──
            Text(
                text = "Delete Account",
                color = TextMuted,
                fontSize = 13.sp,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { showDeleteConfirm = true }
                    .padding(8.dp),
            )

            // ── Version ──
            Text(
                text = "Version 1.0",
                color = TextMuted,
                fontSize = 11.sp,
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(24.dp))
        }
    }

    // ── Sign Out confirm ──
    if (showSignOutConfirm) {
        AlertDialog(
            onDismissRequest = { showSignOutConfirm = false },
            title = { Text("Sign Out", color = TextPrimary) },
            text = { Text("Are you sure you want to sign out?", color = TextSecondary) },
            confirmButton = {
                TextButton(onClick = {
                    showSignOutConfirm = false
                    viewModel.signOut()
                    onSignedOut()
                }) {
                    Text("Sign Out", color = Losses)
                }
            },
            dismissButton = {
                TextButton(onClick = { showSignOutConfirm = false }) {
                    Text("Cancel", color = TextSecondary)
                }
            },
            containerColor = CardBackground,
        )
    }

    // ── Delete Account confirm ──
    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text("Delete Account", color = TextPrimary) },
            text = {
                Text(
                    "This will permanently delete your account, portfolio data, and all subscriptions. This action cannot be undone.",
                    color = TextSecondary,
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    showDeleteConfirm = false
                    viewModel.deleteAccount(onComplete = onSignedOut)
                }) {
                    Text("Delete", color = Losses)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) {
                    Text("Cancel", color = TextSecondary)
                }
            },
            containerColor = CardBackground,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Building blocks (mirror SectionHeader + cardStyle from iOS DesignSystem)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun SettingsSection(
    title: String,
    content: @Composable () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(title, color = TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold)
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(CardBackground)
                .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp)),
        ) {
            content()
        }
    }
}

@Composable
private fun SettingsRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = TextPrimary, fontSize = 14.sp)
        Spacer(Modifier.weight(1f))
        Text(
            value,
            color = TextSecondary,
            fontSize = 13.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun NavRow(icon: ImageVector, label: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = PrimaryAccent, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(12.dp))
        Text(label, color = TextPrimary, fontSize = 14.sp)
        Spacer(Modifier.weight(1f))
        Icon(
            imageVector = Icons.Default.ChevronRight,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(16.dp),
        )
    }
}

@Composable
private fun ToggleRow(
    icon: ImageVector,
    label: String,
    checked: Boolean,
    onChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = PrimaryAccent, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(12.dp))
        Text(label, color = TextPrimary, fontSize = 14.sp)
        Spacer(Modifier.weight(1f))
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = AppBackground,
                checkedTrackColor = PrimaryAccent,
                uncheckedThumbColor = TextMuted,
                uncheckedTrackColor = CardBorder,
                uncheckedBorderColor = CardBorder,
            ),
        )
    }
}

/** ToggleRow variant with a subtitle line, used for Phase D's "Show
 *  Fractional Shares" preference (the subtitle clarifies it only
 *  applies inside scaled portfolio views). */
@Composable
private fun ToggleRowWithSubtitle(
    icon: ImageVector,
    label: String,
    subtitle: String,
    checked: Boolean,
    enabled: Boolean,
    onChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = PrimaryAccent, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(label, color = TextPrimary, fontSize = 14.sp)
            Text(subtitle, color = TextMuted, fontSize = 11.sp)
        }
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            enabled = enabled,
            colors = SwitchDefaults.colors(
                checkedThumbColor = AppBackground,
                checkedTrackColor = PrimaryAccent,
                uncheckedThumbColor = TextMuted,
                uncheckedTrackColor = CardBorder,
                uncheckedBorderColor = CardBorder,
            ),
        )
    }
}

@Composable
private fun Divider() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(0.5.dp)
            .background(CardBorder)
    )
}

@Composable
private fun CopyButton(copied: Boolean, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(PrimaryAccent)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(
            imageVector = if (copied) Icons.Default.Check else Icons.Default.ContentCopy,
            contentDescription = null,
            tint = AppBackground,
            modifier = Modifier.size(12.dp),
        )
        Text(
            text = if (copied) "Copied!" else "Copy",
            color = AppBackground,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun SignOutButton(onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(1.dp, Losses.copy(alpha = 0.5f), RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        Icon(
            imageVector = Icons.AutoMirrored.Filled.Logout,
            contentDescription = null,
            tint = Losses,
            modifier = Modifier.size(18.dp),
        )
        Spacer(Modifier.width(8.dp))
        Text("Sign Out", color = Losses, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

private fun openUrl(context: Context, url: String) {
    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
    runCatching { context.startActivity(intent) }
}

private fun openMailTo(context: Context, address: String) {
    val intent = Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:$address"))
    runCatching { context.startActivity(intent) }
}

// ─────────────────────────────────────────────────────────────────────────
// ViewModel
// ─────────────────────────────────────────────────────────────────────────

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val apiService: ApiService,
) : ViewModel() {
    val currentUser = authRepository.currentUser

    // ── Phase D: portfolio display preferences ───────────────────────
    // `preferFractional` is the cached current value, `*Loaded` flips
    // to true after the initial GET completes so the UI can disable
    // the toggle while we're still hydrating. Default true matches the
    // server-side default in `_get_prefer_fractional`.
    private val _preferFractional = MutableStateFlow(true)
    val preferFractional: StateFlow<Boolean> = _preferFractional.asStateFlow()

    private val _preferFractionalLoaded = MutableStateFlow(false)
    val preferFractionalLoaded: StateFlow<Boolean> = _preferFractionalLoaded.asStateFlow()

    init {
        viewModelScope.launch {
            runCatching { apiService.getPortfolioPreferences() }
                .onSuccess { _preferFractional.value = it.preferFractional }
            // Always flip the loaded flag — even on failure — so the
            // toggle becomes interactive (with the default value).
            _preferFractionalLoaded.value = true
        }
    }

    /** Optimistically flip the local state, then PUT to the server.
     *  Rolls back the local state on failure so it stays in sync. */
    fun setPreferFractional(value: Boolean) {
        val previous = _preferFractional.value
        _preferFractional.value = value
        viewModelScope.launch {
            runCatching {
                apiService.updatePortfolioPreferences(
                    UpdatePortfolioPreferencesRequest(preferFractional = value)
                )
            }.onFailure {
                // Roll back on network/server error.
                _preferFractional.value = previous
            }
        }
    }

    fun signOut() {
        viewModelScope.launch { authRepository.signOut() }
    }

    /**
     * Calls DELETE /auth/account then signs the user out locally. We
     * always sign out even if the server call fails so a stale auth token
     * doesn't keep the user trapped in the app — matches iOS behavior.
     */
    fun deleteAccount(onComplete: () -> Unit) {
        viewModelScope.launch {
            runCatching { apiService.deleteAccount() }
            authRepository.signOut()
            onComplete()
        }
    }
}
