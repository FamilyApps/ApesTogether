package com.apestogether.app

import android.Manifest
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
import com.apestogether.app.ui.RootApp
import com.apestogether.app.ui.theme.ApesTogetherTheme
import dagger.hilt.android.AndroidEntryPoint

/**
 * Hosts the entire Compose UI tree and handles cold-start permission asks.
 *
 * Mirrors the iOS [SceneDelegate]/`@main App` pattern: the Activity owns the
 * top-level `RootApp` composable which decides whether to show the login flow
 * or the main tabbed UI based on auth state.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val requestNotificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* result is observed in repo */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        askForNotificationPermissionIfNeeded()

        setContent {
            ApesTogetherTheme {
                Surface(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(androidx.compose.material3.MaterialTheme.colorScheme.background),
                ) {
                    RootApp(
                        initialDeepLinkUri = intent?.data,
                    )
                }
            }
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
}
