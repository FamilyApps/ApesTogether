package com.apestogether.app.ui.screens.portfolio

import android.content.Intent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.CallMade
import androidx.compose.material.icons.automirrored.filled.CallReceived
import androidx.compose.material.icons.automirrored.filled.ShowChart
import androidx.compose.material.icons.filled.AddCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.RemoveCircle
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.WorkspacePremium
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.window.Dialog
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.billing.BillingService
import com.apestogether.app.data.onboarding.OnboardingManager
import com.apestogether.app.data.billing.SubscriptionPlan
import com.apestogether.app.data.models.Holding
import com.apestogether.app.data.models.LeaderboardBadge
import com.apestogether.app.data.models.PortfolioResponse
import com.apestogether.app.data.models.PortfolioScale
import com.apestogether.app.data.models.PurchaseValidationRequest
import com.apestogether.app.data.models.SetScaleRequest
import com.apestogether.app.data.models.Trade
import com.apestogether.app.ui.components.CompactPlanToggle
import com.apestogether.app.ui.components.PerformanceChartCard
import com.apestogether.app.ui.components.SubscribeStatusBanner
import com.apestogether.app.ui.components.SubscribeUiState
import com.apestogether.app.ui.components.findActivity
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Gains
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.SecondaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import javax.inject.Inject
import kotlin.math.absoluteValue

