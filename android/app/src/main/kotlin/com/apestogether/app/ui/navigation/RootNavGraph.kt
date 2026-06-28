package com.apestogether.app.ui.navigation

import com.apestogether.app.ui.screens.login.LoginScreen
import com.apestogether.app.ui.screens.main.MainTabsScreen
import com.apestogether.app.ui.screens.onboarding.AddStocksScreen
import com.apestogether.app.ui.screens.portfolio.PortfolioDetailScreen
import com.apestogether.app.ui.screens.settings.SettingsScreen
import com.apestogether.app.ui.screens.settings.TaxInfoScreen
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument

/**
 * Routes available across the entire app.
 *
 * "auth" graph:    Login screen.
 * "main" graph:    Bottom-tab UI (Leaderboard / TopInfluencers /
 *                  MyPortfolio / Subscriptions). Settings, PortfolioDetail,
 *                  and AddStocks are pushed on top of any tab.
 *
 * Deep-link routing (`https://apestogether.ai/p/<slug>`) is handled by
 * [com.apestogether.app.ui.RootApp] now — it either pre-empts the NavHost
 * with the [com.apestogether.app.ui.screens.onboarding.ReferralPreviewScreen]
 * (when unauthed) or invokes [navController] directly with the
 * [Screen.PortfolioDetail] route (when authed). This file is therefore a
 * pure NavHost wrapper with no implicit deep-link handling.
 */
@Composable
fun RootNavGraph(
    navController: NavHostController,
    startAuthenticated: Boolean,
) {
    val startRoute = if (startAuthenticated) "main" else Screen.Login.route

    NavHost(navController = navController, startDestination = startRoute) {

        composable(Screen.Login.route) {
            LoginScreen(
                onSignedIn = {
                    navController.navigate("main") {
                        popUpTo(Screen.Login.route) { inclusive = true }
                    }
                },
            )
        }

        composable("main") {
            MainTabsScreen(
                onOpenPortfolio = { slug ->
                    navController.navigate(Screen.PortfolioDetail.route(slug))
                },
                onOpenSettings = {
                    navController.navigate(Screen.Settings.route)
                },
                onOpenAddStocks = {
                    navController.navigate(Screen.AddStocks.route)
                },
                onOpenW9 = {
                    navController.navigate(Screen.W9.route)
                },
                onSignedOut = {
                    navController.navigate(Screen.Login.route) {
                        popUpTo("main") { inclusive = true }
                    }
                },
            )
        }

        composable(
            route = Screen.PortfolioDetail.route,
            arguments = listOf(navArgument(Screen.PortfolioDetail.ARG_SLUG) {
                type = NavType.StringType
            }),
        ) { backStackEntry ->
            val slug = backStackEntry.arguments?.getString(Screen.PortfolioDetail.ARG_SLUG).orEmpty()
            PortfolioDetailScreen(
                slug = slug,
                onBack = { navController.popBackStack() },
            )
        }

        composable(Screen.Settings.route) {
            SettingsScreen(
                onBack = { navController.popBackStack() },
                onSignedOut = {
                    navController.navigate(Screen.Login.route) {
                        popUpTo(0) { inclusive = true }
                    }
                },
            )
        }

        composable(Screen.W9.route) {
            TaxInfoScreen(onClose = { navController.popBackStack() })
        }

        composable(Screen.AddStocks.route) {
            AddStocksScreen(
                showSkip = false,
                showBack = true,
                onBack = { navController.popBackStack() },
                onComplete = { navController.popBackStack() },
            )
        }
    }
}

/** Pulls the portfolio slug out of `https://apestogether.ai/p/<slug>`. */
internal fun extractSlugFromDeepLink(uri: Uri): String? {
    val segments = uri.pathSegments
    val pIdx = segments.indexOf("p")
    return if (pIdx >= 0 && pIdx + 1 < segments.size) segments[pIdx + 1] else null
}
