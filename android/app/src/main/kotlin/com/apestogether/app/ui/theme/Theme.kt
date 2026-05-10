package com.apestogether.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import android.app.Activity

/**
 * App-level theme. The iOS app is dark-only by design (see
 * `Theme.swift` — it never references a light palette), so we mirror that
 * here: every ColorScheme returns the same dark palette regardless of system
 * setting.
 *
 * If/when we add a light theme, branch on `isSystemInDarkTheme()` here.
 */
private val ApesDarkColors = darkColorScheme(
    primary = PrimaryAccent,
    onPrimary = AppBackground,
    secondary = SecondaryAccent,
    onSecondary = AppBackground,
    background = AppBackground,
    onBackground = TextPrimary,
    surface = CardBackground,
    onSurface = TextPrimary,
    surfaceVariant = CardBorder,
    onSurfaceVariant = TextSecondary,
    error = Losses,
    onError = TextPrimary,
)

@Composable
fun ApesTogetherTheme(
    @Suppress("UNUSED_PARAMETER") darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colorScheme = ApesDarkColors

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = AppBackground.toArgb()
            window.navigationBarColor = AppBackground.toArgb()
            // Light icons on dark status bar.
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = ApesTypography,
        content = content,
    )
}
