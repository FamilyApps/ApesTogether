package com.apestogether.app.ui.screens.myportfolio

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import com.apestogether.app.data.auth.AuthRepository
import com.apestogether.app.ui.screens.portfolio.PortfolioDetailScreen
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

/**
 * "My Portfolio" tab. Direct port of iOS [MyPortfolioView]. The bulk of the
 * UI is just [PortfolioDetailScreen] for the current user's slug, with two
 * additions on top:
 *
 *  - "Share Performance" button below the chart (uses Android's standard
 *    [Intent.ACTION_SEND] chooser; iOS uses ShareCardGenerator to render an
 *    image, which is deferred to v1.1).
 *  - Empty state for users without a `portfolio_slug` yet, telling them to
 *    add stocks. The "Add Your Stocks" CTA navigates to [AddStocksScreen]
 *    via the [onOpenAddStocks] callback supplied by [MainTabsScreen].
 *
 * The header (NavLogo + Settings) is owned by [MainTabsScreen] above us, so
 * we render the embedded variant of the detail screen via
 * `showOwnHeader = false`.
 */
@Composable
fun MyPortfolioScreen(
    modifier: Modifier = Modifier,
    onOpenAddStocks: () -> Unit = {},
) {
    val viewModel: MyPortfolioViewModel = hiltViewModel()
    val user by viewModel.currentUser.collectAsState()

    val slug = user?.portfolioSlug

    if (slug.isNullOrBlank()) {
        EmptyMyPortfolio(modifier = modifier, onAddStocks = onOpenAddStocks)
    } else {
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(AppBackground),
        ) {
            // Embed the detail screen body — no extra top bar, since
            // MainTabsScreen owns ours.
            Box(modifier = Modifier.weight(1f)) {
                PortfolioDetailScreen(
                    slug = slug,
                    onBack = { /* no-op when embedded */ },
                    showOwnHeader = false,
                )
            }

            ShareMyPerformanceButton(slug = slug)
        }
    }
}

@Composable
private fun ShareMyPerformanceButton(slug: String) {
    val context = LocalContext.current
    Button(
        onClick = {
            val url = "https://apestogether.ai/p/$slug"
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(
                    Intent.EXTRA_TEXT,
                    "Check out my portfolio on ApesTogether! 🦍📈\n$url",
                )
            }
            ContextCompat.startActivity(
                context,
                Intent.createChooser(intent, "Share my portfolio"),
                null,
            )
        },
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .height(48.dp),
        shape = RoundedCornerShape(10.dp),
        colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
    ) {
        Icon(Icons.Default.Share, null, tint = Color.White, modifier = Modifier.size(14.dp))
        Spacer(Modifier.width(6.dp))
        Text(
            "Share Performance",
            color = Color.White,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun EmptyMyPortfolio(
    modifier: Modifier = Modifier,
    onAddStocks: () -> Unit,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(AppBackground)
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Icon(
                imageVector = Icons.Default.AttachMoney,
                contentDescription = null,
                tint = PrimaryAccent.copy(alpha = 0.6f),
                modifier = Modifier.size(56.dp),
            )
            Text("Start Earning", color = TextPrimary, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Text(
                text = "Add your stocks to join the leaderboard and earn from every subscriber who follows your trades.",
                color = TextSecondary,
                fontSize = 14.sp,
            )
            Button(
                onClick = onAddStocks,
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                shape = RoundedCornerShape(12.dp),
            ) {
                Text("Add Your Stocks", color = Color.White, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@HiltViewModel
class MyPortfolioViewModel @Inject constructor(
    authRepository: AuthRepository,
) : ViewModel() {
    val currentUser = authRepository.currentUser
}
