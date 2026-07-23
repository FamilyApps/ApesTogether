package com.apestogether.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.compose.rememberNavController
import com.apestogether.app.data.auth.AuthRepository
import com.apestogether.app.data.models.User
import com.apestogether.app.data.onboarding.OnboardingManager
import com.apestogether.app.data.onboarding.OnboardingPreferences
import com.apestogether.app.ui.components.AcquisitionSurveyHost
import com.apestogether.app.ui.navigation.RootNavGraph
import com.apestogether.app.ui.navigation.Screen
import com.apestogether.app.ui.screens.onboarding.AddStocksScreen
import com.apestogether.app.ui.screens.onboarding.EarnNudgeScreen
import com.apestogether.app.ui.screens.onboarding.ReferralPreviewScreen
import com.apestogether.app.ui.screens.onboarding.WelcomeCarouselScreen
import com.apestogether.app.ui.theme.AppBackground
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Top-level composable hosted by [com.apestogether.app.MainActivity]. Owns
 * the NavController and decides which top-level surface to show based on:
 *
 *  - Auth state (signed in / signed out)
 *  - Onboarding completion flag (DataStore-backed)
 *  - Pending referral slug (set when the app is cold-launched via the
 *    `https://apestogether.ai/p/<slug>` intent filter while unauthed)
 *  - Pending "you just subscribed" username (set by Subscribe ViewModels
 *    after a successful Play Billing purchase)
 *
 * State machine — high to low priority:
 *
 *   Authed + post-subscribe nudge active + Add Stocks overlay → AddStocksScreen
 *   Authed + post-subscribe nudge active                      → EarnNudgeScreen
 *   Authed + everything else                                  → RootNavGraph (main)
 *   Unauthed + pending slug                                   → ReferralPreviewScreen
 *   Unauthed + onboarding incomplete                          → WelcomeCarouselScreen
 *   Unauthed + onboarding complete                            → RootNavGraph (login)
 *
 * Mirrors iOS [ContentView]'s state-machine layout.
 */
