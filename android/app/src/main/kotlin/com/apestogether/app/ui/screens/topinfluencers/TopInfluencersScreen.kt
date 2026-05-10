package com.apestogether.app.ui.screens.topinfluencers

import com.apestogether.app.ui.screens.common.PlaceholderScreen
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * "Top Creators" tab — equivalent to iOS [TopInfluencersView].
 *
 * TODO: Port the full view from
 * `ios/ApesTogetherApp/Views/TopInfluencersView.swift` (~16KB, 400+ lines).
 * Endpoint: `apiService.getTopInfluencers(industry, limit)`.
 */
@Composable
fun TopInfluencersScreen(
    modifier: Modifier = Modifier,
    @Suppress("unused") onOpenPortfolio: (String) -> Unit,
) {
    PlaceholderScreen(
        modifier = modifier,
        title = "Top Creators",
        body = "List of highest-engagement traders coming soon. iOS reference: TopInfluencersView.swift",
    )
}
