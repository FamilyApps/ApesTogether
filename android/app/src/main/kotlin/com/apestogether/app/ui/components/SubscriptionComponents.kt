package com.apestogether.app.ui.components

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.apestogether.app.data.billing.SubscriptionPlan
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Gains
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary

/**
 * Lightweight UX state for the Subscribe button flow. Shared between
 * PortfolioDetailViewModel and LeaderboardViewModel since both can launch
 * Play Billing.
 */
sealed interface SubscribeUiState {
    data object Idle : SubscribeUiState
    data object Processing : SubscribeUiState
    data class Error(val message: String) : SubscribeUiState
    data object Success : SubscribeUiState
}

/**
 * Two-pill plan toggle (Annual / Monthly). Annual is the recommended
 * default — same pricing as iOS (`$69/yr`, ~36% savings vs `$9/mo`).
 *
 * Used both above the Subscribe CTA on `PortfolioDetailScreen` and inside
 * the expanded leaderboard card.
 */
@Composable
fun CompactPlanToggle(
    selected: SubscriptionPlan,
    onSelect: (SubscriptionPlan) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(CardBackground)
            .border(0.5.dp, CardBorder, RoundedCornerShape(10.dp))
            .padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        PlanChip(
            label = "Annual",
            sublabel = "\$69/yr · save 36%",
            isSelected = selected == SubscriptionPlan.Annual,
            modifier = Modifier.weight(1f),
            onClick = { onSelect(SubscriptionPlan.Annual) },
        )
        PlanChip(
            label = "Monthly",
            sublabel = "\$9/mo",
            isSelected = selected == SubscriptionPlan.Monthly,
            modifier = Modifier.weight(1f),
            onClick = { onSelect(SubscriptionPlan.Monthly) },
        )
    }
}

@Composable
private fun PlanChip(
    label: String,
    sublabel: String,
    isSelected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(if (isSelected) PrimaryAccent.copy(alpha = 0.15f) else Color.Transparent)
            .clickable(onClick = onClick)
            .padding(vertical = 8.dp, horizontal = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(
            text = label,
            color = if (isSelected) PrimaryAccent else TextPrimary,
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = sublabel,
            color = if (isSelected) PrimaryAccent.copy(alpha = 0.85f) else TextMuted,
            fontSize = 10.sp,
        )
    }
}

/**
 * Inline banner that pops below the Subscribe CTA after a billing attempt:
 *  - Idle / Processing → nothing (Processing is shown via spinner on the
 *    button itself).
 *  - Success → green "You're subscribed!" banner.
 *  - Error → red banner with message; tap to dismiss.
 */
@Composable
fun SubscribeStatusBanner(
    state: SubscribeUiState,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    when (state) {
        is SubscribeUiState.Error -> {
            Row(
                modifier = modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(Losses.copy(alpha = 0.1f))
                    .border(0.5.dp, Losses.copy(alpha = 0.3f), RoundedCornerShape(10.dp))
                    .clickable(onClick = onDismiss)
                    .padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = state.message,
                    color = Losses,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    "Dismiss",
                    color = Losses.copy(alpha = 0.7f),
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
        SubscribeUiState.Success -> {
            Row(
                modifier = modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(Gains.copy(alpha = 0.1f))
                    .border(0.5.dp, Gains.copy(alpha = 0.3f), RoundedCornerShape(10.dp))
                    .padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "You're subscribed! Pull to refresh to see your alerts.",
                    color = Gains,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
        SubscribeUiState.Idle, SubscribeUiState.Processing -> Unit
    }
}

/** Walks the [Context] chain to find the host [Activity], or null if not on one. */
fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}
