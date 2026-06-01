package com.apestogether.app.ui.components

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.Gains
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary

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
 * the expanded leaderboard card. Visual port of iOS [CompactPlanToggle].
 *
 * Sizes/padding track the iOS source-of-truth (CompactPlanToggle.swift:
 * title 10, price 13, badge 9 pt; segment v8/h10; badge h5/v2; container
 * pad 3, radius 10). The only deviation is price 14sp (iOS 13) — a single
 * point to offset Roboto rendering slightly smaller than SF Pro. Keep the
 * badge compact: an oversized badge was the main parity gap on Android.
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
            .background(Color.White.copy(alpha = 0.06f))
            .border(1.dp, Color.White.copy(alpha = 0.04f), RoundedCornerShape(10.dp))
            .padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        PlanChip(
            title = "Annual",
            price = "\$69/yr",
            badge = "Save 36%",
            isSelected = selected == SubscriptionPlan.Annual,
            modifier = Modifier.weight(1f),
            onClick = { onSelect(SubscriptionPlan.Annual) },
        )
        PlanChip(
            title = "Monthly",
            price = "\$9/mo",
            badge = null,
            isSelected = selected == SubscriptionPlan.Monthly,
            modifier = Modifier.weight(1f),
            onClick = { onSelect(SubscriptionPlan.Monthly) },
        )
    }
}

@Composable
private fun PlanChip(
    title: String,
    price: String,
    badge: String?,
    isSelected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    // iOS draws a 1px stroke at 55% PrimaryAccent alpha around the selected
    // chip; unselected chips have no stroke at all (clear color in SwiftUI).
    val borderModifier = if (isSelected) {
        Modifier.border(1.dp, PrimaryAccent.copy(alpha = 0.55f), RoundedCornerShape(8.dp))
    } else {
        Modifier
    }
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(if (isSelected) PrimaryAccent.copy(alpha = 0.12f) else Color.Transparent)
            .then(borderModifier)
            .clickable(onClick = onClick)
            .padding(vertical = 8.dp, horizontal = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(horizontalAlignment = Alignment.Start) {
            // Title row ("Annual" / "Monthly") — small, medium weight,
            // muted for the unselected chip.
            Text(
                text = title,
                color = if (isSelected) TextSecondary else TextMuted,
                fontSize = 10.sp,
                fontWeight = FontWeight.Medium,
            )
            // Price row ("$69/yr" / "$9/mo") — the prominent label.
            Text(
                text = price,
                color = if (isSelected) TextPrimary else TextSecondary,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
            )
        }
        // Optional capsule badge (only Annual carries "Save 36%").
        // iOS inverts the badge in the selected state — solid PrimaryAccent
        // pill with dark text — and shows a translucent green pill with
        // green text when unselected.
        if (badge != null) {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(
                        if (isSelected) PrimaryAccent
                        else PrimaryAccent.copy(alpha = 0.18f)
                    )
                    .padding(horizontal = 5.dp, vertical = 2.dp),
            ) {
                Text(
                    text = badge,
                    color = if (isSelected) AppBackground else PrimaryAccent,
                    fontSize = 9.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    softWrap = false,
                )
            }
        }
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
