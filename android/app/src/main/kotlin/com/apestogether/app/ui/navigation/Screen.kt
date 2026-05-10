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

    // Pushed with arg
    data object PortfolioDetail : Screen("portfolio/{slug}") {
        fun route(slug: String) = "portfolio/$slug"
        const val ARG_SLUG = "slug"
    }
}