@Composable
fun RootApp() {
    val rootViewModel: RootViewModel = hiltViewModel()
    // Tri-state — null until the underlying DataStore Flow emits its first
    // value. We render a splash while these are null instead of guessing,
    // because guessing wrong causes either:
    //   - a flash of LoginScreen on cold launch for returning users
    //     (when isAuthed defaults to false), or
    //   - the WelcomeCarousel being skipped entirely on a fresh install
    //     when DataStore takes ~50–150 ms to emit hasCompletedOnboarding.
    val isAuthed: Boolean? by produceState<Boolean?>(initialValue = null, rootViewModel) {
        rootViewModel.isAuthenticated.collect { value = it }
    }
    val hasCompletedOnboarding: Boolean? by produceState<Boolean?>(
        initialValue = null, rootViewModel,
    ) {
        rootViewModel.hasCompletedOnboarding.collect { value = it }
    }
    val pendingSlug by rootViewModel.pendingSlug.collectAsState()
    val subscribedToUsername by rootViewModel.subscribedToUsername.collectAsState()
    val subscribedToSlug by rootViewModel.subscribedToSlug.collectAsState()
    val currentUser by rootViewModel.currentUser.collectAsState()

    val navController = rememberNavController()

    // Local state — these are intentionally not persisted across recomps.
    var carouselDismissed by remember { mutableStateOf(false) }
    var showAddStocksOverlay by remember { mutableStateOf(false) }

    // ── Post-auth bookkeeping ───────────────────────────────────────────
    // On every flip from unauthed → authed:
    //   1. Re-hydrate the cached User object so MyPortfolio renders with
    //      the user's portfolio_slug instead of the empty state.
    //   2. Mark onboarding completed (covers users who jumped straight to
    //      Login from a fresh install without seeing the carousel).
    LaunchedEffect(isAuthed) {
        if (isAuthed == true) {
            rootViewModel.hydrateUser()
            rootViewModel.markOnboardingCompleted()
        }
    }

    // ── Deep-link navigation ────────────────────────────────────────────
    // The pending slug is published by MainActivity (cold start via the App
    // Link Uri or a tapped FCM notification's extras, and warm start via
    // onNewIntent). Keyed on BOTH auth state and the slug so it fires when:
    //   - the user signs in from the ReferralPreview (isAuthed flips), and
    //   - a deep link arrives while the user is already signed in (slug flips).
    // Unauthed + slug is intentionally left to ReferralPreviewScreen below;
    // we only auto-navigate once authenticated. consumePendingSlug() clears the
    // slug so re-running with a null value is a no-op (no double navigation).
    LaunchedEffect(isAuthed, pendingSlug) {
        if (isAuthed == true && !pendingSlug.isNullOrBlank()) {
            delay(300)  // let the NavHost recompose with start = "main"
            val drained = rootViewModel.consumePendingSlug()
            if (!drained.isNullOrBlank()) {
                navController.navigate(Screen.PortfolioDetail.route(drained))
            }
        }
    }

    // ── State-driven render ─────────────────────────────────────────────
    when {
        // Splash — DataStore hasn't returned yet. Solid app-bg avoids any
        // flicker between this and whichever surface we end up rendering.
        isAuthed == null || hasCompletedOnboarding == null -> {
            Box(modifier = Modifier.fillMaxSize().background(AppBackground))
        }

        // Post-subscribe → Add Stocks (chosen "Add Your Stocks" from EarnNudge)
        isAuthed == true && showAddStocksOverlay -> {
            AddStocksScreen(
                onComplete = {
                    showAddStocksOverlay = false
                    rootViewModel.clearSubscribedToUsername()
                },
                showSkip = true,
                showBack = false,
            )
        }

        // Post-subscribe nudge — shown once per successful billing flow.
        isAuthed == true && !subscribedToUsername.isNullOrBlank() -> {
            EarnNudgeScreen(
                subscribedToUsername = subscribedToUsername.orEmpty(),
                onAddStocks = { showAddStocksOverlay = true },
                onSkip = { rootViewModel.clearSubscribedToUsername() },
                // Users who already added their own stocks are creators —
                // skip the "Add Your Stocks" pitch and offer to view the
                // portfolio they just subscribed to instead.
                userHasStocks = (currentUser?.numStocks ?: 0) > 0,
                onViewPortfolio = {
                    val slug = subscribedToSlug
                    // Dismiss the nudge first so the NavHost recomposes, then
                    // reuse the pending-slug deep-link path (LaunchedEffect
                    // above) to navigate once it's live.
                    rootViewModel.clearSubscribedToUsername()
                    if (!slug.isNullOrBlank()) rootViewModel.setPendingSlug(slug)
                },
            )
        }

        // Unauthed + referral slug landing.
        isAuthed == false && !pendingSlug.isNullOrBlank() -> {
            ReferralPreviewScreen(
                slug = pendingSlug.orEmpty(),
                // onSignedIn fires *before* isAuthed flips in the
                // collected state. We rely on the post-auth LaunchedEffect
                // above to drain the slug + navigate.
                onSignedIn = { /* no-op; handled by the effect */ },
                onSkip = { rootViewModel.consumePendingSlug() },
            )
        }

        // First-launch carousel.
        isAuthed == false && hasCompletedOnboarding == false && !carouselDismissed -> {
            WelcomeCarouselScreen(
                onComplete = {
                    carouselDismissed = true
                    rootViewModel.markOnboardingCompleted()
                },
            )
        }

        // Default — everything else routes through the NavHost.
        else -> {
            RootNavGraph(
                navController = navController,
                startAuthenticated = isAuthed == true,
            )
            // One-shot "How did you hear about us?" survey — authed users
            // only, self-gating via DataStore (see AcquisitionSurveyHost).
            if (isAuthed == true) {
                AcquisitionSurveyHost()
            }
        }
    }
}

@HiltViewModel
class RootViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val onboardingPreferences: OnboardingPreferences,
    private val onboardingManager: OnboardingManager,
) : ViewModel() {

    val isAuthenticated = authRepository.isAuthenticated
    val hasCompletedOnboarding = onboardingPreferences.hasCompletedOnboarding
    val pendingSlug: StateFlow<String?> = onboardingManager.pendingSlug
    val subscribedToUsername: StateFlow<String?> = onboardingManager.subscribedToUsername
    val subscribedToSlug: StateFlow<String?> = onboardingManager.subscribedToSlug
    val currentUser: StateFlow<User?> = authRepository.currentUser

    fun hydrateUser() {
        viewModelScope.launch { authRepository.refreshUserData() }
    }

    fun markOnboardingCompleted() {
        viewModelScope.launch { onboardingPreferences.markCompleted() }
    }

    fun setPendingSlug(slug: String?) = onboardingManager.setPendingSlug(slug)

    fun consumePendingSlug(): String? = onboardingManager.consumePendingSlug()

    fun clearSubscribedToUsername() = onboardingManager.clearSubscribedToUsername()
}