/**
 * Portfolio detail screen. Direct port of iOS [PortfolioDetailView].
 *
 * Renders the same content matrix the iOS view does, depending on
 * [PortfolioResponse.isOwner] and [PortfolioResponse.isSubscribed]:
 *
 *   1. Hero card (non-owner only) — avatar, name, account-age + subscriber
 *      count, total portfolio value.
 *   2. Leaderboard badges (when present) — horizontal scroll of medal pills.
 *   3. Performance chart card — uses [PerformanceChartCard]. The chart's
 *      period selector wires through to [PortfolioDetailViewModel.setPeriod]
 *      which kicks off another `/portfolio/{slug}/chart?period=…` fetch.
 *   4. Stats grid (non-owner only) — Stocks / Trades-wk / Large Cap %.
 *   5. Sector allocation card (when industryMix present) — stacked bar
 *      with sector legend chips.
 *   6. Action buttons:
 *      - Non-owner + not subscribed → Subscribe + Share.
 *      - Owner → Buy + Sell.
 *      Subscribe is wired to a placeholder; Buy/Sell are still TODOs.
 *   7. Holdings list (when present) — ticker bubble + qty + value + gain%.
 *   8. Recent trades list (when present, max 5) — directional arrow +
 *      type + ticker + timestamp + qty @ price.
 *   9. Blurred teaser (non-subscriber, holdings withheld) — preview message
 *      + Subscribe CTA.
 *  10. Owner empty state when holdings list is empty.
 *
 * The composable accepts a [showOwnHeader] toggle so MyPortfolioScreen can
 * embed this view inside its own Scaffold without doubling up on a top bar.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PortfolioDetailScreen(
    slug: String,
    onBack: () -> Unit,
    showOwnHeader: Boolean = true,
) {
    val viewModel: PortfolioDetailViewModel = hiltViewModel()
    val state by viewModel.state.collectAsState()
    val period by viewModel.period.collectAsState()

    LaunchedEffect(slug) {
        viewModel.load(slug)
    }

    if (showOwnHeader) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Text(
                            text = (state as? PortfolioState.Loaded)?.portfolio?.owner?.publicName
                                ?: "Portfolio",
                            color = TextPrimary,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    },
                    navigationIcon = {
                        IconButton(onClick = onBack) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                                contentDescription = "Back",
                                tint = TextSecondary,
                            )
                        }
                    },
                    actions = {
                        (state as? PortfolioState.Loaded)?.portfolio
                            ?.takeIf { !it.isOwner }
                            ?.let { p ->
                                ShareIconButton(slug = p.owner.portfolioSlug ?: slug, period = period)
                            }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = AppBackground),
                )
            },
            containerColor = AppBackground,
        ) { padding ->
            PortfolioBody(
                modifier = Modifier.padding(padding),
                slug = slug,
                state = state,
                period = period,
                viewModel = viewModel,
                onPeriodChange = { viewModel.setPeriod(it, slug) },
            )
        }
    } else {
        // Embedded mode (MyPortfolioScreen wraps us inside its own Scaffold).
        PortfolioBody(
            modifier = Modifier.background(AppBackground),
            slug = slug,
            state = state,
            period = period,
            viewModel = viewModel,
            onPeriodChange = { viewModel.setPeriod(it, slug) },
        )
    }
}

@Composable
private fun PortfolioBody(
    modifier: Modifier = Modifier,
    slug: String,
    state: PortfolioState,
    period: String,
    viewModel: PortfolioDetailViewModel,
    onPeriodChange: (String) -> Unit,
) {
    val selectedPlan by viewModel.selectedPlan.collectAsState()
    val subscribeState by viewModel.subscribeState.collectAsState()
    val activity = LocalContext.current.findActivity()

    // ── Phase D: portfolio resizer state ────────────────────────────────
    // The dialog amount is bound to a String (numeric input). It's pre-
    // filled with the current target_dollars on edit. `scaleSaving` is
    // surfaced from the ViewModel so the button can show a spinner.
    var showScaleDialog by remember { mutableStateOf(false) }
    var scaleAmountInput by remember { mutableStateOf("") }
    var scaleErrorText by remember { mutableStateOf<String?>(null) }
    val scaleSaving by viewModel.scaleSaving.collectAsState()
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(AppBackground)
    ) {
        when (state) {
            PortfolioState.Loading -> {
                CircularProgressIndicator(
                    color = PrimaryAccent,
                    modifier = Modifier.align(Alignment.TopCenter).padding(top = 100.dp),
                )
            }

            is PortfolioState.Error -> {
                Column(
                    modifier = Modifier.align(Alignment.TopCenter).padding(top = 100.dp, start = 24.dp, end = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text("Error", color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    Text(state.message, color = TextSecondary, fontSize = 14.sp)
                }
            }

            is PortfolioState.Loaded -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(bottom = 20.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    val portfolio = state.portfolio

                    // Hero (non-owner only). Top padding is intentionally tight
                    // (8dp instead of 16) so the chart + Subscribe CTA both fit
                    // above the fold on shorter Android screens.
                    if (!portfolio.isOwner) {
                        PortfolioHeroCard(
                            portfolio = portfolio,
                            modifier = Modifier.padding(horizontal = 16.dp).padding(top = 8.dp),
                        )
                    }

                    // Badges
                    portfolio.leaderboardBadges?.takeIf { it.isNotEmpty() }?.let { badges ->
                        Row(
                            modifier = Modifier
                                .horizontalScroll(rememberScrollState())
                                .padding(horizontal = 16.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            badges.forEach { LeaderboardBadgePill(badge = it) }
                        }
                    }

                    // Chart
                    PerformanceChartCard(
                        chartData = state.chartData,
                        portfolioReturn = state.portfolioReturn,
                        sp500Return = state.sp500Return,
                        selectedPeriod = period,
                        onPeriodChange = onPeriodChange,
                        portfolioLabel = if (portfolio.isOwner) "Your Portfolio" else portfolio.owner.publicName,
                        leaderboardEligible = state.leaderboardEligible,
                        daysActive = state.daysActive,
                        daysRequired = state.daysRequired,
                        eligibleDate = state.eligibleDate,
                        modifier = Modifier.padding(horizontal = 16.dp),
                    )

                    // Subscribe row + plan toggle — placed immediately under the
                    // chart so the conversion CTA is visible above-the-fold on
                    // both iPhone 17 Pro and Pixel 7 (matches iOS layout).
                    if (!portfolio.isOwner && !portfolio.isSubscribed) {
                        Column(
                            modifier = Modifier.padding(horizontal = 16.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            CompactPlanToggle(
                                selected = selectedPlan,
                                onSelect = viewModel::setPlan,
                            )
                            SubscribeAndShareRow(
                                slug = portfolio.owner.portfolioSlug ?: "",
                                period = period,
                                selectedPlan = selectedPlan,
                                subscriptionPrice = portfolio.subscriptionPrice,
                                subscribeState = subscribeState,
                                onSubscribe = {
                                    activity?.let {
                                        viewModel.subscribe(
                                            activity = it,
                                            subscribedToId = portfolio.owner.id,
                                            subscribedToUsername = portfolio.owner.publicName,
                                        )
                                    }
                                },
                            )
                            SubscribeStatusBanner(
                                state = subscribeState,
                                onDismiss = viewModel::clearSubscribeState,
                            )
                        }
                    }

                    // Stats grid (non-owner)
                    if (!portfolio.isOwner) {
                        PortfolioStatsGrid(
                            portfolio = portfolio,
                            modifier = Modifier.padding(horizontal = 16.dp),
                        )
                    }

                    // Sector allocation
                    portfolio.industryMix?.takeIf { it.isNotEmpty() }?.let { mix ->
                        SectorAllocationCard(
                            industryMix = mix,
                            modifier = Modifier.padding(horizontal = 16.dp),
                        )
                    }

                    if (portfolio.isOwner) {
                        OwnerBuySellRow(
                            modifier = Modifier.padding(horizontal = 16.dp),
                        )
                    }

                    // ── Phase D: Portfolio Resizer Card (subscriber-only) ──
                    // Hidden for the owner viewing their own page and for
                    // non-subscribers (where the holdings are blurred). Two
                    // states: no scale set (CTA) or scale active (badge +
                    // Edit/Clear actions).
                    if (portfolio.isSubscribed && !portfolio.isOwner && portfolio.subscriptionId != null) {
                        ScaleCard(
                            scale = portfolio.scale,
                            onTapEdit = {
                                scaleAmountInput = portfolio.scale
                                    ?.targetDollars
                                    ?.let { "%.0f".format(it) }
                                    ?: ""
                                scaleErrorText = null
                                showScaleDialog = true
                            },
                            onTapClear = {
                                viewModel.clearScale(slug = slug, subscriptionId = portfolio.subscriptionId)
                            },
                            modifier = Modifier.padding(horizontal = 16.dp),
                        )
                    }

                    // Holdings
                    val holdings = portfolio.holdings
                    when {
                        holdings != null && holdings.isNotEmpty() -> {
                            HoldingsSection(
                                holdings = holdings,
                                cashBalance = portfolio.cashBalance,
                                portfolioValue = portfolio.portfolioValue,
                                showSwipeHint = portfolio.isOwner,
                                modifier = Modifier.padding(horizontal = 16.dp),
                            )

                            // Phase D: below-1-share footnote (floor mode only)
                            portfolio.belowOneShareCount?.takeIf { it > 0 }?.let { count ->
                                BelowOneShareFooter(
                                    count = count,
                                    modifier = Modifier.padding(horizontal = 16.dp),
                                )
                            }

                            portfolio.recentTrades?.takeIf { it.isNotEmpty() }?.let { trades ->
                                RecentTradesSection(
                                    trades = trades.take(5),
                                    modifier = Modifier.padding(horizontal = 16.dp),
                                )
                            }
                        }

                        holdings == null -> {
                            // Non-subscriber teaser
                            BlurredHoldingsTeaser(
                                ownerName = portfolio.owner.publicName,
                                previewMessage = portfolio.previewMessage,
                                onSubscribe = {
                                    activity?.let {
                                        viewModel.subscribe(
                                            activity = it,
                                            subscribedToId = portfolio.owner.id,
                                            subscribedToUsername = portfolio.owner.publicName,
                                        )
                                    }
                                },
                                modifier = Modifier.padding(horizontal = 16.dp),
                            )
                        }

                        else -> {
                            OwnerEmptyState(modifier = Modifier.padding(vertical = 40.dp))
                        }
                    }
                }
            }
        }
    }

    // ── Phase D: scale-setting dialog ────────────────────────────────────
    // Lives outside the Box (overlay) so dismiss-by-tap-outside works
    // cleanly. Reads the current portfolio (for owner name / value) from
    // the loaded state.
    if (showScaleDialog) {
        val loaded = state as? PortfolioState.Loaded
        val portfolio = loaded?.portfolio
        SetScaleDialog(
            ownerName = portfolio?.owner?.publicName ?: "this portfolio",
            creatorPortfolioValue = portfolio?.scale?.unscaledPortfolioValue
                ?: portfolio?.portfolioValue,
            currentTargetDollars = portfolio?.scale?.targetDollars,
            amount = scaleAmountInput,
            onAmountChange = { scaleAmountInput = it },
            isSaving = scaleSaving,
            errorText = scaleErrorText,
            onCancel = { showScaleDialog = false },
            onSubmit = { dollars ->
                val subId = portfolio?.subscriptionId
                if (subId == null) {
                    scaleErrorText = "Subscription not found"
                    return@SetScaleDialog
                }
                viewModel.setScale(
                    slug = slug,
                    subscriptionId = subId,
                    targetDollars = dollars,
                    onResult = { ok, message ->
                        if (ok) {
                            showScaleDialog = false
                        } else {
                            scaleErrorText = message ?: "Failed to set scale"
                        }
                    },
                )
            },
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Hero (non-owner)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun PortfolioHeroCard(
    portfolio: PortfolioResponse,
    modifier: Modifier = Modifier,
) {
    val ageText = formatAccountAge(portfolio.accountAgeDays ?: 0)
    // Slimmed: dropped the 56dp gradient avatar and trimmed vertical padding
    // 16 → 10dp, spacing 8 → 4dp. Frees ~85dp so the chart + Subscribe CTA +
    // stats grid fit above the fold on Pixel 7 / iPhone 17 Pro.
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(CardBackground)
            .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
            .padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(
            text = portfolio.owner.publicName,
            color = TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
        )

        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Member for $ageText", color = TextSecondary, fontSize = 12.sp)
            Text("·", color = TextSecondary, fontSize = 12.sp)
            Text(
                text = "${portfolio.subscriberCount} subscriber" + if (portfolio.subscriberCount != 1) "s" else "",
                color = TextSecondary,
                fontSize = 12.sp,
            )
        }

        portfolio.portfolioValue?.takeIf { it > 0 }?.let { value ->
            Text(
                text = "$" + formatLargeNumber(value),
                color = TextPrimary,
                fontSize = 28.sp,
                fontWeight = FontWeight.Black,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
    }
}

private fun formatAccountAge(days: Int): String {
    if (days >= 365) {
        val years = days / 365
        val months = (days % 365) / 30
        return "${years}y ${months}m"
    }
    if (days >= 30) {
        val months = days / 30
        return "$months month" + if (months > 1) "s" else ""
    }
    return "$days day" + if (days != 1) "s" else ""
}

private fun formatLargeNumber(value: Double): String {
    return java.text.NumberFormat.getNumberInstance(Locale.US).apply {
        minimumFractionDigits = 2
        maximumFractionDigits = 2
    }.format(value)
}

// ─────────────────────────────────────────────────────────────────────────
// Badge pill
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun LeaderboardBadgePill(badge: LeaderboardBadge) {
    val medal = when (badge.rank) {
        1 -> "🥇"
        2 -> "🥈"
        3 -> "🥉"
        else -> "🏆"
    }
    val pillColor = when (badge.rank) {
        1 -> Color(0xFFFFD700)
        2 -> Color(0xFFC0C0C0)
        3 -> Color(0xFFCD7F32)
        else -> PrimaryAccent
    }
    val label = if (badge.type == "sector" && badge.sector != null) {
        "#${badge.rank} ${badge.sector} (${badge.period})"
    } else {
        "#${badge.rank} Overall (${badge.period})"
    }

    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(pillColor.copy(alpha = 0.15f))
            .border(1.dp, pillColor.copy(alpha = 0.4f), RoundedCornerShape(20.dp))
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(medal, fontSize = 12.sp)
        Text(label, color = TextPrimary, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Stats grid (non-owner)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun PortfolioStatsGrid(
    portfolio: PortfolioResponse,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Color.White.copy(alpha = 0.06f))
            .border(1.dp, Color.White.copy(alpha = 0.06f), RoundedCornerShape(12.dp)),
    ) {
        StatColumn(value = "${portfolio.numStocks ?: 0}", label = "Stocks", modifier = Modifier.weight(1f))
        StatColumnDivider()
        StatColumn(value = "%.1f".format(portfolio.avgTradesPerWeek ?: 0.0), label = "Trades/Wk", modifier = Modifier.weight(1f))
        StatColumnDivider()
        StatColumn(value = "%.0f%%".format(portfolio.largeCapPct ?: 0.0), label = "Large Cap", modifier = Modifier.weight(1f))
    }
}

@Composable
private fun StatColumn(value: String, label: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.padding(vertical = 14.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(value, color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Text(label, color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun StatColumnDivider() {
    Box(
        modifier = Modifier
            .width(0.5.dp)
            .height(40.dp)
            .background(Color.White.copy(alpha = 0.06f))
    )
}

// ─────────────────────────────────────────────────────────────────────────
// Sector allocation
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun SectorAllocationCard(
    industryMix: Map<String, Double>,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(CardBackground)
            .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            text = "SECTOR ALLOCATION",
            color = TextMuted,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.8.sp,
        )

        // Stacked bar
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp)
                .clip(RoundedCornerShape(4.dp)),
        ) {
            val total = industryMix.values.sum().takeIf { it > 0 } ?: 1.0
            industryMix.entries.sortedByDescending { it.value }.forEach { (name, pct) ->
                Box(
                    modifier = Modifier
                        .weight((pct / total).toFloat().coerceAtLeast(0.005f))
                        .fillMaxSize()
                        .background(sectorColor(name))
                )
            }
        }

        // Legend
        Row(
            modifier = Modifier
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            industryMix.entries.sortedByDescending { it.value }.forEach { (name, pct) ->
                Row(
                    modifier = Modifier
                        .clip(RoundedCornerShape(20.dp))
                        .background(CardBorder.copy(alpha = 0.3f))
                        .padding(horizontal = 8.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Box(
                        modifier = Modifier
                            .size(6.dp)
                            .clip(CircleShape)
                            .background(sectorColor(name))
                    )
                    Text(name, color = TextSecondary, fontSize = 10.sp, fontWeight = FontWeight.Medium)
                    Text("%.0f%%".format(pct), color = TextPrimary, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

private fun sectorColor(sector: String): Color {
    val s = sector.lowercase()
    return when {
        "tech" in s -> Color(0xFF3B82F6)
        "health" in s -> Color(0xFF22C55E)
        "financ" in s -> Color(0xFFF59E0B)
        "consumer d" in s -> Color(0xFFEC4899)
        "communicat" in s -> Color(0xFF8B5CF6)
        "industrial" in s -> Color(0xFF6366F1)
        "consumer s" in s -> Color(0xFF14B8A6)
        "energy" in s -> Color(0xFFEF4444)
        "utilit" in s -> Color(0xFF64748B)
        "real" in s -> Color(0xFFD97706)
        "material" in s -> Color(0xFF78716C)
        else -> Color(0xFF9CA3AF)
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Action rows
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun SubscribeAndShareRow(
    slug: String,
    period: String,
    selectedPlan: SubscriptionPlan,
    subscriptionPrice: Double,
    subscribeState: SubscribeUiState,
    onSubscribe: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val processing = subscribeState is SubscribeUiState.Processing
    val ctaText = when (selectedPlan) {
        SubscriptionPlan.Annual -> "Try 7 Days Free, then $69/yr"
        SubscriptionPlan.Monthly -> "Try 7 Days Free, then $${subscriptionPrice.toInt()}/mo"
    }

    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Button(
            onClick = onSubscribe,
            enabled = !processing,
            modifier = Modifier
                .weight(1f)
                .height(48.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = PrimaryAccent,
                disabledContainerColor = PrimaryAccent.copy(alpha = 0.5f),
            ),
            contentPadding = PaddingValues(0.dp),
        ) {
            if (processing) {
                CircularProgressIndicator(
                    color = Color.White,
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(16.dp),
                )
            } else {
                Icon(
                    Icons.Default.WorkspacePremium,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(13.dp),
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    text = ctaText,
                    color = Color.White,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }

        OutlinedButton(
            onClick = {
                val url = "https://apestogether.ai/p/$slug?period=$period"
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_TEXT, "Check out this portfolio on Apes Together!\n$url")
                }
                context.startActivity(
                    Intent.createChooser(intent, "Share portfolio"),
                )
            },
            modifier = Modifier.height(48.dp),
            shape = RoundedCornerShape(12.dp),
            border = BorderStroke(1.dp, Color.White.copy(alpha = 0.08f)),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = TextSecondary),
            contentPadding = PaddingValues(horizontal = 16.dp),
        ) {
            Icon(Icons.Default.Share, contentDescription = null, tint = TextSecondary, modifier = Modifier.size(13.dp))
            Spacer(Modifier.width(5.dp))
            Text("Share", color = TextSecondary, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun ShareIconButton(slug: String, period: String) {
    val context = LocalContext.current
    IconButton(
        onClick = {
            val url = "https://apestogether.ai/p/$slug?period=$period"
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_TEXT, "Check out this portfolio on Apes Together!\n$url")
            }
            context.startActivity(
                Intent.createChooser(intent, "Share portfolio"),
            )
        }
    ) {
        Icon(Icons.Default.Share, contentDescription = "Share", tint = PrimaryAccent)
    }
}

@Composable
private fun OwnerBuySellRow(modifier: Modifier = Modifier) {
    // Buy / Sell are TODOs (require TradeSheet UI). Buttons render so users
    // see they exist, but tapping is a no-op for now.
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Button(
            onClick = {},
            modifier = Modifier.weight(1f).height(52.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Gains),
        ) {
            Icon(Icons.Default.AddCircle, null, tint = Color.White, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Text("Buy", color = Color.White, fontWeight = FontWeight.Bold)
        }

        OutlinedButton(
            onClick = {},
            modifier = Modifier.weight(1f).height(52.dp),
            shape = RoundedCornerShape(12.dp),
            border = BorderStroke(1.dp, Losses.copy(alpha = 0.3f)),
            colors = ButtonDefaults.outlinedButtonColors(
                containerColor = Losses.copy(alpha = 0.15f),
                contentColor = Losses,
            ),
        ) {
            Icon(Icons.Default.RemoveCircle, null, tint = Losses, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Text("Sell", color = Losses, fontWeight = FontWeight.Bold)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Holdings + Trades
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun HoldingsSection(
    holdings: List<Holding>,
    cashBalance: Double?,
    portfolioValue: Double?,
    showSwipeHint: Boolean,
    modifier: Modifier = Modifier,
) {
    // Phase B: render the cash line as the last row when cash > 0. The
    // mobile_api only returns `cash_balance` when it's > $0.005, so a null
    // here means "fully invested" — no cash row to render. Stock count in
    // the header still reflects the holdings list only.
    val showCash = (cashBalance ?: 0.0) > 0.005

    Column(modifier = modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Holdings", color = TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            Text("${holdings.size} stocks", color = TextMuted, fontSize = 11.sp)
        }
        Spacer(Modifier.height(10.dp))

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(CardBackground)
                .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp)),
        ) {
            holdings.forEachIndexed { idx, h ->
                HoldingRow(holding = h, portfolioValue = portfolioValue)
                if (idx < holdings.size - 1 || showCash) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(0.5.dp)
                            .background(CardBorder)
                    )
                }
            }
            if (showCash) {
                CashRow(
                    cashBalance = cashBalance ?: 0.0,
                    portfolioValue = portfolioValue,
                )
            }
        }
    }
}

@Composable
private fun HoldingRow(holding: Holding, portfolioValue: Double? = null) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Ticker bubble
        Box(
            modifier = Modifier
                .size(44.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(PrimaryAccent.copy(alpha = 0.1f)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = holding.ticker.take(2),
                color = PrimaryAccent,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
            )
        }

        Spacer(Modifier.width(12.dp))

        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(holding.ticker, color = TextPrimary, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            // Phase B fractional-share fix: was `quantity.toInt()` which
            // truncated 0.5 to 0 (showed "0 shares"). `formatQuantity`
            // matches iOS `formattedQuantity`: integers for whole positions,
            // 4-decimal-trimmed for fractional.
            Text(
                text = "${formatQuantity(holding.quantity)} shares",
                color = TextSecondary,
                fontSize = 11.sp,
            )
        }

        Spacer(Modifier.weight(1f))

        Column(
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "$" + "%.2f".format(holding.totalValue),
                    color = TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                )
                if (portfolioValue != null && portfolioValue > 0.0) {
                    val pct = (holding.totalValue / portfolioValue) * 100
                    Text(
                        text = if (pct < 1.0) "<1% port" else "%.0f%% port".format(pct),
                        color = TextMuted,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }
            holding.gainPercent?.let { gain ->
                Text(
                    text = formatPercent(gain, decimals = 1),
                    color = if (gain >= 0) Gains else Losses,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            } ?: Text(
                text = "$" + "%.2f".format(holding.displayPrice) + " avg",
                color = TextMuted,
                fontSize = 11.sp,
            )
        }
    }
}

/**
 * Phase B cash line. Mirrors `CashRow` in the iOS PortfolioDetailView so the
 * holdings list reads as a single cohesive table on both platforms. Only
 * shown when [cashBalance] > $0.005 (controlled by the parent).
 */
