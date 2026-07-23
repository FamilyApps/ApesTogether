package com.apestogether.app.data.onboarding

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

private val Context.onboardingDataStore by preferencesDataStore(name = "onboarding")

/**
 * Persistent flag: has the user dismissed the welcome carousel at least once?
 *
 * Mirrors `DeepLinkManager.hasCompletedOnboarding` on iOS (which is backed
 * by `UserDefaults`). The flag flips to true the first time the user either
 * (a) finishes the carousel via "Get Started", (b) hits "Skip", or
 * (c) signs in successfully (covers the case where they jumped straight
 * to login from a referral link).
 */
@Singleton
class OnboardingPreferences @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val completedKey = booleanPreferencesKey("has_completed_onboarding")
    private val acquisitionSurveyKey = booleanPreferencesKey("acquisition_survey_done")

    /** Reactive flag driving the welcome-carousel routing decision. */
    val hasCompletedOnboarding: Flow<Boolean> =
        context.onboardingDataStore.data.map { it[completedKey] == true }

    suspend fun markCompleted() {
        context.onboardingDataStore.edit { it[completedKey] = true }
    }

    suspend fun isCompletedNow(): Boolean = hasCompletedOnboarding.first()

    /**
     * Has the one-shot "How did you hear about us?" survey been answered or
     * dismissed on this install? Backend enforces first-write-wins, so a
     * reinstall re-asking is harmless (the original answer is kept).
     */
    val acquisitionSurveyDone: Flow<Boolean> =
        context.onboardingDataStore.data.map { it[acquisitionSurveyKey] == true }

    suspend fun markAcquisitionSurveyDone() {
        context.onboardingDataStore.edit { it[acquisitionSurveyKey] = true }
    }
}
