package com.apestogether.app.ui.navigation

import com.apestogether.app.ui.screens.login.LoginScreen
import com.apestogether.app.ui.screens.main.MainTabsScreen
import com.apestogether.app.ui.screens.portfolio.PortfolioDetailScreen
import com.apestogether.app.ui.screens.settings.SettingsScreen
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
 *                  MyPortfolio / Subscriptions). Settings + PortfolioDetail
 *                  are pushed on top of any tab.
 *
 * Deep-link: `https://apestogether.ai/p/<slug>` opens
 * [Screen.PortfolioDetail]. The intent filter is declared in
 * AndroidManifest.xml; we read the URI in [RootApp] and consume it once on
 * first composition.
 */
@Composable
fun RootNavGraph(
    navController: NavHostController,
    startAuthenticated: Boolean,
    initialDeepLinkUri: Uri? = null,
) {
    val startRoute = if (startAuthenticated) "main" else Screen.Login.route

    LaunchedEffect(initialDeepLinkUri, startAuthenticated) {
        val slug = initialDeepLinkUri?.let { extractSlugFromDeepLink(it) }
        if (!slug.isNullOrBlank() && startAuthenticated) {
            navController.navigate(Screen.PortfolioDetail.route(slug))
        }
    }

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
    }
}

/** Pulls the portfolio slug out of `https://apestogether.ai/p/<slug>`. */
private fun extractSlugFromDeepLink(uri: Uri): String? {
    val segments = uri.pathSegments
    val pIdx = segments.indexOf("p")
    return if (pIdx >= 0 && pIdx + 1 < segments.size) segments[pIdx + 1] else null
}