@Composable
private fun CashRow(cashBalance: Double, portfolioValue: Double?) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(44.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(PrimaryAccent.copy(alpha = 0.1f)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = "$",
                color = PrimaryAccent,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
            )
        }

        Spacer(Modifier.width(12.dp))

        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("Cash", color = TextPrimary, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text(
                text = "Available proceeds",
                color = TextSecondary,
                fontSize = 11.sp,
            )
        }

        Spacer(Modifier.weight(1f))

        Column(
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "$" + "%.2f".format(cashBalance),
                    color = TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                )
                if (portfolioValue != null && portfolioValue > 0.0) {
                    val pct = (cashBalance / portfolioValue) * 100
                    Text(
                        text = if (pct < 1.0) "<1% port" else "%.0f%% port".format(pct),
                        color = TextMuted,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }
            Text(
                text = "—",
                color = TextMuted,
                fontSize = 11.sp,
            )
        }
    }
}

@Composable
private fun RecentTradesSection(
    trades: List<Trade>,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier) {
        Text("Recent Trades", color = TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(10.dp))

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(CardBackground)
                .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp)),
        ) {
            trades.forEachIndexed { idx, t ->
                TradeRow(trade = t)
                if (idx < trades.size - 1) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(0.5.dp)
                            .background(CardBorder)
                    )
                }
            }
        }
    }
}

