@file:Suppress("PropertyName")

package com.apestogether.app.data.models

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
    // Count of the user's own holdings. Returned by GET /auth/user so the
    // post-subscribe nudge can skip the "Add Your Stocks" pitch for users
    // who are already creators. Null until /auth/user has been hydrated.
    @SerialName("num_stocks") val numStocks: Int? = null,
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
    // Per-viewer: true when the signed-in viewer already follows this creator
    // (or is this creator). Drives "View Portfolio"-only rendering on the
    // leaderboard card. Defaults false for anonymous/legacy responses.
    @SerialName("is_subscribed") val isSubscribed: Boolean = false,
    // W7: false when the creator turned off "Allow New Subscribers". The row
    // still appears; clients swap the Subscribe CTA for explanatory copy.
    // Optional/defaults-to-accepting for legacy responses.
    @SerialName("accepts_new_subscribers") val acceptsNewSubscribers: Boolean? = null,
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
    // Phase D: subscription_id surfaced by GET /portfolio/<slug> when the
    // viewer is the subscriber, so the Compose UI can call
    // POST/DELETE /subscriptions/<id>/scale directly. Null for owner-view
    // and not-subscribed-view.
    @SerialName("subscription_id") val subscriptionId: Int? = null,
    @SerialName("subscription_price") val subscriptionPrice: Double,
    @SerialName("subscriber_count") val subscriberCount: Int,
    // W7: false when this creator isn't accepting new subscribers. Clients
    // replace the Subscribe CTA with explanatory copy (existing subscribers
    // and the owner are unaffected). Optional for legacy responses.
    @SerialName("accepts_new_subscribers") val acceptsNewSubscribers: Boolean? = null,
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
    // Phase B: dedicated cash line in the Holdings list. Only populated by the
    // mobile_api when cash_balance > $0.005, so a `null` here means
    // "fully invested, no cash row to render". See mobile_api.py:721-725.
    @SerialName("cash_balance") val cashBalance: Double? = null,
    // ── Phase D: portfolio resizer ──────────────────────────────────────
    // When non-null, the holdings.quantity / portfolioValue / cashBalance
    // in this response are ALREADY SCALED. Only populated when the viewer
    // is a subscriber whose subscription has scale_factor set on the
    // server. See mobile_api._scale_qty + the `scale` block.
    val scale: PortfolioScale? = null,
    // Count of positions that floor-rounded to 0 shares at the current
    // scale (only set when prefer_fractional is false). UI renders this
    // as "+N positions below 1 share at this scale" footer.
    @SerialName("below_one_share_count") val belowOneShareCount: Int? = null,
)

/**
 * Phase D scale metadata for a scaled subscriber view. Null when the
 * subscription has no scale set (= full unscaled portfolio).
 */
@Serializable
data class PortfolioScale(
    /** Multiplier applied to all share quantities. e.g. 0.1234. */
    @SerialName("scale_factor") val scaleFactor: Double,
    /** Dollar amount the subscriber chose at set-time. Frozen. */
    @SerialName("target_dollars") val targetDollars: Double,
    /** ISO-8601 timestamp (UTC, with Z) of when scale was set. */
    @SerialName("scale_set_at") val scaleSetAt: String? = null,
    /** Unscaled creator portfolio total at this moment. UI shows
     *  "Scaled from $81,037" using this. */
    @SerialName("unscaled_portfolio_value") val unscaledPortfolioValue: Double,
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

    /**
     * Absolute $ gain on the position. Null when purchasePrice is missing/0
     * (same guard as [gainPercent]), so the UI stays consistent. Mirrors the
     * iOS Holding.gainDollars computed property.
     */
    val gainDollars: Double? get() {
        val cur = currentPrice ?: return null
        if (purchasePrice <= 0.0 || cur <= 0.0) return null
        return (cur - purchasePrice) * quantity
    }

    /**
     * Quantity formatted for display.
     *  - Whole shares (e.g. 10.0) → "10"
     *  - Fractional → up to 5 decimals, trailing zeros trimmed
     *
     * 5 decimals is the precision used by Phase D scaled views — a $100
     * scale on a 50-share position can yield qty like 0.06173. Whole-
     * share positions still render as integers without trailing dots.
     */
    val formattedQuantity: String
        get() {
            val rounded = kotlin.math.round(quantity)
            if (kotlin.math.abs(quantity - rounded) < 0.000005) {
                return rounded.toLong().toString()
            }
            val raw = "%.5f".format(quantity)
            // Strip trailing zeros + dangling '.'
            var trimmed = raw
            if ('.' in trimmed) {
                trimmed = trimmed.trimEnd('0').trimEnd('.')
            }
            return trimmed
        }
}

