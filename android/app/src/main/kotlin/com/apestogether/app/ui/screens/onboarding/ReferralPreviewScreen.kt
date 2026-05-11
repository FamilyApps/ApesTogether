package com.apestogether.app.ui.screens.onboarding

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.auth.AuthRepository
import com.apestogether.app.data.models.PortfolioResponse
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.HeroBackgroundEnd
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Pre-auth landing for users who tap a portfolio share link
 * (`https://apestogether.ai/p/<slug>`) without being signed in.
 *
 * Renders a stripped-down preview of the referred portfolio (avatar pip,
 * display name, subscriber count, value-prop blurb) and a "Continue with
 * Google" CTA. After successful sign-in [onSignedIn] is invoked — RootApp
 * then routes the user straight to the full PortfolioDetailScreen for that
 * slug, where they can subscribe.
 *
 * Direct port of iOS [ReferralPreviewView]; the iOS Sign-In-with-Apple
 * button is replaced with the same Google flow LoginScreen uses since
 * Google Sign-In is the only auth provider on Android.
 */
@Composable
fun ReferralPreviewScreen(
    slug: String,
    onSignedIn: () -> Unit,
    onSkip: () -> Unit,
) {
    val viewModel: ReferralPreviewViewModel = hiltViewModel()
    val state by viewModel.state.collectAsState()
    val isAuthLoading by viewModel.isAuthLoading.collectAsState()
    val authError by viewModel.authError.collectAsState()
    val signedIn by viewModel.signedIn.collectAsState()
    val context = LocalContext.current

    LaunchedEffect(slug) { viewModel.load(slug) }
    LaunchedEffect(signedIn) { if (signedIn) onSignedIn() }

    val heroGradient = Brush.verticalGradient(
        colors = listOf(AppBackground, HeroBackgroundEnd),
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(heroGradient),
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Top bar — "Explore app" lets the user back out and see the
            // standard login screen instead.
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp, vertical = 16.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(onClick = onSkip) {
                    Text(
                        "Explore app",
                        color = TextSecondary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }

            Spacer(Modifier.weight(1f))

            // Body
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp),
                contentAlignment = Alignment.Center,
            ) {
                when (val s = state) {
                    PreviewState.Loading -> {
                        CircularProgressIndicator(color = PrimaryAccent)
                    }
                    is PreviewState.Error -> ReferralErrorBlock(
                        message = s.message,
                        onRetry = { viewModel.load(slug) },
                    )
                    is PreviewState.Loaded -> ReferralPortfolioPreview(s.portfolio)
                }
            }

            Spacer(Modifier.weight(1f))

            // CTA section
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 50.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    "Sign in to start your free trial",
                    color = TextSecondary,
                    fontSize = 13.sp,
                )

                if (isAuthLoading) {
                    CircularProgressIndicator(color = PrimaryAccent)
                } else {
                    Button(
                        onClick = { viewModel.signInWithGoogle(context) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 40.dp)
                            .height(54.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                    ) {
                        Text(
                            "Continue with Google",
                            color = AppBackground,
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }

                if (!authError.isNullOrBlank()) {
                    Text(
                        text = authError.orEmpty(),
                        color = Losses,
                        fontSize = 12.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(horizontal = 40.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun ReferralPortfolioPreview(portfolio: PortfolioResponse) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        // Avatar — single-letter initial inside a soft accent disc. Same
        // visual treatment as iOS even though we removed the equivalent
        // pip from PortfolioHeroCard for vertical-space reasons; the
        // referral landing has no chart fighting for room.
        Box(
            modifier = Modifier
                .size(80.dp)
                .clip(CircleShape)
                .background(PrimaryAccent.copy(alpha = 0.15f)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = portfolio.owner.publicName.take(1).uppercase(),
                color = PrimaryAccent,
                fontSize = 32.sp,
                fontWeight = FontWeight.Bold,
            )
        }

        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                portfolio.owner.publicName,
                color = TextPrimary,
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
            )

            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.People,
                    contentDescription = null,
                    tint = TextSecondary,
                    modifier = Modifier.size(14.dp),
                )
                val count = portfolio.subscriberCount
                Text(
                    "$count subscriber" + if (count != 1) "s" else "",
                    color = TextSecondary,
                    fontSize = 14.sp,
                )
            }
        }

        // Value-prop card
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(CardBackground)
                .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(
                imageVector = Icons.Default.Notifications,
                contentDescription = null,
                tint = PrimaryAccent,
                modifier = Modifier.size(36.dp),
            )
            Text(
                "Get real-time trade alerts",
                color = TextPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "Know the moment ${portfolio.owner.publicName} buys or sells. Never miss a move.",
                color = TextSecondary,
                fontSize = 13.sp,
                textAlign = TextAlign.Center,
                lineHeight = 18.sp,
            )
        }
    }
}

@Composable
private fun ReferralErrorBlock(message: String, onRetry: () -> Unit) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            "Couldn't Load Portfolio",
            color = TextPrimary,
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(
            message,
            color = TextMuted,
            fontSize = 13.sp,
            textAlign = TextAlign.Center,
        )
        OutlinedButton(
            onClick = onRetry,
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = PrimaryAccent),
        ) {
            Icon(
                imageVector = Icons.Default.Refresh,
                contentDescription = null,
                tint = PrimaryAccent,
                modifier = Modifier.size(16.dp),
            )
            Spacer(Modifier.width(6.dp))
            Text("Retry", color = PrimaryAccent, fontWeight = FontWeight.SemiBold)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// State + ViewModel
// ─────────────────────────────────────────────────────────────────────────

sealed interface PreviewState {
    data object Loading : PreviewState
    data class Loaded(val portfolio: PortfolioResponse) : PreviewState
    data class Error(val message: String) : PreviewState
}

@HiltViewModel
class ReferralPreviewViewModel @Inject constructor(
    private val apiService: ApiService,
    private val authRepository: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<PreviewState>(PreviewState.Loading)
    val state: StateFlow<PreviewState> = _state.asStateFlow()

    val isAuthLoading: StateFlow<Boolean> = authRepository.isLoading
    val authError: StateFlow<String?> = authRepository.error

    private val _signedIn = MutableStateFlow(false)
    val signedIn: StateFlow<Boolean> = _signedIn.asStateFlow()

    fun load(slug: String) {
        viewModelScope.launch {
            _state.value = PreviewState.Loading
            runCatching { apiService.getPortfolio(slug) }
                .onSuccess { _state.value = PreviewState.Loaded(it) }
                .onFailure {
                    _state.value = PreviewState.Error(
                        "This portfolio couldn't be loaded right now."
                    )
                }
        }
    }

    fun signInWithGoogle(context: android.content.Context) {
        viewModelScope.launch {
            val result = authRepository.signInWithGoogle(context)
            if (result.isSuccess) _signedIn.value = true
        }
    }
}
