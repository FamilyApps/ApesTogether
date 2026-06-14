import Foundation

// MARK: - User

struct User: Codable, Identifiable {
    let id: Int
    let email: String
    let username: String
    let displayName: String?
    let portfolioSlug: String?
    // Count of the user's own holdings (from GET /auth/user). Lets the
    // post-subscribe nudge skip the "Add Your Stocks" pitch for users who
    // are already creators. Optional for backward-compat with older payloads.
    let numStocks: Int?

    /// Public-facing name. Falls back to `username` when `displayName` is nil/empty.
    var publicName: String {
        if let dn = displayName, !dn.isEmpty { return dn }
        return username
    }
}

// MARK: - Auth

struct AuthResponse: Codable {
    let success: Bool
    let token: String
    let user: User
}

struct AddStocksResponse: Codable {
    let success: Bool
    let addedCount: Int
    let errors: [String]?
    // When the market is closed, an intent='buy' request is queued instead of
    // executed. `pending` is true and `queuedCount` holds how many were queued.
    let pending: Bool?
    let queuedCount: Int?
}

// MARK: - Leaderboard

struct LeaderboardResponse: Codable {
    let period: String
    let category: String
    let sp500Return: Double?
    let availableIndustries: [String]?
    let entries: [LeaderboardEntry]
}

struct LeaderboardEntry: Codable, Identifiable {
    let rank: Int
    let user: LeaderboardUser
    let returnPercent: Double
    let sp500Return: Double?
    let alphaVsSp500: Double?
    let subscriberCount: Int
    let subscriptionPrice: Double
    let sparklineData: [Double?]?
    let sp500SparklineData: [Double?]?
    let avgTradesPerWeek: Double?
    let uniqueStocks: Int?
    let largeCapPct: Double?
    let accountAgeDays: Int?
    let industryMix: [String: Double]?
    let lastTradeDate: String?
    let rankChange: Int?
    // Per-viewer: true when the signed-in viewer already follows this creator
    // (or is this creator). Drives "View Portfolio"-only rendering. Optional
    // for backward-compat with anonymous/legacy responses.
    let isSubscribed: Bool?
    
    var id: Int { user.id }
}

struct LeaderboardUser: Codable {
    let id: Int
    let username: String
    let displayName: String?
    let portfolioSlug: String?

    var publicName: String {
        if let dn = displayName, !dn.isEmpty { return dn }
        return username
    }
}

// MARK: - Portfolio

struct PortfolioResponse: Codable {
    let owner: PortfolioOwner
    let isOwner: Bool
    let isSubscribed: Bool
    // Phase D: subscription_id surfaced by GET /portfolio/<slug> when the
    // viewer is the subscriber, so the scale modal can call
    // POST/DELETE /subscriptions/<id>/scale directly. Nil for owner-view
    // and not-subscribed-view.
    let subscriptionId: Int?
    let subscriptionPrice: Double
    let subscriberCount: Int
    let holdings: [Holding]?
    let recentTrades: [Trade]?
    let previewMessage: String?
    let leaderboardBadges: [LeaderboardBadge]?
    let industryMix: [String: Double]?
    let largeCapPct: Double?
    let accountAgeDays: Int?
    let avgTradesPerWeek: Double?
    let numStocks: Int?
    let portfolioValue: Double?
    let cashBalance: Double?

    // ── Phase D: portfolio resizer ──────────────────────────────────────
    // `scale` is populated only when the viewer is a subscriber whose
    // subscription has a non-NULL scale_factor on the server. When
    // present, `holdings.quantity`, `portfolioValue`, and `cashBalance`
    // in this response are ALREADY SCALED. `scale.unscaledPortfolioValue`
    // is the original creator portfolio total — render as "Scaled from $X"
    // in the UI for context.
    let scale: PortfolioScale?
    // Count of positions that floor-rounded to 0 shares at the current
    // scale (only populated when prefer_fractional is false). The UI
    // surfaces this as "+N positions below 1 share at this scale".
    let belowOneShareCount: Int?
}

/// Phase D scale metadata for a scaled subscriber view. Nil when the
/// subscription has no scale set (= full unscaled portfolio).
struct PortfolioScale: Codable {
    /// The multiplier applied to all share quantities. e.g. 0.1234
    /// means subscriber sees 12.34% of each creator position.
    let scaleFactor: Double
    /// Dollar amount the subscriber chose when configuring scale.
    /// Frozen — does NOT track market drift on the creator portfolio.
    let targetDollars: Double
    /// ISO-8601 timestamp (UTC, with Z) of when scale was set.
    let scaleSetAt: String?
    /// Unscaled portfolio value (full creator total) at THIS moment.
    /// Use this in the UI for "Scaled from $81,037" subtitle.
    let unscaledPortfolioValue: Double
}

