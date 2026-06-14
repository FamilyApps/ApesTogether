package com.apestogether.app.ui.screens.subscriptions

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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.NotificationsOff
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material.icons.filled.StarOutline
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.models.NotificationItem
import com.apestogether.app.data.models.Subscriber
import com.apestogether.app.data.models.SubscriptionMade
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Gains
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import javax.inject.Inject

/**
 * Subscriptions tab. Direct port of iOS [SubscriptionsView]. Three sections:
 *
 *  1. **My Subscribers** — creators see their subscriber count + per-row
 *     "Since {date}" entries.
 *  2. **My Subscriptions** — subscribers see active subs as cards with
 *     status badge, expiration, push toggle, View Portfolio + Cancel CTAs.
 *  3. **Trade Alerts** — combined push + email notification history with
 *     relative timestamps.
 *
 * The Cancel CTA opens a confirmation dialog (matching iOS `.alert`). Push
 * toggle persists via `PUT /notifications/settings`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SubscriptionsScreen(
    modifier: Modifier = Modifier,
    onOpenPortfolio: (String) -> Unit,
) {
    val viewModel: SubscriptionsViewModel = hiltViewModel()
    val state by viewModel.state.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()

    // Refresh on every resume — initial load, returning to this tab, AND coming
    // back from the background (e.g. after tapping a trade-alert push). Because
    // refresh() is silent once data exists, this updates Trade Alerts in place
    // with no spinner flash, so new alerts appear without a manual pull.
    LifecycleResumeEffect(Unit) {
        viewModel.refresh()
        onPauseOrDispose { }
    }

    var pendingCancelId by remember { mutableStateOf<Int?>(null) }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(AppBackground),
    ) {
        when (val s = state) {
            SubsState.Loading -> CircularProgressIndicator(
                color = PrimaryAccent,
                modifier = Modifier.align(Alignment.Center),
            )

            is SubsState.Error -> Text(
                text = s.message,
                color = TextSecondary,
                modifier = Modifier.align(Alignment.Center).padding(24.dp),
            )

            is SubsState.Loaded -> PullToRefreshBox(
                isRefreshing = isRefreshing,
                onRefresh = { viewModel.refresh(manual = true) },
                modifier = Modifier.fillMaxSize(),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(24.dp),
                ) {
                    SubscribersSection(s.subscribers, s.subscriberCount)

                    SubscriptionsSection(
                        subscriptions = s.subscriptions,
                        onTogglePush = { id, enabled -> viewModel.togglePush(id, enabled) },
                        onCancel = { id -> pendingCancelId = id },
                        onOpenPortfolio = onOpenPortfolio,
                    )

                    NotificationsSection(s.notifications)
                }
            }
        }
    }

    pendingCancelId?.let { id ->
        val context = LocalContext.current
        AlertDialog(
            onDismissRequest = { pendingCancelId = null },
            title = { Text("Cancel Subscription", color = TextPrimary) },
            text = {
                Text(
                    "You'll lose access to this trader's portfolio and trade alerts. To stop future billing, you'll also need to cancel in your Google Play subscriptions.",
                    color = TextSecondary,
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.cancel(id)
                        runCatching {
                            context.startActivity(
                                Intent(
                                    Intent.ACTION_VIEW,
                                    Uri.parse(
                                        "https://play.google.com/store/account/subscriptions?package=${context.packageName}"
                                    ),
                                )
                            )
                        }
                        pendingCancelId = null
                    }
                ) {
                    Text("Cancel", color = PrimaryAccent)
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingCancelId = null }) {
                    Text("Keep Subscription", color = TextSecondary)
                }
            },
            containerColor = CardBackground,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Subscribers (creators)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun SubscribersSection(
    subscribers: List<Subscriber>,
    count: Int,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("My Subscribers", color = TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            Text("$count", color = PrimaryAccent, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        }

        if (subscribers.isEmpty()) {
            EmptyCard(
                icon = Icons.Default.PersonAdd,
                title = "No subscribers yet",
                body = "Share your portfolio to attract subscribers",
            )
        } else {
            CardColumn {
                subscribers.forEachIndexed { idx, sub ->
                    SubscriberRow(sub)
                    if (idx < subscribers.size - 1) AccentRowDivider()
                }
            }
        }
    }
}

@Composable
private fun SubscriberRow(sub: Subscriber) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = Icons.Default.AccountCircle,
            contentDescription = null,
            tint = PrimaryAccent,
            modifier = Modifier.size(28.dp),
        )
        Spacer(Modifier.width(10.dp))
        Text(
            text = sub.subscriber?.publicName ?: "User",
            color = TextPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.weight(1f),
        )
        Text(
            text = "Since ${formatShortDate(sub.createdAt)}",
            color = TextMuted,
            fontSize = 11.sp,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Subscriptions (as subscriber)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun SubscriptionsSection(
    subscriptions: List<SubscriptionMade>,
    onTogglePush: (Int, Boolean) -> Unit,
    onCancel: (Int) -> Unit,
    onOpenPortfolio: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("My Subscriptions", color = TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.Bold)

        if (subscriptions.isEmpty()) {
            EmptyCard(
                icon = Icons.Default.StarOutline,
                title = "No subscriptions yet",
                body = "Subscribe to traders from the leaderboard to get real-time alerts",
            )
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                subscriptions.forEach { sub ->
                    SubscriptionCard(
                        subscription = sub,
                        onTogglePush = { onTogglePush(sub.id, it) },
                        onCancel = { onCancel(sub.id) },
                        onOpenPortfolio = onOpenPortfolio,
                    )
                }
            }
        }
    }
}

@Composable
private fun SubscriptionCard(
    subscription: SubscriptionMade,
    onTogglePush: (Boolean) -> Unit,
    onCancel: () -> Unit,
    onOpenPortfolio: (String) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(CardBackground)
            .border(0.5.dp, CardBorder.copy(alpha = 0.4f), RoundedCornerShape(14.dp)),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Default.AccountCircle,
                contentDescription = null,
                tint = PrimaryAccent,
                modifier = Modifier.size(28.dp),
            )
            Spacer(Modifier.width(12.dp))

            Column(
                verticalArrangement = Arrangement.spacedBy(4.dp),
                modifier = Modifier.weight(1f),
            ) {
                Text(
                    text = subscription.portfolioOwner?.publicName ?: "Unknown",
                    color = TextPrimary,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatusBadge(
                        text = subscription.status.replaceFirstChar { it.uppercase() },
                        color = if (subscription.status == "active") Gains else TextSecondary,
                    )
                    subscription.expiresAt?.let { exp ->
                        Text(
                            text = "Renews ${formatShortDate(exp)}",
                            color = TextMuted,
                            fontSize = 11.sp,
                        )
                    }
                }
            }

            Spacer(Modifier.width(8.dp))

            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Icon(
                    imageVector = if (subscription.pushNotificationsEnabled) Icons.Default.Notifications
                    else Icons.Default.NotificationsOff,
                    contentDescription = null,
                    tint = if (subscription.pushNotificationsEnabled) PrimaryAccent else TextMuted,
                    modifier = Modifier.size(14.dp),
                )
                Switch(
                    checked = subscription.pushNotificationsEnabled,
                    onCheckedChange = onTogglePush,
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

        AccentRowDivider()

        Row(modifier = Modifier.fillMaxWidth()) {
            subscription.portfolioOwner?.portfolioSlug?.let { slug ->
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .clickable { onOpenPortfolio(slug) }
                        .padding(vertical = 10.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(5.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Default.ShowChart,
                            contentDescription = null,
                            tint = PrimaryAccent,
                            modifier = Modifier.size(11.dp),
                        )
                        Text(
                            "View Portfolio",
                            color = PrimaryAccent,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }

                Box(
                    modifier = Modifier
                        .width(0.5.dp)
                        .height(20.dp)
                        .background(CardBorder.copy(alpha = 0.4f))
                )
            }

            Box(
                modifier = Modifier
                    .weight(1f)
                    .clickable(onClick = onCancel)
                    .padding(vertical = 10.dp),
                contentAlignment = Alignment.Center,
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(5.dp),
                ) {
                    Icon(
                        imageVector = Icons.Default.Cancel,
                        contentDescription = null,
                        tint = TextMuted,
                        modifier = Modifier.size(11.dp),
                    )
                    Text("Cancel", color = TextMuted, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Notifications history
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun NotificationsSection(notifications: List<NotificationItem>) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Trade Alerts", color = TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.Bold)

        if (notifications.isEmpty()) {
            EmptyCard(
                icon = Icons.Default.NotificationsOff,
                title = "No trade alerts yet",
                body = "You'll see trade notifications from your subscriptions here",
            )
        } else {
            CardColumn {
                notifications.forEachIndexed { idx, n ->
                    NotificationRow(n)
                    if (idx < notifications.size - 1) AccentRowDivider()
                }
            }
        }
    }
}

@Composable
private fun NotificationRow(n: NotificationItem) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(
            imageVector = if (n.type == "push") Icons.Default.Notifications else Icons.Default.Email,
            contentDescription = null,
            tint = PrimaryAccent,
            modifier = Modifier.size(13.dp),
        )

        Column(
            verticalArrangement = Arrangement.spacedBy(3.dp),
            modifier = Modifier.weight(1f),
        ) {
            val body = n.body
            if (!body.isNullOrEmpty()) {
                Text(
                    text = body,
                    color = TextPrimary,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            } else {
                Text(
                    text = "Trade alert from ${n.traderUsername}",
                    color = TextPrimary,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = n.traderUsername,
                    color = PrimaryAccent,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                n.createdAt?.let { date ->
                    Text(
                        text = formatAlertTimestamp(date),
                        color = TextMuted,
                        fontSize = 10.sp,
                    )
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Building blocks
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun StatusBadge(text: String, color: Color) {
    Box(
        modifier = Modifier
            .clip(CircleShape)
            .background(color.copy(alpha = 0.15f))
            .padding(horizontal = 8.dp, vertical = 4.dp),
    ) {
        Text(text, color = color, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun EmptyCard(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    body: String,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(CardBackground)
            .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = PrimaryAccent.copy(alpha = 0.6f),
            modifier = Modifier.size(28.dp),
        )
        Spacer(Modifier.width(12.dp))
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, color = TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            Text(body, color = TextSecondary, fontSize = 12.sp)
        }
    }
}

@Composable
private fun CardColumn(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(CardBackground)
            .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp)),
    ) { content() }
}

@Composable
private fun AccentRowDivider() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(0.5.dp)
            .background(CardBorder)
    )
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

private fun formatShortDate(iso: String): String {
    val parsed = parseIso(iso) ?: return iso
    return SimpleDateFormat("MMM d", Locale.US).format(parsed)
}

private fun formatRelativeDate(iso: String): String {
    val parsed = parseIso(iso) ?: return iso
    val now = System.currentTimeMillis()
    val ms = now - parsed.time
    if (ms < 60_000) return "just now"
    if (ms < 3_600_000) return "${ms / 60_000}m ago"
    if (ms < 86_400_000) return "${ms / 3_600_000}h ago"
    if (ms < 604_800_000) return "${ms / 86_400_000}d ago"
    return SimpleDateFormat("MMM d", Locale.US).format(parsed)
}

/**
 * Trade Alerts timestamp: a friendly relative prefix (for items < 1 week old)
 * followed by the exact calendar date and time down to the minute, e.g.
 * "3d ago · May 28, 5:33 PM". Older items drop the redundant relative prefix
 * and show the absolute date/time only. The year is appended when the alert is
 * not from the current year. Mirrors iOS `formatAlertTimestamp`.
 */
