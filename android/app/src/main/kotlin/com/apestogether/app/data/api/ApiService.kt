package com.apestogether.app.data.api

import com.apestogether.app.data.models.AddStocksRequest
import com.apestogether.app.data.models.AddStocksResponse
import com.apestogether.app.data.models.AuthRequest
import com.apestogether.app.data.models.AuthResponse
import com.apestogether.app.data.models.ChartResponse
import com.apestogether.app.data.models.EmptyResponse
import com.apestogether.app.data.models.LeaderboardResponse
import com.apestogether.app.data.models.NotificationHistoryResponse
import com.apestogether.app.data.models.NotificationSettingsRequest
import com.apestogether.app.data.models.PollResponse
import com.apestogether.app.data.models.PollVoteRequest
import com.apestogether.app.data.models.PollVoteResponse
import com.apestogether.app.data.models.PortfolioPreferencesResponse
import com.apestogether.app.data.models.PortfolioResponse
import com.apestogether.app.data.models.PurchaseValidationRequest
import com.apestogether.app.data.models.PurchaseValidationResponse
import com.apestogether.app.data.models.PayoutSummaryResponse
import com.apestogether.app.data.models.SetScaleRequest
import com.apestogether.app.data.models.SetScaleResponse
import com.apestogether.app.data.models.UpdatePortfolioPreferencesRequest
import com.apestogether.app.data.models.StockPriceResponse
import com.apestogether.app.data.models.SubscriptionSlotResponse
import com.apestogether.app.data.models.SubscriptionsResponse
import com.apestogether.app.data.models.W9Request
import com.apestogether.app.data.models.W9StatusResponse
import com.apestogether.app.data.models.W9SubmitResponse
import com.apestogether.app.data.models.TopInfluencersResponse
import com.apestogether.app.data.models.TradeRequest
import com.apestogether.app.data.models.TradeResponse
import com.apestogether.app.data.models.UnsubscribeResponse
import com.apestogether.app.data.models.User
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Retrofit interface mirroring iOS [APIService.swift].
 *
 * Base URL is configured in [com.apestogether.app.data.api.di.ApiModule] from
 * `BuildConfig.API_BASE_URL` (defaults to https://apestogether.ai/api/mobile/).
 *
 * Authentication is layered in via [AuthInterceptor], which attaches the
 * `Authorization: Bearer <token>` header for all calls — endpoints that the
 * server treats as public (e.g. /leaderboard) ignore the header.
 */
interface ApiService {

    // ── Authentication ───────────────────────────────────────────────────
    @POST("auth/token")
    suspend fun authenticate(@Body request: AuthRequest): AuthResponse

    @GET("auth/user")
    suspend fun getCurrentUser(): User

    @POST("auth/refresh")
    suspend fun refreshToken(): AuthResponse

    @DELETE("auth/account")
    suspend fun deleteAccount(): EmptyResponse

    // ── Device registration (FCM) ────────────────────────────────────────
    @POST("device/register")
    suspend fun registerDevice(@Body request: DeviceRegistrationRequest): EmptyResponse

    // ── Leaderboard ──────────────────────────────────────────────────────
    @GET("leaderboard")
    suspend fun getLeaderboard(
        @Query("period") period: String = "1W",
        @Query("category") category: String = "all",
        @Query("limit") limit: Int = 50,
        @Query("active_edge") activeEdge: Int = 1,
        @Query("industry") industry: String = "all",
        @Query("frequency") frequency: String = "any",
        @Query("hide_fractional") hideFractional: Int = 0,
    ): LeaderboardResponse

    // ── Top Influencers ──────────────────────────────────────────────────
    @GET("top-influencers")
    suspend fun getTopInfluencers(
        @Query("industry") industry: String = "all",
        @Query("limit") limit: Int = 20,
    ): TopInfluencersResponse

    // ── Portfolio ────────────────────────────────────────────────────────
    @GET("portfolio/{slug}")
    suspend fun getPortfolio(@Path("slug") slug: String): PortfolioResponse

    @GET("portfolio/{slug}/chart")
    suspend fun getPortfolioChart(
        @Path("slug") slug: String,
        @Query("period") period: String = "1W",
    ): ChartResponse

    @POST("portfolio/trade")
    suspend fun executeTrade(@Body request: TradeRequest): TradeResponse

    @POST("portfolio/stocks")
    suspend fun addStocks(@Body request: AddStocksRequest): AddStocksResponse

    // ── Subscriptions / IAP ──────────────────────────────────────────────
    @GET("subscriptions")
    suspend fun getSubscriptions(): SubscriptionsResponse

    /** Creator earnings summary (estimate, next payout, W-9 status, history). */
    @GET("payouts")
    suspend fun getPayouts(): PayoutSummaryResponse

    /**
     * Resolve which generic store "slot" product to purchase to subscribe to
     * [subscribedToId]. The backend maps slots to creators per-user (the store
     * only knows "Subscription A/B/..."). Always returns HTTP 200; on no-go the
     * body carries `error` = "max_reached" / "already_subscribed".
     */
    @GET("subscriptions/slot-for-creator")
    suspend fun getSubscriptionSlot(
        @Query("subscribed_to_id") subscribedToId: Int,
    ): SubscriptionSlotResponse

    @POST("purchase/validate")
    suspend fun validatePurchase(@Body request: PurchaseValidationRequest): PurchaseValidationResponse

    @PUT("notifications/settings")
    suspend fun updateNotificationSettings(@Body request: NotificationSettingsRequest): EmptyResponse

    @DELETE("unsubscribe/{id}")
    suspend fun unsubscribe(@Path("id") subscriptionId: Int): UnsubscribeResponse

    // ── Phase D: portfolio resizer ───────────────────────────────────────
    @POST("subscriptions/{id}/scale")
    suspend fun setSubscriptionScale(
        @Path("id") subscriptionId: Int,
        @Body request: SetScaleRequest,
    ): SetScaleResponse

    @DELETE("subscriptions/{id}/scale")
    suspend fun clearSubscriptionScale(@Path("id") subscriptionId: Int): EmptyResponse

    @GET("settings/portfolio-preferences")
    suspend fun getPortfolioPreferences(): PortfolioPreferencesResponse

    @PUT("settings/portfolio-preferences")
    suspend fun updatePortfolioPreferences(
        @Body request: UpdatePortfolioPreferencesRequest,
    ): PortfolioPreferencesResponse

    // ── Notification history ─────────────────────────────────────────────
    @GET("notifications/history")
    suspend fun getNotificationHistory(
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0,
    ): NotificationHistoryResponse

    // ── Stock data ───────────────────────────────────────────────────────
    @GET("stock/price/{ticker}")
    suspend fun getStockPrice(@Path("ticker") ticker: String): StockPriceResponse

    // ── Feature poll ─────────────────────────────────────────────────────
    @GET("poll/active")
    suspend fun getActivePoll(): PollResponse

    @POST("poll/vote")
    suspend fun voteOnPoll(@Body request: PollVoteRequest): PollVoteResponse

    // ── Tax info / W-9 (in-app collection; full TIN stored only in Xero) ──
    @GET("tax/w9/status")
    suspend fun getW9Status(): W9StatusResponse

    @POST("tax/w9")
    suspend fun submitW9(@Body request: W9Request): W9SubmitResponse
}

/**
 * Request body for FCM token registration. Mirrors the body that iOS's
 * [APIService.registerDeviceToken] sends.
 */
@Serializable
data class DeviceRegistrationRequest(
    val token: String,
    val platform: String,             // "android" or "ios"
    @SerialName("device_id") val deviceId: String,
    @SerialName("app_version") val appVersion: String,
    @SerialName("os_version") val osVersion: String,
)