struct LeaderboardBadge: Codable, Identifiable {
    let period: String
    let rank: Int
    let type: String        // "overall" or "sector"
    let sector: String?     // only for type == "sector"
    
    var id: String { "\(type)_\(period)_\(sector ?? "")" }
}

struct PortfolioOwner: Codable {
    let id: Int
    let username: String
    let displayName: String?
    let portfolioSlug: String?

    var publicName: String {
        if let dn = displayName, !dn.isEmpty { return dn }
        return username
    }
}

struct Holding: Codable, Identifiable {
    let ticker: String
    let quantity: Double
    let purchasePrice: Double
    let currentPrice: Double?
    let purchaseDate: String?
    
    var id: String { ticker }
    
    var displayPrice: Double {
        currentPrice ?? purchasePrice
    }
    
    var totalValue: Double {
        displayPrice * quantity
    }
    
    var gainPercent: Double? {
        guard purchasePrice > 0, let current = currentPrice, current > 0 else { return nil }
        return ((current - purchasePrice) / purchasePrice) * 100
    }

    /// Absolute $ gain on the position. Nil if `purchasePrice` is missing/0
    /// (matches the same guard as `gainPercent` so the UI stays consistent).
    var gainDollars: Double? {
        guard purchasePrice > 0, let current = currentPrice, current > 0 else { return nil }
        return (current - purchasePrice) * quantity
    }

    /// Quantity formatted for display.
    /// - Whole-share positions (e.g. 10.0) show as "10"
    /// - Fractional positions show with up to 5 decimals, trailing zeros
    ///   trimmed (e.g. 0.5 → "0.5", 1.23456 → "1.23456", 0.10000 → "0.1")
    ///
    /// 5 decimals is the precision used by Phase D scaled views — a
    /// $100 scale on a 50-share position can yield qty like 0.06173.
    /// Whole shares from non-scaled views still render cleanly as integers.
    var formattedQuantity: String {
        let rounded = quantity.rounded()
        if abs(quantity - rounded) < 0.000005 {
            return String(format: "%.0f", quantity)
        }
        // Format to 5 decimals, then strip trailing zeros + dangling '.'
        let raw = String(format: "%.5f", quantity)
        var trimmed = raw
        if trimmed.contains(".") {
            while trimmed.hasSuffix("0") { trimmed.removeLast() }
            if trimmed.hasSuffix(".") { trimmed.removeLast() }
        }
        return trimmed
    }

    /// Returns this position's share of the owner's portfolio as a percent
    /// (0–100). Returns nil when `portfolioValue` is unavailable or zero.
    func percentOfPortfolio(_ portfolioValue: Double?) -> Double? {
        guard let total = portfolioValue, total > 0 else { return nil }
        return (totalValue / total) * 100
    }
}

struct Trade: Codable, Identifiable {
    let ticker: String
    let quantity: Double
    // null for PENDING (after-hours) trades whose price isn't set until
    // the market-open settlement establishes it.
    let price: Double?
    let type: String
    let timestamp: String
    // 'executed' or 'pending'. Optional for backwards compatibility.
    let status: String?
    // Present on pending trades so the app can offer a cancel action.
    let pendingId: Int?
    
    var isPending: Bool { (status?.lowercased() == "pending") || price == nil }
    
    var id: String { "\(status ?? "x")-\(ticker)-\(timestamp)" }
}

// MARK: - Subscriptions

struct SubscriptionsResponse: Codable {
    let subscriptionsMade: [SubscriptionMade]
    let subscribers: [Subscriber]
    let subscriberCount: Int
}

/// Response from /subscriptions/slot-for-creator. On success `slot` + the
/// product IDs are set; on a 409 `error` is "max_reached" or "already_subscribed".
struct SubscriptionSlotResponse: Codable {
    let slot: Int?
    let slotLabel: String?
    let monthlyProductId: String?
    let annualProductId: String?
    let maxSlots: Int?
    let error: String?
}

struct SubscriptionMade: Codable, Identifiable {
    let id: Int
    let portfolioOwner: PortfolioOwner?
    let status: String
    let expiresAt: String?
    let pushNotificationsEnabled: Bool
    // Per-creator store slot (1..N) + its letter label ("A".."T"). The store
    // shows generic "Subscription A/B/..." entries; this tells the user which
    // one maps to this creator so they cancel the right one. Optional for
    // legacy rows created before the slot feature.
    let slot: Int?
    let slotLabel: String?
}

