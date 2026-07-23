package com.apestogether.app.util

import android.app.Activity
import android.content.Context
import android.util.Log
import com.google.android.play.core.review.ReviewManagerFactory

/**
 * Play In-App Review prompt, mirroring iOS `TradeSheetView.promptReviewIfEligible`:
 * count successful trades and request the review flow exactly once, after the
 * 3rd (user is engaged and just accomplished something). The in-app prompt at a
 * "happy moment" is our ONLY legitimate ratings lever (MARKETING_PLAN.md — paid
 * or incentivized reviews are a developer-account-termination offense).
 *
 * Play itself decides whether the dialog actually appears (quota-managed; the
 * API is a silent no-op when throttled), so this must never gate app flow and
 * gets no success/failure UI of its own.
 */
object ReviewPrompter {
    private const val TAG = "ReviewPrompter"
    private const val PREFS = "review_prompter"
    private const val KEY_TRADE_COUNT = "successful_trade_count"

    /** Same threshold as iOS (`successfulTradeCount == 3`). */
    private const val PROMPT_AT_TRADE = 3

    fun onSuccessfulTrade(activity: Activity) {
        val prefs = activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val count = prefs.getInt(KEY_TRADE_COUNT, 0) + 1
        prefs.edit().putInt(KEY_TRADE_COUNT, count).apply()
        if (count != PROMPT_AT_TRADE) return

        val manager = ReviewManagerFactory.create(activity)
        manager.requestReviewFlow().addOnCompleteListener { task ->
            if (task.isSuccessful) {
                // Fire-and-forget: Play may or may not show the dialog.
                manager.launchReviewFlow(activity, task.result)
            } else {
                Log.d(TAG, "requestReviewFlow failed: ${task.exception?.message}")
            }
        }
    }
}
