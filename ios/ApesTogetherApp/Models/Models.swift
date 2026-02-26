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
    let purchaseDate: String?
    
    var id: String { ticker }
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
