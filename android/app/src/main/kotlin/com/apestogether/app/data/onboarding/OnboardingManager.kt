package com.apestogether.app.data.onboarding

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * In-memory cross-screen messaging hub for the onboarding flow. Counterpart
 * to iOS [DeepLinkManager] + the `NotificationCenter` events (`.openPortfolio`
 * / `.didSubscribe`) used by `ContentView` to drive the post-subscribe nudge.
 *
 * Intentionally **not** persisted — every field here is reset on app restart:
 *  - `pendingSlug` is set on cold start by [com.apestogether.app.MainActivity]
 *    when launched via the `https://apestogether.ai/p/<slug>` intent filter
 *    *and* the user is currently signed out. After consumption it's cleared
 *    so a subsequent sign-out doesn't re-trigger the referral preview.
 *  - `subscribedToUsername` is set by [PortfolioDetailViewModel] /
 *    [LeaderboardViewModel] right after a Play-Billing subscribe completes
 *    successfully. RootApp watches this flag and renders the EarnNudge view
 *    when it transitions from null → non-null.
 */
@Singleton
class OnboardingManager @Inject constructor() {

    private val _pendingSlug = MutableStateFlow<String?>(null)
    val pendingSlug: StateFlow<String?> = _pendingSlug.asStateFlow()

    private val _subscribedToUsername = MutableStateFlow<String?>(null)
    val subscribedToUsername: StateFlow<String?> = _subscribedToUsername.asStateFlow()

    // Portfolio slug of the just-subscribed creator, captured alongside the
    // username so the EarnNudge can offer a "View Portfolio" button (for users
    // who already have their own stocks and don't need the Add-Stocks pitch).
    private val _subscribedToSlug = MutableStateFlow<String?>(null)
    val subscribedToSlug: StateFlow<String?> = _subscribedToSlug.asStateFlow()

    /** Called from MainActivity when the cold-start intent carries a slug. */
    fun setPendingSlug(slug: String?) {
        _pendingSlug.value = slug?.takeIf { it.isNotBlank() }
    }

    /** Called once the slug has been routed to the referral preview screen. */
    fun consumePendingSlug(): String? {
        val slug = _pendingSlug.value
        _pendingSlug.value = null
        return slug
    }

    /** Called by Subscribe ViewModels on success. Triggers EarnNudge. */
    fun notifyDidSubscribe(username: String, slug: String? = null) {
        _subscribedToUsername.value = username
        _subscribedToSlug.value = slug?.takeIf { it.isNotBlank() }
    }

    /** Called when the user dismisses (or completes) the EarnNudge flow. */
    fun clearSubscribedToUsername() {
        _subscribedToUsername.value = null
        _subscribedToSlug.value = null
    }
}