@Serializable
data class Trade(
    val ticker: String,
    val quantity: Double,
    // null for PENDING (after-hours) trades — price isn't set until the
    // market-open settlement establishes it.
    val price: Double? = null,
    val type: String,
    val timestamp: String,
    // 'executed' or 'pending'.
    val status: String? = null,
    @SerialName("pending_id") val pendingId: Int? = null,
) {
    val isPending: Boolean
        get() = (status?.lowercase() == "pending") || price == null
}

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
    // Per-creator store slot (1..N) + its letter label ("A".."T"). The store
    // shows generic "Subscription A/B/..." entries; this tells the user which
    // one maps to this creator. Null for legacy rows predating the slot feature.
    val slot: Int? = null,
    @SerialName("slot_label") val slotLabel: String? = null,
)

/**
 * Response from GET subscriptions/slot-for-creator. On success [slot] + the
 * product IDs are set; otherwise [error] is "max_reached" or "already_subscribed".
 * The backend always returns HTTP 200 so this decodes uniformly.
 */
@Serializable
data class SubscriptionSlotResponse(
    val slot: Int? = null,
    @SerialName("slot_label") val slotLabel: String? = null,
    @SerialName("monthly_product_id") val monthlyProductId: String? = null,
    @SerialName("annual_product_id") val annualProductId: String? = null,
    @SerialName("max_slots") val maxSlots: Int? = null,
    val error: String? = null,
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
    val platform: String,                          // "apple" or "google" (matches backend `Platform` enum)
    @SerialName("subscribed_to_id") val subscribedToId: Int,
    @SerialName("receipt_data") val receiptData: String? = null,    // Apple: StoreKit 2 JWS or legacy base64 receipt
    @SerialName("purchase_token") val purchaseToken: String? = null, // Google: Play Billing purchase token
    @SerialName("product_id") val productId: String? = null,        // Google: purchased SKU (pricing/accounting hint)
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

// ── Phase D: portfolio resizer ───────────────────────────────────────────

/** Body for POST /subscriptions/<id>/scale. */
@Serializable
data class SetScaleRequest(
    @SerialName("target_dollars") val targetDollars: Double,
)

/** Response from POST /subscriptions/<id>/scale. Mirrors mobile_api. */
@Serializable
data class SetScaleResponse(
    val success: Boolean,
    @SerialName("scale_factor") val scaleFactor: Double,
    @SerialName("target_dollars") val targetDollars: Double,
    @SerialName("scale_set_at") val scaleSetAt: String? = null,
    @SerialName("target_portfolio_value") val targetPortfolioValue: Double,
)

/** Response from GET/PUT /settings/portfolio-preferences. */
@Serializable
data class PortfolioPreferencesResponse(
    @SerialName("prefer_fractional") val preferFractional: Boolean,
    // W7: whether this creator is accepting NEW subscribers (default true).
    @SerialName("accepts_new_subscribers") val acceptsNewSubscribers: Boolean? = null,
    val success: Boolean? = null,
)

/** Body for PUT /settings/portfolio-preferences. All fields optional —
 *  only provided fields are mutated. */
@Serializable
data class UpdatePortfolioPreferencesRequest(
    @SerialName("prefer_fractional") val preferFractional: Boolean? = null,
    @SerialName("accepts_new_subscribers") val acceptsNewSubscribers: Boolean? = null,
)

// ── Tax info / W-9 (in-app collection; full TIN stored only in Xero) ───────

@Serializable
data class W9StatusResponse(
    val status: String,                                  // not_submitted | submitted | on_file | failed
    val required: Boolean = false,                       // payout-eligible and not yet on file
    @SerialName("on_file") val onFile: Boolean = false,
    @SerialName("tin_last4") val tinLast4: String? = null,
    @SerialName("legal_name") val legalName: String? = null,
    @SerialName("held_payout_count") val heldPayoutCount: Int = 0,
    @SerialName("held_payout_total") val heldPayoutTotal: Double = 0.0,
)

@Serializable
data class W9Request(
    @SerialName("legal_name") val legalName: String,
    @SerialName("business_name") val businessName: String? = null,
    @SerialName("tax_classification") val taxClassification: String,
    @SerialName("tin_type") val tinType: String,         // "ssn" | "ein"
    val tin: String,                                     // 9 digits (server strips non-digits)
    @SerialName("address_line1") val addressLine1: String,
    @SerialName("address_line2") val addressLine2: String? = null,
    val city: String,
    val state: String,
    @SerialName("postal_code") val postalCode: String,
    val country: String = "US",
    val certified: Boolean,
)

@Serializable
data class W9SubmitResponse(
    val status: String,
    @SerialName("on_file") val onFile: Boolean = false,
    @SerialName("tin_last4") val tinLast4: String? = null,
    @SerialName("released_payouts") val releasedPayouts: Int? = null,
    val message: String? = null,
)

// ── Empty response (for endpoints that just return {success: true}) ───────

@Serializable
data class EmptyResponse(
    val success: Boolean? = null,
)
