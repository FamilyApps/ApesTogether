@file:Suppress("PropertyName")

package ai.apestogether.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/*
 * Direct port of the iOS Codable structs in
 * `ios/ApesTogetherApp/Models/Models.swift`. Field names match the JSON
 * payload exactly (snake_case) via @SerialName so that Retrofit's
 * kotlinx.serialization converter decodes responses with no extra config.
 *
 * Where the iOS layer exposes a computed `publicName` helper (display_name
 * or username fallback), we provide an equivalent `publicName` extension
 * property so view code reads the same in both apps.
 */

// ── User ──────────────────────────────────────────────────────────────────

@Serializable
data class User(
    val id: Int,
    val email: String,
    val username: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("portfolio_slug") val portfolioSlug: String? = null,
) {
    val publicName: String get() = displayName?.takeIf { it.isNotEmpty() } ?: username
}

// ── Auth ──────────────────────────────────────────────────────────────────

@Serializable
data class AuthResponse(
    val success: Boolean,
    val token: String,
    val user: User,
)

@Serializable
data class AuthRequest(
    val provider: String,            // "google" or "apple"
    @SerialName("id_token") val idToken: String,
    val email: String? = null,
)

@Serializable
data class AddStocksResponse(
    val success: Boolean,
    @SerialName("added_count") val addedCount: Int,
    val errors: List<String>? = null,
)

// ── Leaderboard ───────────────────────────────────────────────────────────

@Serializable
data class LeaderboardResponse(
    val period: String,
    val category: String,
    @SerialName("sp500_return") val sp500Return: Double? = null,
    @SerialName("available_industries") val availableIndustries: List<String>? = null,
    val entries: List<LeaderboardEntry>,
)

@Serializable
data class LeaderboardEntry(
    val rank: Int,
    val user: LeaderboardUser,
    @SerialName("return_percent") val returnPercent: Double,
    @SerialName("sp500_return") val sp500Return: Double? = null,
    @SerialName("alpha_vs_sp500") val alphaVsSp500: Double? = null,
    @SerialName("subscriber_count") val subscriberCount: Int,
    @SerialName("subscription_price") val subscriptionPrice: Double,
    @SerialName("sparkline_data") val sparklineData: List<Double?>? = null,
    @SerialName("sp500_sparkline_data") val sp500SparklineData: List<Double?>? = null,
    @SerialName("avg_trades_per_week") val avgTradesPerWeek: Double? = null,
    @SerialName("unique_stocks") val uniqueStocks: Int? = null,
    @SerialName("large_cap_pct") val largeCapPct: Double? = null,
    @SerialName("account_age_days") val accountAgeDays: Int? = null,
    @SerialName("industry_mix") val industryMix: Map<String, Double>? = null,
    @SerialName("last_trade_date") val lastTradeDate: String? = null,
    @SerialName("rank_change") val rankChange: Int? = null,
)

@Serializable
data class LeaderboardUser(
    val id: Int,
    val username: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("portfolio_slug") val portfolioSlug: String? = null,
) {
    val publicName: String get() = displayName?.takeIf { it.isNotEmpty() } ?: username
}

// ── Portfolio ─────────────────────────────────────────────────────────────

@Serializable
data class PortfolioResponse(
    val owner: PortfolioOwner,
    @SerialName("is_owner") val isOwner: Boolean,
    @SerialName("is_subscribed") val isSubscribed: Boolean,
    @SerialName("subscription_price") val subscriptionPrice: Double,
    @SerialName("subscriber_count") val subscriberCount: Int,
    val holdings: List<Holding>? = null,
    @SerialName("recent_trades") val recentTrades: List<Trade>? = null,
    @SerialName("preview_message") val previewMessage: String? = null,
    @SerialName("leaderboard_badges") val leaderboardBadges: List<LeaderboardBadge>? = null,
    @SerialName("industry_mix") val industryMix: Map<String, Double>? = null,
    @SerialName("large_cap_pct") val largeCapPct: Double? = null,
    @SerialName("account_age_days") val accountAgeDays: Int? = null,
    @SerialName("avg_trades_per_week") val avgTradesPerWeek: Double? = null,
    @SerialName("num_stocks") val numStocks: Int? = null,
    @SerialName("portfolio_value") val portfolioValue: Double? = null,
)

