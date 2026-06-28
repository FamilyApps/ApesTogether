package com.apestogether.app.ui.navigation

/**
 * Type-safe route definitions for the Compose Navigation graph.
 *
 * Tab screens (Leaderboard, TopInfluencers, MyPortfolio, Subscriptions)
 * mirror the iOS [MainTabView]. PortfolioDetail is pushed on top of any tab
 * when the user taps a leaderboard row or a deep-link arrives.
 */
sealed class Screen(val route: String) {
    // Pre-auth
    data object Login : Screen("login")

    // Tabs (iOS MainTabView equivalents)
    data object Leaderboard : Screen("leaderboard")
    data object TopInfluencers : Screen("top_influencers")
    data object MyPortfolio : Screen("my_portfolio")
    data object Subscriptions : Screen("subscriptions")

    // Pushed
    data object Settings : Screen("settings")

    // Pushed (no args). In-app W-9 collection (iOS `TaxInfoView`). Reached from
    // the Earnings card's "Complete your W-9 to get paid" CTA on the
    // Subscriptions tab — a creator must have a W-9 on file before payout.
    data object W9 : Screen("w9")

    // Pushed with arg
    data object PortfolioDetail : Screen("portfolio/{slug}") {
        fun route(slug: String) = "portfolio/$slug"
        const val ARG_SLUG = "slug"
    }

    // Pushed (no args). Reachable from MyPortfolio's empty-state CTA so
    // first-launch users can populate their holdings without going through
    // the post-subscribe onboarding nudge. The post-subscribe path
    // (EarnNudge → Add Stocks) is handled at the RootApp level instead of
    // via NavHost, mirroring iOS [ContentView]'s state-machine swap.
    data object AddStocks : Screen("add_stocks")
}
