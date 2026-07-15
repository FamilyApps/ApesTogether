package com.apestogether.app.ui.screens.topinfluencers

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.models.IndustryInfo
import com.apestogether.app.data.models.InfluencerEntry
import com.apestogether.app.ui.screens.leaderboard.GicsSectors
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Top Creators tab. Direct port of iOS [TopInfluencersView]. The list is
 * ranked by subscriber count (server-side) and filterable by GICS sector.
 *
 *  - Title row: "Top Creators" + "Ranked by subscriber count" subtitle.
 *  - Filter bar: "Industry" toggle button (with badge if a filter is
 *    active) + an inline pill chip showing the active sector (when the
 *    expandable panel is collapsed).
 *  - Expandable filter panel: horizontal scroll of sector chips +
 *    "Reset filters" link.
 *  - List: rank badge (medals for 1-3, number after), public name, two
 *    industry tag pills OR the unique-stocks count, subscriber count
 *    on the right.
 *  - Tapping a row → [onOpenPortfolio] with the user's slug.
 */
@Composable
fun TopInfluencersScreen(
    modifier: Modifier = Modifier,
    onOpenPortfolio: (String) -> Unit,
) {
    val viewModel: TopInfluencersViewModel = hiltViewModel()
    val state by viewModel.state.collectAsState()
    val selectedIndustry by viewModel.industry.collectAsState()
    var showFilters by remember { mutableStateOf(false) }
    val activeFilterCount = if (selectedIndustry != "all") 1 else 0

    LaunchedEffect(Unit) { viewModel.load() }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(AppBackground)
    ) {
        // Header strip
        HeaderStrip()

        // Filter bar
        FilterBar(
            activeFilterCount = activeFilterCount,
            showFilters = showFilters,
            selectedIndustry = selectedIndustry,
            onToggleFilters = { showFilters = !showFilters },
            onClearIndustry = { viewModel.setIndustry("all") },
        )

        // Expandable filter panel
        AnimatedVisibility(visible = showFilters) {
            FilterPanel(
                selectedIndustry = selectedIndustry,
                activeFilterCount = activeFilterCount,
                onSelect = { viewModel.setIndustry(it) },
            )
        }

        // Thin divider before the list
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(0.5.dp)
                .background(CardBorder)
        )

        // List
        Box(modifier = Modifier.weight(1f)) {
            when (val s = state) {
                TopInfluencersState.Loading -> CircularProgressIndicator(
                    color = PrimaryAccent,
                    modifier = Modifier.align(Alignment.Center),
                )

                is TopInfluencersState.Error -> Text(
                    text = s.message,
                    color = TextSecondary,
                    fontSize = 14.sp,
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )

                is TopInfluencersState.Loaded -> {
                    if (s.entries.isEmpty()) {
                        EmptyState(modifier = Modifier.align(Alignment.Center))
                    } else {
                        LazyColumn(modifier = Modifier.fillMaxSize()) {
                            items(items = s.entries, key = { it.user.id }) { entry ->
                                InfluencerRow(
                                    entry = entry,
                                    onClick = {
                                        entry.user.portfolioSlug?.takeIf { it.isNotBlank() }
                                            ?.let(onOpenPortfolio)
                                    },
                                )
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(start = 50.dp)
                                        .height(0.5.dp)
                                        .background(CardBorder)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Header
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun HeaderStrip() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(CardBackground.copy(alpha = 0.5f))
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text("Top Creators", color = TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Text("Ranked by subscriber count", color = TextMuted, fontSize = 11.sp)
    }
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(0.5.dp)
            .background(CardBorder.copy(alpha = 0.5f))
    )
}

// ─────────────────────────────────────────────────────────────────────────
// Filter bar (collapsed)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun FilterBar(
    activeFilterCount: Int,
    showFilters: Boolean,
    selectedIndustry: String,
    onToggleFilters: () -> Unit,
    onClearIndustry: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        IndustryToggleButton(
            activeFilterCount = activeFilterCount,
            showFilters = showFilters,
            onClick = onToggleFilters,
        )

        if (activeFilterCount > 0 && !showFilters) {
            ActiveFilterChip(
                label = selectedIndustry,
                onClear = onClearIndustry,
            )
        }
    }
}

@Composable
private fun IndustryToggleButton(
    activeFilterCount: Int,
    showFilters: Boolean,
    onClick: () -> Unit,
) {
    val tint = if (activeFilterCount > 0) PrimaryAccent else TextMuted
    val bg = if (activeFilterCount > 0) PrimaryAccent.copy(alpha = 0.1f) else CardBackground
    val border = if (activeFilterCount > 0) PrimaryAccent.copy(alpha = 0.3f) else CardBorder

    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(bg)
            .border(0.5.dp, border, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Icon(Icons.Default.Tune, null, tint = tint, modifier = Modifier.size(12.dp))
        Text("Industry", color = tint, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        if (activeFilterCount > 0) {
            Box(
                modifier = Modifier
                    .size(16.dp)
                    .clip(CircleShape)
                    .background(PrimaryAccent),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = "$activeFilterCount",
                    color = AppBackground,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
        Icon(
            imageVector = Icons.Default.ExpandMore,
            contentDescription = null,
            tint = tint,
            modifier = Modifier
                .size(9.dp)
                .rotate(if (showFilters) 180f else 0f),
        )
    }
}

@Composable
private fun ActiveFilterChip(label: String, onClear: () -> Unit) {
    Row(
        modifier = Modifier
            .clip(CircleShape)
            .background(PrimaryAccent.copy(alpha = 0.1f))
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(label, color = PrimaryAccent, fontSize = 11.sp, fontWeight = FontWeight.Medium)
        Icon(
            imageVector = Icons.Default.Close,
            contentDescription = "Clear filter",
            tint = PrimaryAccent,
            modifier = Modifier
                .size(10.dp)
                .clickable(onClick = onClear),
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Filter panel (expanded)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun FilterPanel(
    selectedIndustry: String,
    activeFilterCount: Int,
    onSelect: (String) -> Unit,
) {
    Column(
        modifier = Modifier
            .padding(horizontal = 16.dp, vertical = 0.dp)
            .padding(bottom = 8.dp)
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(CardBackground)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            "INDUSTRY",
            color = TextMuted,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.5.sp,
        )

        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            IndustryFilterChip(
                label = "All",
                isSelected = selectedIndustry == "all",
                onClick = { onSelect("all") },
            )
            GicsSectors.forEach { sector ->
                IndustryFilterChip(
                    label = sector,
                    isSelected = selectedIndustry == sector,
                    onClick = { onSelect(sector) },
                )
            }
        }

        if (activeFilterCount > 0) {
            Row(
                modifier = Modifier.clickable { onSelect("all") },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Icon(Icons.Default.Cancel, null, tint = TextMuted, modifier = Modifier.size(10.dp))
                Text("Reset filters", color = TextMuted, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun IndustryFilterChip(
    label: String,
    isSelected: Boolean,
    onClick: () -> Unit,
) {
    val bg = if (isSelected) PrimaryAccent else CardBackground
    val fg = if (isSelected) AppBackground else TextSecondary
    val border = if (isSelected) Color.Transparent else CardBorder

    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(bg)
            .border(0.5.dp, border, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 7.dp),
    ) {
        Text(label, color = fg, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Row
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun InfluencerRow(entry: InfluencerEntry, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        RankBadge(rank = entry.rank)

        Column(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = entry.user.publicName,
                color = TextPrimary,
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )

            if (entry.topIndustries.isNotEmpty()) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    entry.topIndustries.take(2).forEach { ind ->
                        IndustryTagPill(shortenIndustry(ind.name))
                    }
                }
            } else {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Icon(
                        imageVector = Icons.Default.People,
                        contentDescription = null,
                        tint = TextMuted,
                        modifier = Modifier.size(9.dp),
                    )
                    Text(
                        text = "${entry.uniqueStocks} stocks",
                        color = TextMuted,
                        fontSize = 10.sp,
                    )
                }
            }
        }

        Column(
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.People,
                    contentDescription = null,
                    tint = PrimaryAccent,
                    modifier = Modifier.size(11.dp),
                )
                Text(
                    text = "${entry.subscriberCount}",
                    color = PrimaryAccent,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
            Text("subscribers", color = TextMuted, fontSize = 9.sp)
        }
    }
}

@Composable
private fun RankBadge(rank: Int) {
    val fill = if (rank <= 3) PrimaryAccent.copy(alpha = 0.15f) else CardBackground
    Box(
        modifier = Modifier
            .size(36.dp)
            .clip(CircleShape)
            .background(fill),
        contentAlignment = Alignment.Center,
    ) {
        if (rank <= 3) {
            val medals = listOf("\uD83E\uDD47", "\uD83E\uDD48", "\uD83E\uDD49")
            Text(medals[rank - 1], fontSize = 16.sp)
        } else {
            Text(
                text = "$rank",
                color = TextSecondary,
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun IndustryTagPill(label: String) {
    Box(
        modifier = Modifier
            .clip(CircleShape)
            .background(PrimaryAccent.copy(alpha = 0.1f))
            .padding(horizontal = 6.dp, vertical = 2.dp),
    ) {
        Text(label, color = PrimaryAccent, fontSize = 9.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun EmptyState(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("No Creators Yet", color = TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold)
        Text(
            text = "As traders gain subscribers, the top creators will appear here. Share your portfolio to be the first!",
            color = TextSecondary,
            fontSize = 13.sp,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

/** Mirror of iOS [InfluencerRow.shortenIndustry]. */
private fun shortenIndustry(name: String): String {
    val map = linkedMapOf(
        "AUTO MANUFACTURERS" to "Auto",
        "CONSUMER ELECTRONICS" to "Tech",
        "SOFTWARE" to "Software",
        "SEMICONDUCTORS" to "Chips",
        "INTERNET" to "Internet",
        "BANKS" to "Finance",
        "CREDIT SERVICES" to "Finance",
        "INSURANCE" to "Insurance",
        "DRUG MANUFACTURERS" to "Pharma",
        "HEALTHCARE PLANS" to "Health",
        "ETF - INDEX FUND" to "ETF",
        "TECHNOLOGY" to "Tech",
        "FINANCIAL" to "Finance",
        "HEALTHCARE" to "Health",
    )
    val upper = name.uppercase()
    map.entries.firstOrNull { (key, _) -> key in upper }?.let { return it.value }
    return if (name.length > 10) name.take(8) + "…" else name
}

// ─────────────────────────────────────────────────────────────────────────
// State + ViewModel
// ─────────────────────────────────────────────────────────────────────────

sealed interface TopInfluencersState {
    data object Loading : TopInfluencersState
    data class Loaded(val entries: List<InfluencerEntry>) : TopInfluencersState
    data class Error(val message: String) : TopInfluencersState
}

@HiltViewModel
class TopInfluencersViewModel @Inject constructor(
    private val apiService: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow<TopInfluencersState>(TopInfluencersState.Loading)
    val state: StateFlow<TopInfluencersState> = _state.asStateFlow()

    private val _industry = MutableStateFlow("all")
    val industry: StateFlow<String> = _industry.asStateFlow()

    /**
     * Transient-failure resilience (a cold Vercel instance or a brief network
     * blip previously flashed the full-screen error): failures are retried
     * once after a short delay before ANY error is surfaced, and if content
     * is already on screen a failed re-fetch keeps it instead of replacing
     * it with the error state — subscriber counts changing mid-session must
     * never kick the user out to a retry screen. [reset] forces the loading
     * state when the current content is invalid (industry filter changed).
     */
    fun load(reset: Boolean = false) {
        viewModelScope.launch {
            val hadData = !reset && _state.value is TopInfluencersState.Loaded
            if (!hadData) _state.value = TopInfluencersState.Loading
            var result = runCatching { apiService.getTopInfluencers(_industry.value, limit = 20) }
            if (result.isFailure) {
                delay(RETRY_DELAY_MS)
                result = runCatching { apiService.getTopInfluencers(_industry.value, limit = 20) }
            }
            result
                .onSuccess { _state.value = TopInfluencersState.Loaded(it.entries) }
                .onFailure {
                    // Keep showing existing content on a failed refresh; only
                    // surface the error screen when there is nothing to show.
                    if (!hadData) {
                        _state.value = TopInfluencersState.Error(it.message ?: "Failed to load")
                    }
                }
        }
    }

    fun setIndustry(industry: String) {
        if (_industry.value == industry) return
        _industry.value = industry
        load(reset = true)
    }

    companion object {
        private const val RETRY_DELAY_MS = 1_500L
    }
}

