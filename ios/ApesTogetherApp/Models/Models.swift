import Foundation

// MARK: - User

struct User: Codable, Identifiable {
    let id: Int
    let email: String
    let username: String
    let portfolioSlug: String?
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
}

// MARK: - Leaderboard

struct LeaderboardResponse: Codable {
    let period: String
    let category: String
    let entries: [LeaderboardEntry]
}

struct LeaderboardEntry: Codable, Identifiable {
    let rank: Int
    let user: LeaderboardUser
    let returnPercent: Double
    let subscriberCount: Int
    let subscriptionPrice: Double
    
    var id: Int { user.id }
}

struct LeaderboardUser: Codable {
    let id: Int
    let username: String
    let portfolioSlug: String?
}

// MARK: - Portfolio

struct PortfolioResponse: Codable {
    let owner: PortfolioOwner
    let isOwner: Bool
    let isSubscribed: Bool
    let subscriptionPrice: Double
    let subscriberCount: Int
    let holdings: [Holding]?
    let recentTrades: [Trade]?
    let previewMessage: String?
}

struct PortfolioOwner: Codable {
    let id: Int
    let username: String
    let portfolioSlug: String?
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
}

struct Trade: Codable, Identifiable {
    let ticker: String
    let quantity: Double
    let price: Double
    let type: String
    let timestamp: String
    
    var id: String { "\(ticker)-\(timestamp)" }
}

// MARK: - Subscriptions

struct SubscriptionsResponse: Codable {
    let subscriptionsMade: [SubscriptionMade]
    let subscribers: [Subscriber]
    let subscriberCount: Int
}

struct SubscriptionMade: Codable, Identifiable {
    let id: Int
    let portfolioOwner: PortfolioOwner?
    let status: String
    let expiresAt: String?
    let pushNotificationsEnabled: Bool
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
}

struct TradeDetail: Codable {
    let ticker: String
    let quantity: Double
    let price: Double
    let type: String
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
