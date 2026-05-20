package com.apestogether.app.data.leaderboard

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.leaderboardDataStore by preferencesDataStore(name = "leaderboard")

/**
 * Persistent leaderboard filter prefs. Currently only [hideFractional] —
 * matches iOS @AppStorage("leaderboard_hide_fractional"). Other filters
 * (sector / category / frequency / hideLoQ) intentionally don't persist
 * across launches; they reset to defaults each session, same as iOS.
 *
 * Pattern mirrors [com.apestogether.app.data.onboarding.OnboardingPreferences].
 */
@Singleton
class LeaderboardPreferences @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val hideFractionalKey = booleanPreferencesKey("hide_fractional")

    /** Reactive flag — emits whenever the user toggles. */
    val hideFractional: Flow<Boolean> =
        context.leaderboardDataStore.data.map { it[hideFractionalKey] == true }

    suspend fun setHideFractional(value: Boolean) {
        context.leaderboardDataStore.edit { it[hideFractionalKey] = value }
    }

    suspend fun hideFractionalNow(): Boolean = hideFractional.first()
}
