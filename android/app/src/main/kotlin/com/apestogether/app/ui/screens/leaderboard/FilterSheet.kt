package com.apestogether.app.ui.screens.leaderboard

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary

/**
 * Holds all the leaderboard filter selections. Mirrors the four state vars
 * on iOS [LeaderboardView] (`pendingCategory`, `pendingSectors`,
 * `pendingFrequency`, `pendingHideLoQ`).
 */
data class LeaderboardFilters(
    val category: String = "all",          // "all" | "large_cap" | "small_cap"
    val sectors: Set<String> = emptySet(), // empty = all sectors
    val frequency: String = "any",         // "any" | "day_trader" | "moderate"
    val hideLoQ: Boolean = true,
) {
    val activeCount: Int
        get() = listOf(
            category != "all",
            sectors.isNotEmpty(),
            frequency != "any",
            !hideLoQ,
        ).count { it }
}

/** 11 GICS sectors — order matches iOS [LeaderboardView.gicsSectors]. */
val GicsSectors = listOf(
    "Technology", "Healthcare", "Financials", "Consumer Discretionary",
    "Communication Services", "Industrials", "Consumer Staples",
    "Energy", "Utilities", "Real Estate", "Materials",
)

/**
 * Bottom-sheet filter UI. Equivalent to iOS [FilterSheet]. Uses a "pending"
 * state internally so users can tweak selections and only commit them by
 * tapping **Apply Filters** (or revert via **Reset**, which clears the
 * pending state but does NOT close the sheet — same UX as iOS).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FilterSheet(
    initial: LeaderboardFilters,
    onDismiss: () -> Unit,
    onApply: (LeaderboardFilters) -> Unit,
) {
    var pending by remember { mutableStateOf(initial) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = AppBackground,
        contentColor = TextPrimary,
        scrimColor = Color.Black.copy(alpha = 0.6f),
        dragHandle = null,
    ) {
        Box {
            // ── Scrollable content ──
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp)
                    .padding(top = 16.dp, bottom = 96.dp), // leave room for sticky bar
                verticalArrangement = Arrangement.spacedBy(24.dp),
            ) {
                // Title row
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        text = "Filters",
                        color = TextPrimary,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }

                // ── Quality ──
                FilterSection(title = "Quality") {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = if (pending.hideLoQ) Icons.Default.Verified else Icons.Default.Shield,
                            contentDescription = null,
                            tint = PrimaryAccent,
                            modifier = Modifier.size(14.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "Hide low quality",
                            color = TextPrimary,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.weight(1f),
                        )
                        Switch(
                            checked = pending.hideLoQ,
                            onCheckedChange = { pending = pending.copy(hideLoQ = it) },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = AppBackground,
                                checkedTrackColor = PrimaryAccent,
                                uncheckedThumbColor = TextSecondary,
                                uncheckedTrackColor = CardBackground,
                                uncheckedBorderColor = CardBorder,
                            ),
                        )
                    }
                }

                // ── Market Cap ──
                FilterSection(title = "Market Cap") {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        FilterPill(
                            label = "All",
                            selected = pending.category == "all",
                            modifier = Modifier.weight(1f),
                            onClick = { pending = pending.copy(category = "all") },
                        )
                        FilterPill(
                            label = "Large Cap",
                            selected = pending.category == "large_cap",
                            modifier = Modifier.weight(1f),
                            onClick = { pending = pending.copy(category = "large_cap") },
                        )
                        FilterPill(
                            label = "Small Cap",
                            selected = pending.category == "small_cap",
                            modifier = Modifier.weight(1f),
                            onClick = { pending = pending.copy(category = "small_cap") },
                        )
                    }
                }

                // ── Trading Frequency ──
                FilterSection(title = "Trading Frequency") {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        FilterPill(
                            label = "Any",
                            selected = pending.frequency == "any",
                            modifier = Modifier.weight(1f),
                            onClick = { pending = pending.copy(frequency = "any") },
                        )
                        FilterPill(
                            label = "Day Traders",
                            selected = pending.frequency == "day_trader",
                            modifier = Modifier.weight(1f),
                            onClick = { pending = pending.copy(frequency = "day_trader") },
                        )
                        FilterPill(
                            label = "Moderate",
                            selected = pending.frequency == "moderate",
                            modifier = Modifier.weight(1f),
                            onClick = { pending = pending.copy(frequency = "moderate") },
                        )
                    }
                }

                // ── Sector (GICS) ──
                FilterSection(title = "Sector") {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(
                                color = CardBackground,
                                shape = RoundedCornerShape(12.dp),
                            )
                            .border(
                                width = 0.5.dp,
                                color = CardBorder,
                                shape = RoundedCornerShape(12.dp),
                            ),
                    ) {
                        SectorRow(
                            label = "All Sectors",
                            selected = pending.sectors.isEmpty(),
                            bold = true,
                            onClick = { pending = pending.copy(sectors = emptySet()) },
                        )
                        GicsSectors.forEach { sector ->
                            SectorRow(
                                label = sector,
                                selected = pending.sectors.contains(sector),
                                bold = false,
                                onClick = {
                                    val next = pending.sectors.toMutableSet()
                                    if (next.contains(sector)) next.remove(sector) else next.add(sector)
                                    pending = pending.copy(sectors = next)
                                },
                            )
                        }
                    }
                }
            }

            // ── Sticky bottom bar (Reset + Apply) ──
            Row(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .background(AppBackground)
                    .padding(horizontal = 20.dp, vertical = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                OutlinedButton(
                    onClick = {
                        pending = LeaderboardFilters() // defaults
                    },
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, CardBorder),
                    contentPadding = PaddingValues(0.dp),
                ) {
                    Text(
                        "Reset",
                        color = TextSecondary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Button(
                    onClick = { onApply(pending) },
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                    contentPadding = PaddingValues(0.dp),
                ) {
                    Text(
                        "Apply Filters",
                        color = AppBackground,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

@Composable
private fun FilterSection(
    title: String,
    content: @Composable () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(
            text = title.uppercase(),
            color = TextMuted,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.8.sp,
        )
        content()
    }
}

@Composable
private fun FilterPill(
    label: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Box(
        modifier = modifier
            .background(
                color = if (selected) PrimaryAccent else CardBackground,
                shape = RoundedCornerShape(10.dp),
            )
            .border(
                width = 0.5.dp,
                color = if (selected) Color.Transparent else CardBorder,
                shape = RoundedCornerShape(10.dp),
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = label,
            color = if (selected) AppBackground else TextSecondary,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun SectorRow(
    label: String,
    selected: Boolean,
    bold: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(
                color = if (selected && bold) PrimaryAccent.copy(alpha = 0.10f) else Color.Transparent,
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = if (selected) Icons.Default.CheckCircle else Icons.Default.RadioButtonUnchecked,
            contentDescription = null,
            tint = if (selected) PrimaryAccent else TextMuted,
            modifier = Modifier.size(18.dp),
        )
        Spacer(Modifier.width(10.dp))
        Text(
            text = label,
            color = TextPrimary,
            fontSize = 14.sp,
            fontWeight = if (bold) FontWeight.SemiBold else FontWeight.Medium,
        )
    }
}

