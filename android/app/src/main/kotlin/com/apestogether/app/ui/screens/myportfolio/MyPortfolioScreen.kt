package com.apestogether.app.ui.screens.myportfolio

import com.apestogether.app.ui.screens.common.PlaceholderScreen
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * "Portfolio" tab — equivalent to iOS [MyPortfolioView].
 *
 * TODO: Port `ios/ApesTogetherApp/Views/MyPortfolioView.swift` and
 * `PortfolioDetailView.swift` (the latter is shared between owner/non-owner
 * views via the `is_owner` field in the response).
 *
 * Pulls /portfolio/<own_slug> using the user's slug from getCurrentUser().
 */
@Composable
fun MyPortfolioScreen(modifier: Modifier = Modifier) {
    PlaceholderScreen(
        modifier = modifier,
        title = "My Portfolio",
        body = "Your holdings, recent trades, and earnings appear here. iOS reference: MyPortfolioView.swift",
    )
}
