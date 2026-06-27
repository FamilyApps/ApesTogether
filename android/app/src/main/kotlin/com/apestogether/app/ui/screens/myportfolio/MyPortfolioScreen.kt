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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.auth.AuthRepository
import com.apestogether.app.ui.screens.portfolio.PortfolioDetailScreen
import com.apestogether.app.ui.share.ShareCard
import com.apestogether.app.ui.share.ShareCardData
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * "My Portfolio" tab. Direct port of iOS [MyPortfolioView]. The bulk of the
 * UI is just [PortfolioDetailScreen] for the current user's slug, with two
 * additions on top:
 *
 *  - "Share Performance" button below the chart: renders a branded
 *    performance card to a PNG via [ShareCard] and opens the system share
 *    sheet (image + follow link), matching iOS `ShareCardGenerator`. Falls
 *    back to a plain link share if the data fetch fails.
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

            ShareMyPerformanceButton(slug = slug, viewModel = viewModel)

            // Inline "Quick Poll" card (mirrors iOS MyPortfolioView). Renders
            // nothing when there's no active poll.
            FeaturePoll()
        }
    }
}

@Composable
private fun ShareMyPerformanceButton(slug: String, viewModel: MyPortfolioViewModel) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var sharing by remember { mutableStateOf(false) }
    Button(
        onClick = {
            if (sharing) return@Button
            sharing = true
            scope.launch {
                val data = viewModel.buildShareData(slug)
                if (data != null) {
                    // Renders the branded performance card to a PNG and opens
                    // the share sheet (image + follow link). Mirrors iOS.
                    runCatching { ShareCard.sharePortfolioPerformance(context, data) }
                } else {
                    // Fallback to a plain link share if the data fetch failed.
                    val url = "https://apestogether.ai/p/$slug"
                    val intent = Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(
                            Intent.EXTRA_TEXT,
                            "Check out my portfolio on ApesTogether! 🦍📈\n$url",
                        )
                    }
                    runCatching {
                        context.startActivity(Intent.createChooser(intent, "Share my portfolio"))
                    }
                }
                sharing = false
            }
        },
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .height(48.dp),
        shape = RoundedCornerShape(10.dp),
        colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
    ) {
        if (sharing) {
            CircularProgressIndicator(
                color = Color.White,
                strokeWidth = 2.dp,
                modifier = Modifier.size(16.dp),
            )
            Spacer(Modifier.width(8.dp))
            Text("Preparing…", color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        } else {
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
    private val apiService: ApiService,
) : ViewModel() {
    val currentUser = authRepository.currentUser

    /**
     * Fetch the data needed to render the portfolio-performance share card.
     * Returns null if the portfolio fetch fails (the caller then falls back to
     * a plain link share).
     */
    suspend fun buildShareData(slug: String, period: String = "1W"): ShareCardData? {
        val portfolio = runCatching { apiService.getPortfolio(slug) }.getOrNull() ?: return null
        val chart = runCatching { apiService.getPortfolioChart(slug, period) }.getOrNull()
        return ShareCardData(
            username = portfolio.owner.publicName,
            portfolioReturn = chart?.portfolioReturn ?: 0.0,
            sp500Return = chart?.sp500Return ?: 0.0,
            chartValues = chart?.chartData?.mapNotNull { it.portfolio } ?: emptyList(),
            holdingsCount = portfolio.holdings?.size ?: 0,
            subscriberCount = portfolio.subscriberCount,
            period = period,
            slug = slug,
        )
    }
}
