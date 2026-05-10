package ai.apestogether.ui.screens.main

import ai.apestogether.ui.screens.leaderboard.LeaderboardScreen
import ai.apestogether.ui.screens.myportfolio.MyPortfolioScreen
import ai.apestogether.ui.screens.subscriptions.SubscriptionsScreen
import ai.apestogether.ui.screens.topinfluencers.TopInfluencersScreen
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import ai.apestogether.ui.theme.AppBackground
import ai.apestogether.ui.theme.PrimaryAccent
import ai.apestogether.ui.theme.TextSecondary

/**
 * Bottom-tab host. Mirrors iOS [MainTabView] in `ContentView.swift`.
 *
 * Tabs (in order, matching iOS for visual parity):
 *   0. Leaderboard        — trophy icon
 *   1. Top Creators       — people icon
 *   2. My Portfolio       — pie-chart icon
 *   3. Subscriptions      — bell icon
 *
 * Top bar shows app title + Settings cog (matching iOS [AppHeaderRow]).
 */
@Composable
fun MainTabsScreen(
    onOpenPortfolio: (String) -> Unit,
    onOpenSettings: () -> Unit,
    onSignedOut: () -> Unit,
) {
    var selectedTab by remember { mutableStateOf(0) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        "Apes Together",
                        style = MaterialTheme.typography.titleLarge,
                        color = MaterialTheme.colorScheme.onBackground,
                    )
                },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(
                            imageVector = Icons.Default.Settings,
                            contentDescription = "Settings",
                            tint = TextSecondary,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = AppBackground),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = AppBackground) {
                Tabs.entries.forEachIndexed { index, tab ->
                    NavigationBarItem(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = PrimaryAccent,
                            selectedTextColor = PrimaryAccent,
                            unselectedIconColor = TextSecondary,
                            unselectedTextColor = TextSecondary,
                            indicatorColor = AppBackground,
                        ),
                    )
                }
            }
        },
    ) { padding ->
        when (selectedTab) {
            0 -> LeaderboardScreen(
                modifier = Modifier.padding(padding),
                onOpenPortfolio = onOpenPortfolio,
            )
            1 -> TopInfluencersScreen(
                modifier = Modifier.padding(padding),
                onOpenPortfolio = onOpenPortfolio,
            )
            2 -> MyPortfolioScreen(
                modifier = Modifier.padding(padding),
            )
            3 -> SubscriptionsScreen(
                modifier = Modifier.padding(padding),
                onOpenPortfolio = onOpenPortfolio,
            )
        }
    }
}

private enum class Tabs(val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Leaderboard("Leaderboard", Icons.Default.EmojiEvents),
    TopCreators("Top Creators", Icons.Default.People),
    Portfolio("Portfolio", Icons.Default.PieChart),
    Subscriptions("Subscriptions", Icons.Default.Notifications),
}