@Composable
private fun TradeRow(trade: Trade) {
    val isBuy = trade.type.equals("buy", ignoreCase = true)
    val accent = if (isBuy) Gains else Losses

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(CircleShape)
                .background(accent.copy(alpha = 0.15f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = if (isBuy) Icons.AutoMirrored.Filled.CallReceived else Icons.AutoMirrored.Filled.CallMade,
                contentDescription = null,
                tint = accent,
                modifier = Modifier.size(14.dp),
            )
        }

        Column(
            verticalArrangement = Arrangement.spacedBy(3.dp),
            modifier = Modifier.weight(1f),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = trade.type.uppercase(),
                    color = accent,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = trade.ticker,
                    color = TextPrimary,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
            Text(
                text = formatTradeDate(trade.timestamp),
                color = TextMuted,
                fontSize = 11.sp,
            )
        }

        Text(
            text = "${formatQuantity(trade.quantity)} @ $" + "%.2f".format(trade.price),
            color = TextSecondary,
            fontSize = 13.sp,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Teasers + empty states
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun BlurredHoldingsTeaser(
    ownerName: String,
    previewMessage: String?,
    onSubscribe: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(CardBackground)
            .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(Icons.Default.WorkspacePremium, null, tint = PrimaryAccent, modifier = Modifier.size(36.dp))
        Text(
            text = "$ownerName's holdings",
            color = TextPrimary,
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = previewMessage ?: "Subscribe to see exactly what they're trading and get instant alerts.",
            color = TextSecondary,
            fontSize = 13.sp,
        )
        Button(
            onClick = onSubscribe,
            colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
            shape = RoundedCornerShape(12.dp),
        ) {
            Text("Subscribe", color = Color.White, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun OwnerEmptyState(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Icon(Icons.AutoMirrored.Filled.ShowChart, null, tint = PrimaryAccent.copy(alpha = 0.6f), modifier = Modifier.size(48.dp))
        Text("No Holdings Yet", color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Text(
            text = "Add your first stocks to start tracking performance",
            color = TextSecondary,
            fontSize = 14.sp,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

private fun formatPercent(value: Double, decimals: Int): String {
    val sign = if (value >= 0) "+" else "−"
    val abs = value.absoluteValue
    return "$sign${"%.${decimals}f".format(abs)}%"
}

private fun formatQuantity(quantity: Double): String {
    if (quantity == quantity.toLong().toDouble() && quantity >= 1) return "%.0f".format(quantity)
    if (quantity >= 1) return "%.2f".format(quantity)
    val full = "%.4f".format(quantity)
    var trimmed = full
    while (trimmed.endsWith("0")) trimmed = trimmed.dropLast(1)
    if (trimmed.endsWith(".")) trimmed = trimmed.dropLast(1)
    return trimmed
}

private fun formatTradeDate(iso: String): String {
    // Backend sends Python isoformat() output, sometimes with microseconds and
    // sometimes without; sometimes with timezone offset, often without. Try
    // each known shape until one parses.
    val patterns = listOf(
        "yyyy-MM-dd'T'HH:mm:ss.SSSSSS",
        "yyyy-MM-dd'T'HH:mm:ss.SSS",
        "yyyy-MM-dd'T'HH:mm:ssXXX",
        "yyyy-MM-dd'T'HH:mm:ss",
    )
    val parsed: Date? = patterns.firstNotNullOfOrNull { p ->
        runCatching { SimpleDateFormat(p, Locale.US).parse(iso) }.getOrNull()
    }
    val out = SimpleDateFormat("MMM d, h:mm:ss a", Locale.US)
    return parsed?.let { out.format(it) } ?: iso
}

// ─────────────────────────────────────────────────────────────────────────
// State + ViewModel
// ─────────────────────────────────────────────────────────────────────────

sealed interface PortfolioState {
    data object Loading : PortfolioState
    data class Loaded(
        val portfolio: PortfolioResponse,
        val chartData: List<com.apestogether.app.data.models.ChartPoint>,
        val portfolioReturn: Double,
        val sp500Return: Double,
        val leaderboardEligible: Boolean,
        val daysActive: Int,
        val daysRequired: Int,
        val eligibleDate: String?,
    ) : PortfolioState

    data class Error(val message: String) : PortfolioState
}

@HiltViewModel
class PortfolioDetailViewModel @Inject constructor(
    private val apiService: ApiService,
    private val billingService: BillingService,
    private val onboardingManager: OnboardingManager,
) : ViewModel() {
    private val _state = MutableStateFlow<PortfolioState>(PortfolioState.Loading)
    val state: StateFlow<PortfolioState> = _state.asStateFlow()

    private val _period = MutableStateFlow("1W")
    val period: StateFlow<String> = _period.asStateFlow()

    private val _selectedPlan = MutableStateFlow(SubscriptionPlan.Annual)
    val selectedPlan: StateFlow<SubscriptionPlan> = _selectedPlan.asStateFlow()

    private val _subscribeState = MutableStateFlow<SubscribeUiState>(SubscribeUiState.Idle)
    val subscribeState: StateFlow<SubscribeUiState> = _subscribeState.asStateFlow()

    /** Live Play Billing connection state — drives the Subscribe button disabled state. */
    val billingConnectionState = billingService.connectionState

    // ── Phase D: portfolio resizer ───────────────────────────────────────
    private val _scaleSaving = MutableStateFlow(false)
    val scaleSaving: StateFlow<Boolean> = _scaleSaving.asStateFlow()

    fun load(slug: String) {
        if (slug.isBlank()) {
            _state.value = PortfolioState.Error("Invalid portfolio")
            return
        }
        viewModelScope.launch {
            _state.value = PortfolioState.Loading
            val portfolioResult = runCatching { apiService.getPortfolio(slug) }
            val chartResult = runCatching { apiService.getPortfolioChart(slug, _period.value) }

            val portfolio = portfolioResult.getOrNull()
            if (portfolio == null) {
                _state.value = PortfolioState.Error(
                    portfolioResult.exceptionOrNull()?.message ?: "Failed to load portfolio"
                )
                return@launch
            }

            val chart = chartResult.getOrNull()
            _state.value = PortfolioState.Loaded(
                portfolio = portfolio,
                chartData = chart?.chartData ?: emptyList(),
                portfolioReturn = chart?.portfolioReturn ?: 0.0,
                sp500Return = chart?.sp500Return ?: 0.0,
                leaderboardEligible = chart?.leaderboardEligible ?: true,
                daysActive = chart?.daysActive ?: 0,
                daysRequired = chart?.daysRequired ?: 0,
                eligibleDate = chart?.eligibleDate,
            )

            // Prefetch Play Billing products for snappier Subscribe UX. Failures are
            // expected during development before Play Console is set up; the
            // Subscribe button shows an error in that case.
            if (!portfolio.isOwner && !portfolio.isSubscribed) {
                runCatching { billingService.queryProducts() }
            }
        }
    }

    fun setPeriod(period: String, slug: String) {
        _period.value = period
        viewModelScope.launch {
            val result = runCatching { apiService.getPortfolioChart(slug, period) }
            val current = _state.value as? PortfolioState.Loaded ?: return@launch
            val chart = result.getOrNull()
            _state.value = current.copy(
                chartData = chart?.chartData ?: emptyList(),
                portfolioReturn = chart?.portfolioReturn ?: 0.0,
                sp500Return = chart?.sp500Return ?: 0.0,
                leaderboardEligible = chart?.leaderboardEligible ?: true,
                daysActive = chart?.daysActive ?: 0,
                daysRequired = chart?.daysRequired ?: 0,
                eligibleDate = chart?.eligibleDate,
            )
        }
    }

    fun setPlan(plan: SubscriptionPlan) {
        _selectedPlan.value = plan
    }

    /** Reset the subscribe error/success banner. */
    fun clearSubscribeState() {
        _subscribeState.value = SubscribeUiState.Idle
    }

    /**
     * Launches the Play Billing flow for the [selectedPlan], then on success
     * POSTs the resulting purchase token to the backend for validation.
     * Mirrors the iOS [SubscriptionManager.subscribe] flow.
     */
    fun subscribe(
        activity: android.app.Activity,
        subscribedToId: Int,
        subscribedToUsername: String,
    ) {
        viewModelScope.launch {
            _subscribeState.value = SubscribeUiState.Processing

            val ensure = runCatching { billingService.ensureConnected() }.getOrNull()
            if (ensure == null ||
                ensure.responseCode != com.android.billingclient.api.BillingClient.BillingResponseCode.OK
            ) {
                _subscribeState.value = SubscribeUiState.Error(
                    "Play Billing unavailable on this device. Please try again later."
                )
                return@launch
            }

            // Make sure product details are loaded (formattedPrice for the button).
            if (billingService.productDetails.value.isEmpty()) {
                runCatching { billingService.queryProducts() }
            }

            val result = billingService.purchase(activity, _selectedPlan.value.productId)
            when (result) {
                is BillingService.PurchaseResult.UserCanceled -> {
                    _subscribeState.value = SubscribeUiState.Idle
                }
                is BillingService.PurchaseResult.Error -> {
                    _subscribeState.value = SubscribeUiState.Error(result.message)
                }
                is BillingService.PurchaseResult.Success -> {
                    val purchase = result.purchase
                    val validation = runCatching {
                        apiService.validatePurchase(
                            PurchaseValidationRequest(
                                platform = "google",
                                subscribedToId = subscribedToId,
                                purchaseToken = purchase.purchaseToken,
                            )
                        )
                    }
                    val resp = validation.getOrNull()
                    if (resp?.success == true) {
                        // Server happy → acknowledge with Play (idempotent).
                        runCatching { billingService.acknowledge(purchase) }
                        _subscribeState.value = SubscribeUiState.Success
                        // Trigger the EarnNudge flow at the RootApp level —
                        // mirrors iOS .didSubscribe NotificationCenter event.
                        onboardingManager.notifyDidSubscribe(subscribedToUsername)
                    } else {
                        _subscribeState.value = SubscribeUiState.Error(
                            resp?.error
                                ?: validation.exceptionOrNull()?.message
                                ?: "Server failed to validate the purchase."
                        )
                    }
                }
            }
        }
    }

    // ── Phase D: portfolio resizer ───────────────────────────────────────
    /**
     * Set the subscriber's scale (target dollar amount) for this portfolio.
     * Reloads the portfolio on success so holdings + scale banner reflect
     * the new state. [onResult] is invoked with (success, errorMessage)
     * so the dialog can dismiss or surface the error inline.
     */
    fun setScale(
        slug: String,
        subscriptionId: Int,
        targetDollars: Double,
        onResult: (Boolean, String?) -> Unit,
    ) {
        viewModelScope.launch {
            _scaleSaving.value = true
            val result = runCatching {
                apiService.setSubscriptionScale(
                    subscriptionId = subscriptionId,
                    request = SetScaleRequest(targetDollars = targetDollars),
                )
            }
            _scaleSaving.value = false
            result.onSuccess {
                load(slug)            // re-fetch so scaled holdings populate
                onResult(true, null)
            }.onFailure { e ->
                onResult(false, e.message)
            }
        }
    }

    /** Clear the subscriber's scale (return to unscaled view). Reloads
     *  the portfolio so the scale banner disappears immediately. */
    fun clearScale(slug: String, subscriptionId: Int) {
        viewModelScope.launch {
            runCatching { apiService.clearSubscriptionScale(subscriptionId) }
                .onSuccess { load(slug) }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Phase D: Portfolio Resizer Components
// ─────────────────────────────────────────────────────────────────────────

/**
 * Card shown above the Holdings list for subscribers. Two states:
 *   • No scale set: "Adjust Portfolio Size" CTA
 *   • Scale active: badge with target_dollars + Edit/Clear actions
 *
 * Mirrors the iOS [ScaleCard]. Hidden by the parent for the owner viewing
 * their own page and for non-subscribers.
 */
@Composable
private fun ScaleCard(
    scale: PortfolioScale?,
    onTapEdit: () -> Unit,
    onTapClear: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (scale != null) {
        // Active-scale state
        Row(
            modifier = modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(CardBackground)
                .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Default.Tune,
                contentDescription = null,
                tint = PrimaryAccent,
                modifier = Modifier.size(20.dp),
            )
            Spacer(Modifier.width(10.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Scaled to ${formatCompactDollars(scale.targetDollars)}",
                    color = TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = "From ${formatCompactDollars(scale.unscaledPortfolioValue)} creator portfolio",
                    color = TextMuted,
                    fontSize = 11.sp,
                )
            }
            OutlinedButton(
                onClick = onTapEdit,
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                border = BorderStroke(1.dp, PrimaryAccent.copy(alpha = 0.5f)),
            ) {
                Icon(Icons.Default.Edit, contentDescription = "Edit", tint = PrimaryAccent, modifier = Modifier.size(14.dp))
                Spacer(Modifier.width(4.dp))
                Text("Edit", color = PrimaryAccent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            }
            Spacer(Modifier.width(6.dp))
            IconButton(onClick = onTapClear, modifier = Modifier.size(32.dp)) {
                Icon(
                    imageVector = Icons.Default.Close,
                    contentDescription = "Clear scale",
                    tint = TextMuted,
                    modifier = Modifier.size(16.dp),
                )
            }
        }
    } else {
        // No-scale CTA
        Row(
            modifier = modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(CardBackground)
                .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
                .clickable { onTapEdit() }
                .padding(horizontal = 14.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Default.Tune,
                contentDescription = null,
                tint = PrimaryAccent,
                modifier = Modifier.size(18.dp),
            )
            Spacer(Modifier.width(10.dp))
            Text(
                text = "Adjust Portfolio Size",
                color = TextPrimary,
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            Icon(
                imageVector = Icons.AutoMirrored.Filled.CallMade,
                contentDescription = null,
                tint = TextMuted,
                modifier = Modifier.size(14.dp),
            )
        }
    }
}

/** Compact dollar formatter: $10K, $1.2M, $500. Mirrors the iOS helper
 *  in [ScaleCard.formatDollars] so both platforms render the same. */
private fun formatCompactDollars(value: Double): String = when {
    value >= 1_000_000 -> "$%.1fM".format(value / 1_000_000)
    value >= 10_000 -> "$%.0fK".format(value / 1_000)
    value >= 1_000 -> "$%.1fK".format(value / 1_000)
    else -> "$%.0f".format(value)
}

/**
 * Footer that surfaces the count of positions which floor-rounded to 0
 * shares at the current scale. Only rendered in floor mode
 * (prefer_fractional=false). The string mirrors the iOS copy verbatim.
 */
@Composable
private fun BelowOneShareFooter(count: Int, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = Icons.Default.Info,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(12.dp),
        )
        Spacer(Modifier.width(6.dp))
        Text(
            text = "$count position${if (count == 1) "" else "s"} below 1 share at this scale — enable Show Fractional Shares in Settings to see them.",
            color = TextMuted,
            fontSize = 11.sp,
        )
    }
}

/**
 * Modal dialog presented when the subscriber taps "Adjust Portfolio Size"
 * or "Edit". Lets them type a dollar amount (numeric keyboard) and
 * submits to /subscriptions/<id>/scale.
 */
@Composable
private fun SetScaleDialog(
    ownerName: String,
    creatorPortfolioValue: Double?,
    currentTargetDollars: Double?,
    amount: String,
    onAmountChange: (String) -> Unit,
    isSaving: Boolean,
    errorText: String?,
    onCancel: () -> Unit,
    onSubmit: (Double) -> Unit,
) {
    Dialog(onDismissRequest = onCancel) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(20.dp))
                .background(CardBackground)
                .border(0.5.dp, CardBorder, RoundedCornerShape(20.dp))
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Headline + body
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = if (currentTargetDollars == null) "Adjust portfolio size"
                    else "Update portfolio size",
                    color = TextPrimary,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "All holdings on $ownerName's portfolio will be scaled to match. The scale is frozen at the moment you set it.",
                    color = TextSecondary,
                    fontSize = 12.sp,
                )
                // Compliance disclaimer per LAUNCH_PLAYBOOK.md — must be
                // visible at the moment the user commits to a $ amount.
                Text(
                    text = "For educational purposes only. This is not investment advice.",
                    color = TextMuted,
                    fontSize = 10.sp,
                )
            }

            // Creator portfolio context
            if (creatorPortfolioValue != null && creatorPortfolioValue > 0) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(AppBackground)
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("Creator portfolio", color = TextMuted, fontSize = 12.sp)
                    Spacer(Modifier.weight(1f))
                    Text(
                        text = "$%.0f".format(creatorPortfolioValue),
                        color = TextSecondary,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }

            // Dollar input (uses OutlinedTextField for the standard Compose
            // experience — the leading "$" prefix is rendered as a
            // leadingIcon so the actual TextField content stays numeric).
            OutlinedTextField(
                value = amount,
                onValueChange = { v ->
                    // Strip non-digit chars so paste/dictation can't sneak
                    // in commas or "$" — server expects a clean float.
                    onAmountChange(v.filter { it.isDigit() })
                },
                placeholder = { Text("0", color = TextMuted, fontSize = 24.sp) },
                leadingIcon = {
                    Text("$", color = TextSecondary, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = AppBackground,
                    unfocusedContainerColor = AppBackground,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary,
                    cursorColor = PrimaryAccent,
                    focusedBorderColor = PrimaryAccent,
                    unfocusedBorderColor = CardBorder,
                ),
                modifier = Modifier.fillMaxWidth(),
            )

            if (errorText != null) {
                Text(text = errorText, color = Losses, fontSize = 12.sp)
            }

            // Actions
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onCancel,
                    border = BorderStroke(1.dp, CardBorder),
                    modifier = Modifier.weight(1f),
                    enabled = !isSaving,
                ) {
                    Text("Cancel", color = TextSecondary, fontWeight = FontWeight.SemiBold)
                }
                Button(
                    onClick = {
                        val dollars = amount.toDoubleOrNull() ?: 0.0
                        if (dollars > 0) onSubmit(dollars)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                    modifier = Modifier.weight(1f),
                    enabled = !isSaving && amount.toDoubleOrNull()?.let { it > 0 } == true,
                ) {
                    if (isSaving) {
                        CircularProgressIndicator(
                            color = Color.White,
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(14.dp),
                        )
                        Spacer(Modifier.width(6.dp))
                    }
                    Text(
                        text = if (isSaving) "Saving..." else "Apply Scale",
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}
