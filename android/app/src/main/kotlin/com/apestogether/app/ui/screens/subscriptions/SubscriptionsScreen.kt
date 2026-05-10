package com.apestogether.app.ui.screens.subscriptions

import com.apestogether.app.ui.screens.common.PlaceholderScreen
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * "Subscriptions" tab — equivalent to iOS [SubscriptionsView].
 *
 * TODO: Port `ios/ApesTogetherApp/Views/SubscriptionsView.swift`. Calls
 * `apiService.getSubscriptions()`. Two list sections: portfolios I follow
 * (subscriptionsMade) and people who follow me (subscribers). Tapping a
 * "subscribed-to" card shows recent trade activity for that portfolio.
 */
@Composable
fun SubscriptionsScreen(
    modifier: Modifier = Modifier,
    @Suppress("unused") onOpenPortfolio: (String) -> Unit,
) {
    PlaceholderScreen(
        modifier = modifier,
        title = "Subscriptions",
        body = "Portfolios you follow + people who follow you. iOS reference: SubscriptionsView.swift",
    )
}
