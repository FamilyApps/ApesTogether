package ai.apestogether

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import dagger.hilt.android.HiltAndroidApp

/**
 * Application class — Hilt entry point and notification-channel setup.
 *
 * Mirrors iOS [ApesTogetherApp.swift] configuration:
 *  - Configures Firebase (auto-init via google-services.json plugin).
 *  - Creates the trade-alerts notification channel so FCM messages can render.
 *  - Hosts the dependency-injection graph (Hilt).
 */
@HiltAndroidApp
class ApesTogetherApplication : Application() {

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java) ?: return

        val tradeAlerts = NotificationChannel(
            CHANNEL_TRADE_ALERTS,
            "Trade alerts",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Alerts when a portfolio you follow makes a trade."
            enableLights(true)
            enableVibration(true)
        }
        nm.createNotificationChannel(tradeAlerts)
    }

    companion object {
        const val CHANNEL_TRADE_ALERTS = "trade_alerts"
    }
}