private fun formatAlertTimestamp(iso: String): String {
    val parsed = parseIso(iso) ?: return iso
    val yearFmt = SimpleDateFormat("yyyy", Locale.US)
    val sameYear = yearFmt.format(parsed) == yearFmt.format(Date())
    val pattern = if (sameYear) "MMM d, h:mm a" else "MMM d, yyyy, h:mm a"
    val absolute = SimpleDateFormat(pattern, Locale.US).format(parsed)

    val ms = System.currentTimeMillis() - parsed.time
    val relative = when {
        ms < 60_000 -> "just now"
        ms < 3_600_000 -> "${ms / 60_000}m ago"
        ms < 86_400_000 -> "${ms / 3_600_000}h ago"
        ms < 604_800_000 -> "${ms / 86_400_000}d ago"
        else -> null
    }
    return if (relative != null) "$relative · $absolute" else absolute
}

private fun parseIso(iso: String): Date? {
    // The backend emits 6-digit microseconds (e.g. ".761915"). SimpleDateFormat's
    // millisecond field ('S') would read that whole number as milliseconds —
    // adding ~12 minutes — so truncate any fractional component to 3 digits.
    val normalized = Regex("\\.(\\d{3})\\d+").replace(iso) { "." + it.groupValues[1] }

    // Patterns carrying an explicit offset/"Z" — the timezone comes from the
    // string itself, so parse as-is.
    val tzPatterns = listOf(
        "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
        "yyyy-MM-dd'T'HH:mm:ssXXX",
    )
    for (p in tzPatterns) {
        val r = runCatching { SimpleDateFormat(p, Locale.US).parse(normalized) }.getOrNull()
        if (r != null) return r
    }

    // Naive (no-offset) timestamps: backend times are UTC, so force UTC instead
    // of the device's local zone (which would shift the displayed time).
    val utcPatterns = listOf(
        "yyyy-MM-dd'T'HH:mm:ss.SSS",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd",
    )
    for (p in utcPatterns) {
        val r = runCatching {
            SimpleDateFormat(p, Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.parse(normalized)
        }.getOrNull()
        if (r != null) return r
    }
    return null
}

// ─────────────────────────────────────────────────────────────────────────
// State + ViewModel
// ─────────────────────────────────────────────────────────────────────────

sealed interface SubsState {
    data object Loading : SubsState
    data class Loaded(
        val subscriptions: List<SubscriptionMade>,
        val subscribers: List<Subscriber>,
        val subscriberCount: Int,
        val notifications: List<NotificationItem>,
    ) : SubsState

    data class Error(val message: String) : SubsState
}

@HiltViewModel
class SubscriptionsViewModel @Inject constructor(
    private val apiService: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow<SubsState>(SubsState.Loading)
    val state: StateFlow<SubsState> = _state.asStateFlow()

    // Drives the pull-to-refresh spinner. Distinct from SubsState.Loading (the
    // full-screen first-load placeholder) so a manual pull keeps the existing
    // content visible underneath the indicator.
    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    /**
     * Reload subscriptions + notification history. Three modes:
     *  - [manual] = true (pull-to-refresh): shows the pull indicator, leaves the
     *    current content in place, and keeps it on failure (a failed gesture
     *    isn't destructive).
     *  - first load (no data yet): shows the full-screen Loading placeholder,
     *    and a full-screen Error on failure.
     *  - silent (data already present, e.g. on lifecycle resume / tab re-entry):
     *    refetches in the background and swaps the data in without any spinner
     *    flash; on failure the existing content is kept.
     *
     * The silent path is what makes new trade alerts appear automatically when
     * the app is reopened after receiving a push — no manual pull required.
     */
    fun refresh(manual: Boolean = false) {
        viewModelScope.launch {
            val hadData = _state.value is SubsState.Loaded
            when {
                manual -> _isRefreshing.value = true
                !hadData -> _state.value = SubsState.Loading
                // else: silent refresh — keep showing existing content.
            }
            val subsResult = runCatching { apiService.getSubscriptions() }
            val notifResult = runCatching { apiService.getNotificationHistory(limit = 30, offset = 0) }
            val resp = subsResult.getOrNull()
            if (resp == null) {
                // Only surface a full-screen error on the very first load; a
                // failed manual/silent refresh keeps whatever is already shown.
                if (!hadData && !manual) {
                    _state.value = SubsState.Error(subsResult.exceptionOrNull()?.message ?: "Failed to load")
                }
                if (manual) _isRefreshing.value = false
                return@launch
            }
            _state.value = SubsState.Loaded(
                subscriptions = resp.subscriptionsMade,
                subscribers = resp.subscribers,
                subscriberCount = resp.subscriberCount,
                notifications = notifResult.getOrNull()?.notifications ?: emptyList(),
            )
            if (manual) _isRefreshing.value = false
        }
    }

    fun togglePush(id: Int, enabled: Boolean) {
        viewModelScope.launch {
            // Optimistic update
            _state.update { current ->
                if (current is SubsState.Loaded) {
                    current.copy(
                        subscriptions = current.subscriptions.map {
                            if (it.id == id) it.copy(pushNotificationsEnabled = enabled) else it
                        },
                    )
                } else current
            }
            runCatching {
                apiService.updateNotificationSettings(
                    com.apestogether.app.data.models.NotificationSettingsRequest(
                        subscriptionId = id,
                        pushNotificationsEnabled = enabled,
                    )
                )
            }
        }
    }

    fun cancel(id: Int) {
        viewModelScope.launch {
            runCatching { apiService.unsubscribe(id) }
            _state.update { current ->
                if (current is SubsState.Loaded) {
                    current.copy(
                        subscriptions = current.subscriptions.map {
                            if (it.id == id) it.copy(status = "canceled") else it
                        },
                    )
                } else current
            }
        }
    }
}
