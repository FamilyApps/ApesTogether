package com.apestogether.app.ui.screens.main

import com.apestogether.app.R
import com.apestogether.app.ui.screens.leaderboard.LeaderboardScreen
import com.apestogether.app.ui.screens.myportfolio.MyPortfolioScreen
import com.apestogether.app.ui.screens.subscriptions.SubscriptionsScreen
import com.apestogether.app.ui.screens.topinfluencers.TopInfluencersScreen
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary

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
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainTabsScreen(
    onOpenPortfolio: (String) -> Unit,
    onOpenSettings: () -> Unit,
    onOpenAddStocks: () -> Unit,
    onOpenW9: () -> Unit,
    onSignedOut: () -> Unit,
) {
    var selectedTab by remember { mutableStateOf(0) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Image(
                            painter = painterResource(id = R.drawable.nav_logo),
                            contentDescription = null,
                            modifier = Modifier
                                .size(28.dp)
                                .clip(CircleShape),
                            contentScale = ContentScale.Fit,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = "ApesTogether",
                            color = TextPrimary,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                        )
                    }
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
                onOpenAddStocks = onOpenAddStocks,
            )
            3 -> SubscriptionsScreen(
                modifier = Modifier.padding(padding),
                onOpenPortfolio = onOpenPortfolio,
                onOpenW9 = onOpenW9,
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
