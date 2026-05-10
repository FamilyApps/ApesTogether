package com.apestogether.app.ui.screens.leaderboard

import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.models.LeaderboardEntry
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Gains
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextSecondary
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Leaderboard tab. Equivalent to iOS [LeaderboardView].
 *
 * v0 scope: pull `/leaderboard?period=1W` and render a tappable list of
 * portfolios with rank, public_name, return %, alpha vs S&P, subscriber
 * count, and trade frequency. Tapping a row opens [PortfolioDetailScreen].
 *
 * Future iterations will add the period/category/industry/frequency filter
 * pills, sparkline previews, and the share-card overlay.
 */
@Composable
fun LeaderboardScreen(
    modifier: Modifier = Modifier,
    onOpenPortfolio: (String) -> Unit,
) {
    val viewModel: LeaderboardViewModel = hiltViewModel()
    val state by viewModel.state.collectAsState()

    LaunchedEffect(Unit) { viewModel.refresh() }

    Box(modifier = modifier.fillMaxSize()) {
        when (val s = state) {
            is LeaderboardState.Loading ->
                CircularProgressIndicator(
                    color = PrimaryAccent,
                    modifier = Modifier.align(Alignment.Center),
                )

            is LeaderboardState.Error ->
                Text(
                    text = s.message,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )

            is LeaderboardState.Loaded ->
                LazyColumn(
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(s.entries, key = { it.user.id }) { entry ->
                        LeaderboardRow(entry = entry, onClick = {
                            entry.user.portfolioSlug
                                ?.takeIf { it.isNotBlank() }
                                ?.let(onOpenPortfolio)
                        })
                    }
                }
        }
    }
}

@Composable
private fun LeaderboardRow(entry: LeaderboardEntry, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = CardBackground),
        border = androidx.compose.foundation.BorderStroke(1.dp, CardBorder),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .clickable(onClick = onClick)
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "#${entry.rank}",
                style = MaterialTheme.typography.titleMedium,
                color = PrimaryAccent,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.width(16.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = entry.user.publicName,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = "${entry.subscriberCount} subscribers · $${entry.subscriptionPrice.toInt()}/mo",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary,
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(horizontalAlignment = Alignment.End) {
                val isUp = entry.returnPercent >= 0
                Text(
                    text = (if (isUp) "+" else "") + "%.2f%%".format(entry.returnPercent),
                    style = MaterialTheme.typography.titleMedium,
                    color = if (isUp) Gains else Losses,
                    fontWeight = FontWeight.SemiBold,
                )
                entry.alphaVsSp500?.let { alpha ->
                    Text(
                        text = (if (alpha >= 0) "α +" else "α ") + "%.1f%%".format(alpha),
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary,
                    )
                }
            }
        }
    }
}

sealed interface LeaderboardState {
    data object Loading : LeaderboardState
    data class Loaded(val entries: List<LeaderboardEntry>) : LeaderboardState
    data class Error(val message: String) : LeaderboardState
}

@HiltViewModel
class LeaderboardViewModel @Inject constructor(
    private val apiService: ApiService,
) : ViewModel() {
    private val _state = MutableStateFlow<LeaderboardState>(LeaderboardState.Loading)
    val state: StateFlow<LeaderboardState> = _state.asStateFlow()

    fun refresh(period: String = "1W", category: String = "all") {
        viewModelScope.launch {
            _state.value = LeaderboardState.Loading
            runCatching { apiService.getLeaderboard(period = period, category = category) }
                .onSuccess { _state.value = LeaderboardState.Loaded(it.entries) }
                .onFailure { _state.value = LeaderboardState.Error(it.message ?: "Failed to load leaderboard") }
        }
    }
}
