package ai.apestogether.ui.screens.portfolio

import ai.apestogether.ui.screens.common.PlaceholderScreen
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.padding
import ai.apestogether.ui.theme.AppBackground
import ai.apestogether.ui.theme.TextSecondary

/**
 * Portfolio detail — equivalent to iOS [PortfolioDetailView] (47KB; the
 * largest view in the iOS app). Shows owner header, performance chart,
 * holdings, recent trades, badges, and the subscribe CTA when not the owner.
 *
 * TODO: Full port. For now, displays the slug being requested so deep-link
 * routing can be verified end-to-end.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PortfolioDetailScreen(
    slug: String,
    onBack: () -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        slug,
                        style = MaterialTheme.typography.titleLarge,
                        color = MaterialTheme.colorScheme.onBackground,
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = TextSecondary,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = AppBackground),
            )
        },
    ) { padding ->
        PlaceholderScreen(
            modifier = Modifier.padding(padding),
            title = "Portfolio: $slug",
            body = "Holdings, trades, chart, and subscribe CTA. iOS reference: PortfolioDetailView.swift",
        )
    }
}
