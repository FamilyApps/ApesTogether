package com.apestogether.app.ui.screens.leaderboard

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.spring
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.ArrowDropUp
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material.icons.filled.WorkspacePremium
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.models.LeaderboardEntry
import com.apestogether.app.ui.components.SparklineView
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
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
import kotlin.math.absoluteValue

/**
 * Leaderboard tab. Direct port of iOS [LeaderboardView] in
 * `ios/.../LeaderboardView.swift`. Visual + interaction parity is the goal —
 * any divergence is a bug.
 *
 * Layout (top → bottom):
 *  1. Period pills (1D / 1W / 1M / 3M / YTD / 1Y) + Filter button (with badge
 *     showing the count of non-default filters).
 *  2. S&P 500 benchmark banner ("S&P 500 +x.yz%   1W").
 *  3. Scrollable list of [LeaderboardCard]s — tap a card to expand it
 *     in-place, revealing stats, sector mix, View Portfolio + Subscribe CTAs.
 *  4. Filter modal bottom sheet on tap of the filter icon.
 */
@Composable
fun LeaderboardScreen(
    modifier: Modifier = Modifier,
    onOpenPortfolio: (String) -> Unit,
) {
    val viewModel: LeaderboardViewModel = hiltViewModel()
    val state by viewModel.state.collectAsState()
    val period by viewModel.period.collectAsState()
    val filters by viewModel.filters.collectAsState()

    var showFilters by remember { mutableStateOf(false) }
    var expandedEntryId by remember { mutableStateOf<Int?>(null) }
    var autoExpandedTop by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) { viewModel.refresh() }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(AppBackground),
    ) {
        // ── Period pills + Filter button ──
        PeriodPillRow(
            selected = period,
            filterBadgeCount = filters.activeCount,
            onPeriodSelected = {
                expandedEntryId = null
                autoExpandedTop = true
                viewModel.setPeriod(it)
            },
            onFilterTap = { showFilters = true },
        )

        // ── S&P 500 banner ──
        Sp500Banner(
            sp500Return = (state as? LeaderboardState.Loaded)?.sp500Return ?: 0.0,
            period = period,
        )

        // ── List / states ──
        when (val s = state) {
            LeaderboardState.Loading -> LoadingPlaceholder()
            is LeaderboardState.Error -> ErrorPlaceholder(
                message = s.message,
                onRetry = { viewModel.refresh() },
            )

            is LeaderboardState.Loaded -> {
                if (s.entries.isEmpty()) {
                    EmptyPlaceholder(onRefresh = { viewModel.refresh() })
                } else {
                    LazyColumn(
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        items(s.entries, key = { it.user.id }) { entry ->
                            val isExpanded =
                                expandedEntryId?.let { it == entry.user.id }
                                    ?: (autoExpandedTop && entry.rank == 1)
                            LeaderboardCard(
                                entry = entry,
                                period = period,
                                isExpanded = isExpanded,
                                onTap = {
                                    autoExpandedTop = false
                                    expandedEntryId =
                                        if (expandedEntryId == entry.user.id) null else entry.user.id
                                },
                                onOpenPortfolio = {
                                    entry.user.portfolioSlug
                                        ?.takeIf { it.isNotBlank() }
                                        ?.let(onOpenPortfolio)
                                },
                                onSubscribe = {
                                    // TODO: wire to Play Billing — see LAUNCH_TODO §C.
                                    // For now this is a no-op so the button is visible
                                    // for visual parity with iOS.
                                },
                            )
                        }
                    }
                }
            }
        }
    }

    if (showFilters) {
        FilterSheet(
            initial = filters,
            onDismiss = { showFilters = false },
            onApply = {
                viewModel.setFilters(it)
                expandedEntryId = null
                autoExpandedTop = true
                showFilters = false
            },
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Period pill row + Filter button (mirrors iOS LeaderboardView 102-150)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun PeriodPillRow(
    selected: String,
    filterBadgeCount: Int,
    onPeriodSelected: (String) -> Unit,
    onFilterTap: () -> Unit,
) {
    val periods = remember { listOf("1D", "1W", "1M", "3M", "YTD", "1Y") }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(
            modifier = Modifier.weight(1f),
        ) {
            periods.forEach { p ->
                val isActive = p == selected
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(8.dp))
                        .background(if (isActive) PrimaryAccent else Color.Transparent)
                        .clickable { onPeriodSelected(p) }
                        .padding(vertical = 8.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = p,
                        color = if (isActive) AppBackground else TextMuted,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }

        // Filter button (with badge if any active filters)
        Box {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(
                        if (filterBadgeCount > 0) PrimaryAccent.copy(alpha = 0.15f)
                        else CardBackground
                    )
                    .border(
                        width = 0.5.dp,
                        color = if (filterBadgeCount > 0) PrimaryAccent.copy(alpha = 0.4f)
                        else CardBorder,
                        shape = RoundedCornerShape(8.dp),
                    )
                    .clickable(onClick = onFilterTap),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Default.FilterList,
                    contentDescription = "Filters",
                    tint = if (filterBadgeCount > 0) PrimaryAccent else TextMuted,
                    modifier = Modifier.size(16.dp),
                )
            }
            if (filterBadgeCount > 0) {
                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .size(16.dp)
                        .clip(CircleShape)
                        .background(PrimaryAccent),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "$filterBadgeCount",
                        color = AppBackground,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// S&P 500 banner (mirrors iOS LeaderboardView 153-184)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun Sp500Banner(sp500Return: Double, period: String) {
    Column {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(CardBackground)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Icon(
                imageVector = Icons.Default.ShowChart,
                contentDescription = null,
                tint = PrimaryAccent,
                modifier = Modifier.size(14.dp),
            )
            Text(
                text = "S&P 500",
                color = TextSecondary,
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = formatPercent(sp500Return, decimals = 2),
                color = if (sp500Return >= 0) Gains else Losses,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.weight(1f))
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(CardBorder.copy(alpha = 0.3f))
                    .padding(horizontal = 8.dp, vertical = 3.dp),
            ) {
                Text(
                    text = period,
                    color = TextMuted,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
        Divider(color = CardBorder.copy(alpha = 0.3f), thickness = 0.5.dp)
    }
}

// ─────────────────────────────────────────────────────────────────────────
// State placeholders
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun LoadingPlaceholder() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator(color = PrimaryAccent)
    }
}

@Composable
private fun ErrorPlaceholder(message: String, onRetry: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(
                imageVector = Icons.Default.Refresh,
                contentDescription = null,
                tint = PrimaryAccent.copy(alpha = 0.6f),
                modifier = Modifier.size(48.dp),
            )
            Text("Error", color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Text(
                text = message,
                color = TextSecondary,
                fontSize = 14.sp,
            )
            Button(
                onClick = onRetry,
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                shape = RoundedCornerShape(12.dp),
            ) {
                Text("Retry", color = AppBackground, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun EmptyPlaceholder(onRefresh: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(
                imageVector = Icons.Default.EmojiEvents,
                contentDescription = null,
                tint = PrimaryAccent.copy(alpha = 0.6f),
                modifier = Modifier.size(48.dp),
            )
            Text("No Rankings Yet", color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Text(
                text = "Rankings are calculated during market hours.\nCheck back soon!",
                color = TextSecondary,
                fontSize = 14.sp,
            )
            Button(
                onClick = onRefresh,
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                shape = RoundedCornerShape(12.dp),
            ) {
                Text("Refresh", color = AppBackground, fontWeight = FontWeight.Bold)
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Card (mirrors iOS LeaderboardCard 471-756)
// ─────────────────────────────────────────────────────────────────────────

/**
 * Compose's default [Text] adds significant vertical font padding
 * (`includeFontPadding = true`) and uses Material3's `bodyLarge` line
 * height (24sp) even when fontSize is overridden — together that's
 * roughly +12dp per Text relative to SwiftUI. For dense list rows we
 * disable both so 14sp text only occupies ~14dp instead of ~24dp,
 * letting us match the iOS row count (~9 visible vs ~7.5 before).
 */
private fun tightTextStyle(fontSize: androidx.compose.ui.unit.TextUnit): TextStyle = TextStyle(
    fontSize = fontSize,
    lineHeight = fontSize,
    platformStyle = PlatformTextStyle(includeFontPadding = false),
    lineHeightStyle = LineHeightStyle(
        alignment = LineHeightStyle.Alignment.Center,
        trim = LineHeightStyle.Trim.Both,
    ),
)

@Composable
private fun LeaderboardCard(
    entry: LeaderboardEntry,
    period: String,
    isExpanded: Boolean,
    onTap: () -> Unit,
    onOpenPortfolio: () -> Unit,
    onSubscribe: () -> Unit,
) {
    val rankTint: Color? = when (entry.rank) {
        1 -> Color(0xFFFFD700).copy(alpha = 0.12f)
        2 -> Color(0xFFC0C0C0).copy(alpha = 0.08f)
        3 -> Color(0xFFCD7F32).copy(alpha = 0.08f)
        else -> null
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(CardBackground)
            .then(
                if (rankTint != null) Modifier.background(rankTint) else Modifier
            )
            .border(
                width = if (isExpanded) 1.dp else 0.5.dp,
                color = if (isExpanded) PrimaryAccent.copy(alpha = 0.25f)
                else CardBorder.copy(alpha = 0.4f),
                shape = RoundedCornerShape(14.dp),
            )
            .clickable(onClick = onTap),
    ) {
        // ── Compact row ──
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            RankBadge(rank = entry.rank, rankChange = entry.rankChange)

            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(3.dp),
            ) {
                Text(
                    text = entry.user.publicName,
                    color = TextPrimary,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    style = tightTextStyle(14.sp),
                )
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    SubBadge(
                        icon = Icons.Default.Star,
                        text = "${entry.subscriberCount}",
                    )
                    val tpw = entry.avgTradesPerWeek
                    if (tpw != null && tpw > 0) {
                        SubBadge(
                            icon = Icons.Default.SwapHoriz,
                            text = "%.0f/wk".format(tpw),
                        )
                    }
                }
            }

            // Sparkline
            SparklineView(
                dataPoints = entry.sparklineData ?: emptyList(),
                sp500Points = entry.sp500SparklineData ?: emptyList(),
                isPositive = (entry.alphaVsSp500 ?: entry.returnPercent) >= 0,
                modifier = Modifier
                    .width(52.dp)
                    .height(26.dp),
            )

            // Alpha vs S&P (the headline metric)
            val alpha = entry.alphaVsSp500
                ?: (entry.returnPercent - (entry.sp500Return ?: 0.0))
            Column(
                horizontalAlignment = Alignment.End,
                modifier = Modifier.widthIn(min = 56.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    text = formatPercent(alpha, decimals = 1),
                    color = if (alpha >= 0) Gains else Losses,
                    fontWeight = FontWeight.Bold,
                    style = tightTextStyle(15.sp),
                )
                Text(
                    text = "vs S&P",
                    color = TextMuted,
                    fontWeight = FontWeight.Medium,
                    style = tightTextStyle(8.sp),
                )
            }

            // Chevron
            Icon(
                imageVector = Icons.Default.ArrowDropDown,
                contentDescription = null,
                tint = TextMuted,
                modifier = Modifier
                    .size(16.dp)
                    .rotate(if (isExpanded) 180f else 0f),
            )
        }

        AnimatedVisibility(
            visible = isExpanded,
            enter = fadeIn(animationSpec = spring(dampingRatio = 0.85f)) +
                expandVertically(animationSpec = spring(dampingRatio = 0.85f)),
            exit = fadeOut() + shrinkVertically(),
        ) {
            ExpandedDetail(
                entry = entry,
                onOpenPortfolio = onOpenPortfolio,
                onSubscribe = onSubscribe,
            )
        }
    }
}

@Composable
private fun RankBadge(rank: Int, rankChange: Int?) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Box(
            modifier = Modifier
                .size(30.dp)
                .clip(CircleShape)
                .background(
                    when (rank) {
                        1 -> Color(0xFFFFD700).copy(alpha = 0.2f)
                        2 -> Color(0xFFC0C0C0).copy(alpha = 0.2f)
                        3 -> Color(0xFFCD7F32).copy(alpha = 0.2f)
                        else -> CardBorder.copy(alpha = 0.3f)
                    }
                ),
            contentAlignment = Alignment.Center,
        ) {
            when (rank) {
                1 -> Text("🥇", fontSize = 16.sp)
                2 -> Text("🥈", fontSize = 16.sp)
                3 -> Text("🥉", fontSize = 16.sp)
                else -> Text(
                    text = "$rank",
                    color = TextSecondary,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }

        when {
            rankChange == null || rankChange == 0 -> {
                Text(
                    text = "—",
                    color = TextMuted.copy(alpha = 0.5f),
                    fontWeight = FontWeight.Medium,
                    style = tightTextStyle(10.sp),
                )
            }

            rankChange > 0 -> Icon(
                // Filled solid triangle, matches iOS `arrowtriangle.up.fill`.
                imageVector = Icons.Default.ArrowDropUp,
                contentDescription = null,
                tint = Gains,
                modifier = Modifier.size(14.dp),
            )

            else -> Icon(
                imageVector = Icons.Default.ArrowDropDown,
                contentDescription = null,
                tint = Losses,
                modifier = Modifier.size(14.dp),
            )
        }
    }
}

@Composable
private fun SubBadge(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    text: String,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(10.dp),
        )
        Text(
            text = text,
            color = TextMuted,
            fontWeight = FontWeight.Medium,
            style = tightTextStyle(10.sp),
        )
    }
}

@Composable
private fun ExpandedDetail(
    entry: LeaderboardEntry,
    onOpenPortfolio: () -> Unit,
    onSubscribe: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Divider(
            color = CardBorder.copy(alpha = 0.3f),
            thickness = 0.5.dp,
            modifier = Modifier.padding(horizontal = 14.dp),
        )

        // Stats row
        Row(
            modifier = Modifier
                .padding(horizontal = 14.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(AppBackground.copy(alpha = 0.5f))
                .fillMaxWidth()
                .padding(vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            StatCell(
                title = "Subscribers",
                value = "${entry.subscriberCount}",
                modifier = Modifier.weight(1f),
            )
            StatDivider()
            StatCell(
                title = "Stocks",
                value = "${entry.uniqueStocks ?: 0}",
                modifier = Modifier.weight(1f),
            )
            StatDivider()
            StatCell(
                title = "Trades/wk",
                value = "%.1f".format(entry.avgTradesPerWeek ?: 0.0),
                modifier = Modifier.weight(1f),
            )
            StatDivider()
            StatCell(
                title = "Return",
                value = formatPercent(entry.returnPercent, decimals = 1),
                modifier = Modifier.weight(1f),
            )
        }

        // Sector mix
        val mix = entry.industryMix?.takeIf { it.isNotEmpty() }
        if (mix != null) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = "PORTFOLIO MIX",
                    color = TextMuted,
                    fontSize = 9.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.6.sp,
                    modifier = Modifier.padding(horizontal = 14.dp),
                )

                StackedSectorBar(
                    mix = mix,
                    modifier = Modifier
                        .padding(horizontal = 14.dp)
                        .fillMaxWidth()
                        .height(6.dp)
                        .clip(RoundedCornerShape(50)),
                )

                Row(
                    modifier = Modifier
                        .horizontalScroll(rememberScrollState())
                        .padding(horizontal = 14.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    mix.entries.sortedByDescending { it.value }.forEach { (name, pct) ->
                        SectorChip(name = name, pct = pct)
                    }
                }
            }
        }

        // Action buttons (stacked, like iOS lines 690-727)
        Column(
            modifier = Modifier
                .padding(horizontal = 14.dp, vertical = 0.dp)
                .padding(bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedButton(
                onClick = onOpenPortfolio,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 40.dp),
                shape = RoundedCornerShape(10.dp),
                border = BorderStroke(1.dp, PrimaryAccent.copy(alpha = 0.4f)),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = PrimaryAccent),
                contentPadding = PaddingValues(vertical = 10.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.ShowChart,
                    contentDescription = null,
                    tint = PrimaryAccent,
                    modifier = Modifier.size(12.dp),
                )
                Spacer(Modifier.width(5.dp))
                Text(
                    "View Portfolio",
                    color = PrimaryAccent,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }

            Button(
                onClick = onSubscribe,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 40.dp),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                contentPadding = PaddingValues(vertical = 10.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.WorkspacePremium,
                    contentDescription = null,
                    tint = AppBackground,
                    modifier = Modifier.size(12.dp),
                )
                Spacer(Modifier.width(5.dp))
                Text(
                    text = "Try Free for 7 Days, then $${entry.subscriptionPrice.toInt()}/mo",
                    color = AppBackground,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun StatCell(
    title: String,
    value: String,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Text(value, color = TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.Bold)
        Text(title, color = TextMuted, fontSize = 9.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun StatDivider() {
    Box(
        modifier = Modifier
            .width(0.5.dp)
            .height(28.dp)
            .background(CardBorder.copy(alpha = 0.4f))
    )
}

@Composable
private fun StackedSectorBar(
    mix: Map<String, Double>,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier) {
        val w = size.width
        val total = mix.values.sum().takeIf { it > 0 } ?: 1.0
        var cursor = 0f
        mix.entries.sortedByDescending { it.value }.forEach { (name, pct) ->
            val widthPx = ((pct / total).toFloat() * w).coerceAtLeast(2.dp.toPx())
            drawRect(
                color = sectorColor(name),
                topLeft = androidx.compose.ui.geometry.Offset(cursor, 0f),
                size = androidx.compose.ui.geometry.Size(widthPx, size.height),
            )
            cursor += widthPx
        }
    }
}

@Composable
private fun SectorChip(name: String, pct: Double) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
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

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

private fun formatPercent(value: Double, decimals: Int): String {
    val sign = if (value >= 0) "+" else "−"
    val abs = value.absoluteValue
    return "$sign${"%.${decimals}f".format(abs)}%"
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
// State + ViewModel
// ─────────────────────────────────────────────────────────────────────────

sealed interface LeaderboardState {
    data object Loading : LeaderboardState
    data class Loaded(
        val entries: List<LeaderboardEntry>,
        val sp500Return: Double,
    ) : LeaderboardState

    data class Error(val message: String) : LeaderboardState
}

@HiltViewModel
class LeaderboardViewModel @Inject constructor(
    private val apiService: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow<LeaderboardState>(LeaderboardState.Loading)
    val state: StateFlow<LeaderboardState> = _state.asStateFlow()

    private val _period = MutableStateFlow("1W")
    val period: StateFlow<String> = _period.asStateFlow()

    private val _filters = MutableStateFlow(LeaderboardFilters())
    val filters: StateFlow<LeaderboardFilters> = _filters.asStateFlow()

    fun setPeriod(period: String) {
        _period.value = period
        refresh()
    }

    fun setFilters(filters: LeaderboardFilters) {
        _filters.value = filters
        refresh()
    }

    fun refresh() {
        val period = _period.value
        val filters = _filters.value
        viewModelScope.launch {
            _state.value = LeaderboardState.Loading
            runCatching {
                apiService.getLeaderboard(
                    period = period,
                    category = filters.category,
                    activeEdge = if (filters.hideLoQ) 1 else 0,
                    industry = if (filters.sectors.isEmpty()) "all"
                    else filters.sectors.sorted().joinToString(","),
                    frequency = filters.frequency,
                )
            }
                .onSuccess { resp ->
                    _state.value = LeaderboardState.Loaded(
                        entries = resp.entries,
                        sp500Return = resp.sp500Return ?: 0.0,
                    )
                }
                .onFailure { e ->
                    _state.value = LeaderboardState.Error(e.message ?: "Failed to load leaderboard")
                }
        }
    }
}
