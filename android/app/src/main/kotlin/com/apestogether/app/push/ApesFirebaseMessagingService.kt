package com.apestogether.app.push

import com.apestogether.app.ApesTogetherApplication.Companion.CHANNEL_TRADE_ALERTS
import com.apestogether.app.MainActivity
import com.apestogether.app.R
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.api.DeviceRegistrationRequest
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Receives FCM messages and renders local notifications.
 *
 * Mirrors iOS [AppDelegate.messaging(_:didReceiveRegistrationToken:)] +
 * [userNotificationCenter(_:didReceive:withCompletionHandler:)].
 *
 * Backend (`push_notification_service.py:send_trade_notification`) sends a
 * data-payload-only message with these keys:
 *   type           = "trade_alert"
 *   ticker         = "AAPL"
 *   action         = "BUY" | "SELL"
 *   quantity       = "10"
 *   price          = "182.50"
 *   portfolio_slug = "the-grok-portfolio"     (optional, drives deep-link)
 *
 * The notification.title/body fields ARE present too (set server-side), so
 * we display them when available and fall back to constructing a string from
 * the data fields.
 */
@AndroidEntryPoint
class ApesFirebaseMessagingService : FirebaseMessagingService() {

    @Inject lateinit var apiService: ApiService

    private val scope = CoroutineScope(Dispatchers.IO)

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        // Fire-and-forget. If the user is logged in, the AuthInterceptor will
        // attach the bearer; if not, the call returns 401 and we'll re-register
        // after next sign-in (handled in AuthRepository).
        scope.launch {
            runCatching {
                apiService.registerDevice(
                    DeviceRegistrationRequest(
                        token = token,
                        platform = "android",
                        deviceId = android.os.Build.MODEL,
                        appVersion = packageInfoVersionName(),
                        osVersion = "Android ${android.os.Build.VERSION.RELEASE}",
                    ),
                )
            }
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)

        val title = message.notification?.title ?: message.data["title"] ?: "Apes Together"
        val body = message.notification?.body ?: buildBodyFromData(message.data)
        val deepLink = message.data["portfolio_slug"]?.let { "https://apestogether.ai/p/$it" }

        showNotification(title, body, deepLink)
    }

    private fun buildBodyFromData(data: Map<String, String>): String {
        val action = data["action"]?.uppercase() ?: ""
        val ticker = data["ticker"] ?: ""
        val quantity = data["quantity"] ?: ""
        val price = data["price"] ?: ""
        return if (action.isNotEmpty()) {
            "$action $quantity $ticker @ \$${price}"
        } else {
            "New activity"
        }
    }

    private fun showNotification(title: String, body: String, deepLinkUri: String?) {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            if (!deepLinkUri.isNullOrBlank()) data = Uri.parse(deepLinkUri)
        }
        val pending = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_TRADE_ALERTS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()

        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(System.currentTimeMillis().toInt(), notification)
    }

    private fun packageInfoVersionName(): String = try {
        @Suppress("DEPRECATION")
        packageManager.getPackageInfo(packageName, 0).versionName ?: "unknown"
    } catch (_: Exception) {
        "unknown"
    }
}
