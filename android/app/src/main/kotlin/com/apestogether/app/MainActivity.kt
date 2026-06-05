package com.apestogether.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import com.apestogether.app.data.onboarding.OnboardingManager
import com.apestogether.app.ui.RootApp
import com.apestogether.app.ui.navigation.extractSlugFromDeepLink
import com.apestogether.app.ui.theme.ApesTogetherTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Hosts the entire Compose UI tree and handles cold-start permission asks.
 *
 * Mirrors the iOS [SceneDelegate]/`@main App` pattern: the Activity owns the
 * top-level `RootApp` composable which decides whether to show the login flow
 * or the main tabbed UI based on auth state.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var onboardingManager: OnboardingManager

    private val requestNotificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* result is observed in repo */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        askForNotificationPermissionIfNeeded()
        ingestDeepLink(intent)

        setContent {
            ApesTogetherTheme {
                Surface(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(androidx.compose.material3.MaterialTheme.colorScheme.background),
                ) {
                    RootApp()
                }
            }
        }
    }

    /**
     * Warm-start entry point. Because the Activity is `singleTask`, a deep link
     * that arrives while the app is already in memory (App Link tap, or a tapped
     * FCM trade-alert notification) is delivered here instead of `onCreate`.
     * Without this override those links would be silently dropped.
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        ingestDeepLink(intent)
    }

    /**
     * Resolve a portfolio slug from an incoming intent and hand it to the
     * [OnboardingManager], which `RootApp` observes to drive navigation.
     *
     * Two delivery shapes are handled:
     *  - App Links + our own foreground notification PendingIntent carry the
     *    slug as the intent `data` Uri (`https://apestogether.ai/p/<slug>`).
     *  - A tapped FCM notification rendered by the system tray while the app is
     *    backgrounded delivers the push `data` map as intent extras, so the slug
     *    arrives as the `portfolio_slug` string extra (no Uri).
     */
    private fun ingestDeepLink(intent: Intent?) {
        if (intent == null) return
        val slug = intent.data?.let { extractSlugFromDeepLink(it) }
            ?: intent.getStringExtra(EXTRA_PORTFOLIO_SLUG)
        if (!slug.isNullOrBlank()) {
            onboardingManager.setPendingSlug(slug)
        }
    }

    /**
     * Android 13+ requires runtime permission for displaying notifications.
     * Older devices grant this implicitly.
     */
    private fun askForNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            requestNotificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    companion object {
        /**
         * Key under which the backend push `data` map carries the portfolio
         * slug. Must match `push_notification_service.send_trade_notification`
         * (`data['portfolio_slug']`).
         */
        private const val EXTRA_PORTFOLIO_SLUG = "portfolio_slug"
    }
}