struct Subscriber: Codable, Identifiable {
    let id: Int
    let subscriber: SubscriberUser?
    let status: String
    let createdAt: String
}

struct SubscriberUser: Codable {
    let id: Int
    let username: String
    let displayName: String?

    var publicName: String {
        if let dn = displayName, !dn.isEmpty { return dn }
        return username
    }
}

// MARK: - Purchase

struct PurchaseValidationResponse: Codable {
    let success: Bool
    let purchaseId: Int?
    let subscriptionStatus: String?
    let expiresDate: String?
    let error: String?
}

// MARK: - Portfolio Chart

struct ChartResponse: Codable {
    let portfolioReturn: Double
    let sp500Return: Double
    let chartData: [ChartPoint]
    let period: String
    
    // Leaderboard eligibility (for banner display)
    let leaderboardEligible: Bool?
    let daysActive: Int?
    let daysRequired: Int?
    let eligibleDate: String?       // ISO date when user will become eligible
    let firstActivityDate: String?  // ISO date of user's first trade/asset
}

struct ChartPoint: Codable, Identifiable {
    let date: String
    let portfolio: Double?
    let sp500: Double?
    
    // Use index-based ID to avoid crashes from duplicate date labels
    // (e.g. "Mar '25" appearing multiple times in 1Y chart)
    var index: Int?
    var id: String { "\(index ?? 0)_\(date)" }
    
    enum CodingKeys: String, CodingKey {
        case date, portfolio, sp500
    }
}

// MARK: - Stock Price

struct StockPriceResponse: Codable {
    let ticker: String
    let price: Double
    let source: String?
}

// MARK: - Trade

struct TradeResponse: Codable {
    let success: Bool
    let trade: TradeDetail?
    let error: String?
    // True when an after-hours trade was queued rather than executed.
    let pending: Bool?
    let message: String?
}

struct TradeDetail: Codable {
    let ticker: String
    let quantity: Double
    let price: Double?
    let type: String
    let status: String?
}

// MARK: - Top Influencers

struct TopInfluencersResponse: Codable {
    let entries: [InfluencerEntry]
    let availableIndustries: [String]
    let total: Int
}

struct InfluencerEntry: Codable, Identifiable {
    let rank: Int
    let user: LeaderboardUser
    let subscriberCount: Int
    let uniqueStocks: Int
    let avgTradesPerWeek: Double
    let topIndustries: [IndustryInfo]
    
    var id: Int { user.id }
}

struct IndustryInfo: Codable, Identifiable {
    let name: String
    let percent: Double
    
    var id: String { name }
}

// MARK: - Feature Poll

struct PollResponse: Codable {
    let poll: PollData?
}

struct PollData: Codable, Identifiable {
    let id: Int
    let question: String
    let options: [String]
    let totalVotes: Int
    let results: [PollOptionResult]
    let userVoted: String?
}

struct PollOptionResult: Codable, Identifiable {
    let option: String
    let votes: Int
    
    var id: String { option }
}

struct PollVoteResponse: Codable {
    let success: Bool?
    let selectedOption: String?
    let error: String?
}

// MARK: - Notification History

struct NotificationHistoryResponse: Codable {
    let notifications: [NotificationItem]
    let total: Int
    let limit: Int
    let offset: Int
}

struct NotificationItem: Codable, Identifiable {
    let id: String
    let type: String
    let traderUsername: String
    let status: String?
    let createdAt: String?
    let title: String?
    let body: String?
}

// MARK: - Unsubscribe

struct UnsubscribeResponse: Codable {
    let success: Bool?
    let message: String?
}

// MARK: - Phase D: portfolio resizer

/// Response from POST /subscriptions/<id>/scale. Mirrors the JSON
/// returned by `mobile_api.set_subscription_scale`.
struct SetScaleResponse: Codable {
    let success: Bool
    let scaleFactor: Double
    let targetDollars: Double
    let scaleSetAt: String?
    let targetPortfolioValue: Double
}

/// Response from GET/PUT /settings/portfolio-preferences. Currently
/// exposes only prefer_fractional but designed to grow.
struct PortfolioPreferencesResponse: Codable {
    let preferFractional: Bool
    // success is only set on the PUT response; optional so the GET
    // response decodes cleanly too.
    let success: Bool?
}