@Serializable
data class LeaderboardBadge(
    val period: String,
    val rank: Int,
    val type: String,                 // "overall" or "sector"
    val sector: String? = null,
)

@Serializable
data class PortfolioOwner(
    val id: Int,
    val username: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("portfolio_slug") val portfolioSlug: String? = null,
) {
    val publicName: String get() = displayName?.takeIf { it.isNotEmpty() } ?: username
}

@Serializable
data class Holding(
    val ticker: String,
    val quantity: Double,
    @SerialName("purchase_price") val purchasePrice: Double,
    @SerialName("current_price") val currentPrice: Double? = null,
    @SerialName("purchase_date") val purchaseDate: String? = null,
) {
    val displayPrice: Double get() = currentPrice ?: purchasePrice
    val totalValue: Double get() = displayPrice * quantity
    val gainPercent: Double? get() {
        val cur = currentPrice ?: return null
        if (purchasePrice <= 0.0 || cur <= 0.0) return null
        return ((cur - purchasePrice) / purchasePrice) * 100
    }
}

@Serializable
data class Trade(
    val ticker: String,
    val quantity: Double,
    val price: Double,
    val type: String,
    val timestamp: String,
)

// ── Subscriptions ─────────────────────────────────────────────────────────

@Serializable
data class SubscriptionsResponse(
    @SerialName("subscriptions_made") val subscriptionsMade: List<SubscriptionMade>,
    val subscribers: List<Subscriber>,
    @SerialName("subscriber_count") val subscriberCount: Int,
)

@Serializable
data class SubscriptionMade(
    val id: Int,
    @SerialName("portfolio_owner") val portfolioOwner: PortfolioOwner? = null,
    val status: String,
    @SerialName("expires_at") val expiresAt: String? = null,
    @SerialName("push_notifications_enabled") val pushNotificationsEnabled: Boolean,
)

@Serializable
data class Subscriber(
    val id: Int,
    val subscriber: SubscriberUser? = null,
    val status: String,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class SubscriberUser(
    val id: Int,
    val username: String,
    @SerialName("display_name") val displayName: String? = null,
) {
    val publicName: String get() = displayName?.takeIf { it.isNotEmpty() } ?: username
}

// ── Purchase / IAP ────────────────────────────────────────────────────────

@Serializable
data class PurchaseValidationRequest(
    val platform: String,                          // "ios" or "android"
    @SerialName("subscribed_to_id") val subscribedToId: Int,
    @SerialName("receipt_data") val receiptData: String? = null,    // iOS
    @SerialName("purchase_token") val purchaseToken: String? = null, // Android
)

@Serializable
data class PurchaseValidationResponse(
    val success: Boolean,
    @SerialName("purchase_id") val purchaseId: Int? = null,
    @SerialName("subscription_status") val subscriptionStatus: String? = null,
    @SerialName("expires_date") val expiresDate: String? = null,
    val error: String? = null,
)

// ── Portfolio Chart ───────────────────────────────────────────────────────

@Serializable
data class ChartResponse(
    @SerialName("portfolio_return") val portfolioReturn: Double,
    @SerialName("sp500_return") val sp500Return: Double,
    @SerialName("chart_data") val chartData: List<ChartPoint>,
    val period: String,
    @SerialName("leaderboard_eligible") val leaderboardEligible: Boolean? = null,
    @SerialName("days_active") val daysActive: Int? = null,
    @SerialName("days_required") val daysRequired: Int? = null,
    @SerialName("eligible_date") val eligibleDate: String? = null,
    @SerialName("first_activity_date") val firstActivityDate: String? = null,
)

@Serializable
data class ChartPoint(
    val date: String,
    val portfolio: Double? = null,
    val sp500: Double? = null,
)

// ── Stock price / trade ───────────────────────────────────────────────────

@Serializable
data class StockPriceResponse(
    val ticker: String,
    val price: Double,
    val source: String? = null,
)

@Serializable
data class TradeRequest(
    val ticker: String,
    val quantity: Double,
    val price: Double,
    val type: String,
)

@Serializable
data class TradeResponse(
    val success: Boolean,
    val trade: TradeDetail? = null,
    val error: String? = null,
)

@Serializable
data class TradeDetail(
    val ticker: String,
    val quantity: Double,
    val price: Double,
    val type: String,
)

@Serializable
data class AddStocksRequest(
    val stocks: List<StockEntry>,
)

@Serializable
data class StockEntry(
    val ticker: String,
    val quantity: Double,
    @SerialName("purchase_price") val purchasePrice: Double? = null,
    @SerialName("purchase_date") val purchaseDate: String? = null,
)

// ── Top influencers ───────────────────────────────────────────────────────

@Serializable
data class TopInfluencersResponse(
    val entries: List<InfluencerEntry>,
    @SerialName("available_industries") val availableIndustries: List<String>,
    val total: Int,
)

@Serializable
data class InfluencerEntry(
    val rank: Int,
    val user: LeaderboardUser,
    @SerialName("subscriber_count") val subscriberCount: Int,
    @SerialName("unique_stocks") val uniqueStocks: Int,
    @SerialName("avg_trades_per_week") val avgTradesPerWeek: Double,
    @SerialName("top_industries") val topIndustries: List<IndustryInfo>,
)

@Serializable
data class IndustryInfo(
    val name: String,
    val percent: Double,
)

// ── Feature poll ──────────────────────────────────────────────────────────

@Serializable
data class PollResponse(
    val poll: PollData? = null,
)

@Serializable
data class PollData(
    val id: Int,
    val question: String,
    val options: List<String>,
    @SerialName("total_votes") val totalVotes: Int,
    val results: List<PollOptionResult>,
    @SerialName("user_voted") val userVoted: String? = null,
)

@Serializable
data class PollOptionResult(
    val option: String,
    val votes: Int,
)

@Serializable
data class PollVoteRequest(
    @SerialName("poll_id") val pollId: Int,
    @SerialName("selected_option") val selectedOption: String,
)

@Serializable
data class PollVoteResponse(
    val success: Boolean? = null,
    @SerialName("selected_option") val selectedOption: String? = null,
    val error: String? = null,
)

// ── Notification history ──────────────────────────────────────────────────

@Serializable
data class NotificationHistoryResponse(
    val notifications: List<NotificationItem>,
    val total: Int,
    val limit: Int,
    val offset: Int,
)

@Serializable
data class NotificationItem(
    val id: String,
    val type: String,
    @SerialName("trader_username") val traderUsername: String,
    val status: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    val title: String? = null,
    val body: String? = null,
)

// ── Unsubscribe + settings ────────────────────────────────────────────────

@Serializable
data class UnsubscribeResponse(
    val success: Boolean? = null,
    val message: String? = null,
)

@Serializable
data class NotificationSettingsRequest(
    @SerialName("subscription_id") val subscriptionId: Int,
    @SerialName("push_notifications_enabled") val pushNotificationsEnabled: Boolean,
)

// ── Tax status ────────────────────────────────────────────────────────────

@Serializable
data class TaxStatusResponse(
    @SerialName("tax_info_on_file") val taxInfoOnFile: Boolean,
    val status: String,
    val message: String,
)

// ── Empty response (for endpoints that just return {success: true}) ───────

@Serializable
data class EmptyResponse(
    val success: Boolean? = null,
)
