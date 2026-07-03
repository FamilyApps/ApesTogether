import Foundation
import UIKit

class APIService {
    static let shared = APIService()
    
    #if DEBUG
    private let baseURL = "https://apestogether.ai/api/mobile"
    #else
    private let baseURL = "https://apestogether.ai/api/mobile"
    #endif
    
    private init() {}
    
    private var authToken: String? {
        KeychainService.shared.getToken()
    }
    
    // MARK: - Authentication
    
    func authenticate(provider: String, idToken: String, email: String?) async throws -> AuthResponse {
        let body: [String: Any] = [
            "provider": provider,
            "id_token": idToken,
            "email": email as Any
        ]
        
        return try await post("/auth/token", body: body, authenticated: false)
    }
    
    func getCurrentUser() async throws -> User {
        return try await get("/auth/user")
    }
    
    func refreshToken() async throws -> AuthResponse {
        return try await post("/auth/refresh", body: [:], authenticated: true)
    }
    
    // MARK: - Device Registration
    
    @MainActor
    func registerDeviceToken(_ token: String) async {
        let deviceId = UIDevice.current.identifierForVendor?.uuidString ?? ""
        let appVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let osVersion = UIDevice.current.systemVersion
        
        let body: [String: Any] = [
            "token": token,
            "platform": "ios",
            "device_id": deviceId,
            "app_version": appVersion,
            "os_version": osVersion
        ]
        
        do {
            let _: EmptyResponse = try await post("/device/register", body: body, authenticated: true)
        } catch {
            print("Failed to register device token: \(error)")
        }
    }
    
    // MARK: - Leaderboard
    
    func getLeaderboard(period: String = "1W", category: String = "all", limit: Int = 50, activeEdge: Bool = true, industry: String = "all", frequency: String = "any", hideFractional: Bool = false) async throws -> LeaderboardResponse {
        let ae = activeEdge ? "1" : "0"
        let hf = hideFractional ? "1" : "0"
        let ind = industry.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? industry
        // authenticated: true — the leaderboard endpoint uses OPTIONAL auth: the
        // backend layers the signed-in viewer's active subscriptions on top of
        // the viewer-agnostic cache to set each entry's `is_subscribed`. Without
        // the Bearer token the viewer is anonymous, so every entry comes back
        // not-subscribed and the UI shows "Subscribe" even for creators the user
        // already follows. (The token is only attached when present, and the
        // endpoint still works for logged-out callers.)
        return try await get("/leaderboard?period=\(period)&category=\(category)&limit=\(limit)&active_edge=\(ae)&industry=\(ind)&frequency=\(frequency)&hide_fractional=\(hf)", authenticated: true)
    }
    
    // MARK: - Portfolio
    
    func getPortfolio(slug: String) async throws -> PortfolioResponse {
        return try await get("/portfolio/\(slug)")
    }
    
    // MARK: - Subscriptions
    
    func getSubscriptions() async throws -> SubscriptionsResponse {
        return try await get("/subscriptions")
    }

    /// Creator earnings summary (estimate, next payout, W-9 status, history)
    /// for the Earnings card on the Subscriptions tab.
    func getPayouts() async throws -> PayoutSummaryResponse {
        return try await get("/payouts")
    }

    /// Resolve which generic store "slot" product to purchase to subscribe to
    /// [subscribedToId]. The backend maps slots to creators per-user (the store
    /// only knows about "Subscription A/B/..."). Returns the slot's product IDs,
    /// or an `error` of "max_reached" / "already_subscribed" (HTTP 409). We decode
    /// the body on both 200 and 409 so the caller can branch on `error`.
    func getSubscriptionSlot(subscribedToId: Int) async throws -> SubscriptionSlotResponse {
        guard let url = URL(string: baseURL + "/subscriptions/slot-for-creator?subscribed_to_id=\(subscribedToId)") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        if httpResponse.statusCode == 401 { throw APIError.unauthorized }
        // 200 = a slot was assigned; 409 = max_reached / already_subscribed.
        // Both carry a JSON body we want to inspect.
        guard httpResponse.statusCode == 200 || httpResponse.statusCode == 409 else {
            throw APIError.serverError(httpResponse.statusCode)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SubscriptionSlotResponse.self, from: data)
    }
    
    func validatePurchase(platform: String, receiptData: String?, purchaseToken: String?, subscribedToId: Int) async throws -> PurchaseValidationResponse {
        var body: [String: Any] = [
            "platform": platform,
            "subscribed_to_id": subscribedToId
        ]
        if let receiptData = receiptData {
            body["receipt_data"] = receiptData
        }
        if let purchaseToken = purchaseToken {
            body["purchase_token"] = purchaseToken
        }
        
        return try await post("/purchase/validate", body: body, authenticated: true)
    }
    
    func updateNotificationSettings(subscriptionId: Int, enabled: Bool) async throws {
        let body: [String: Any] = [
            "subscription_id": subscriptionId,
            "push_notifications_enabled": enabled
        ]
        let _: EmptyResponse = try await put("/notifications/settings", body: body)
    }
    
    func unsubscribe(subscriptionId: Int) async throws -> UnsubscribeResponse {
        return try await delete("/unsubscribe/\(subscriptionId)")
    }

    // MARK: - Phase D: portfolio resizer

    /// Set or update a subscription's scale (target dollar size).
    /// Backend computes scale_factor from current creator portfolio value
    /// at the moment of the call and freezes it.
    func setSubscriptionScale(subscriptionId: Int, targetDollars: Double) async throws -> SetScaleResponse {
        let body: [String: Any] = ["target_dollars": targetDollars]
        return try await post("/subscriptions/\(subscriptionId)/scale", body: body, authenticated: true)
    }

    /// Clear a subscription's scale (return to full unscaled view).
    func clearSubscriptionScale(subscriptionId: Int) async throws {
        let _: EmptyResponse = try await delete("/subscriptions/\(subscriptionId)/scale")
    }

    /// Read the current user's portfolio display preferences.
    func getPortfolioPreferences() async throws -> PortfolioPreferencesResponse {
        return try await get("/settings/portfolio-preferences", authenticated: true)
    }

    /// Update the current user's portfolio preferences. All fields optional —
    /// only the ones passed are changed (e.g. prefer_fractional for the scaled
    /// view, or accepts_new_subscribers for the W7 "Allow New Subscribers" toggle).
    func updatePortfolioPreferences(preferFractional: Bool? = nil,
                                    acceptsNewSubscribers: Bool? = nil) async throws -> PortfolioPreferencesResponse {
        var body: [String: Any] = [:]
        if let preferFractional = preferFractional {
            body["prefer_fractional"] = preferFractional
        }
        if let acceptsNewSubscribers = acceptsNewSubscribers {
            body["accepts_new_subscribers"] = acceptsNewSubscribers
        }
        return try await put("/settings/portfolio-preferences", body: body)
    }
    
    // MARK: - Notification History
    
    func getNotificationHistory(limit: Int = 50, offset: Int = 0) async throws -> NotificationHistoryResponse {
        return try await get("/notifications/history?limit=\(limit)&offset=\(offset)")
    }
    
    // MARK: - Account Management
    
    func deleteAccount() async throws {
        let _: EmptyResponse = try await delete("/auth/account")
    }
    
    // MARK: - Top Influencers
    
    func getTopInfluencers(industry: String = "all", limit: Int = 20) async throws -> TopInfluencersResponse {
        return try await get("/top-influencers?industry=\(industry.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? industry)&limit=\(limit)")
    }
    
    // MARK: - Portfolio Charts
    
    func getPortfolioChart(slug: String, period: String = "1W") async throws -> ChartResponse {
        return try await get("/portfolio/\(slug)/chart?period=\(period)")
    }
    
    // MARK: - Feature Poll
    
    func getActivePoll() async throws -> PollResponse {
        return try await get("/poll/active")
    }
    
    func voteOnPoll(pollId: Int, selectedOption: String) async throws -> PollVoteResponse {
        let body: [String: Any] = [
            "poll_id": pollId,
            "selected_option": selectedOption
        ]
        return try await post("/poll/vote", body: body, authenticated: true)
    }
    
    // MARK: - Stock Price
    
    func getStockPrice(ticker: String) async throws -> StockPriceResponse {
        return try await get("/stock/price/\(ticker)")
    }
    
    // MARK: - Trading
    
    func executeTrade(ticker: String, quantity: Double, price: Double, type: String) async throws -> TradeResponse {
        let body: [String: Any] = [
            "ticker": ticker,
            "quantity": quantity,
            "price": price,
            "type": type
        ]
        return try await post("/portfolio/trade", body: body, authenticated: true)
    }
    
    // MARK: - Portfolio Management
    
    /// `intent` = "buy" for a real market purchase (live price, queued after
    /// hours) or "seed" (default) to declare already-owned holdings.
    func addStocks(stocks: [[String: Any]], intent: String = "seed") async throws -> AddStocksResponse {
        let body: [String: Any] = [
            "stocks": stocks,
            "intent": intent
        ]
        return try await post("/portfolio/stocks", body: body, authenticated: true)
    }
    
    // MARK: - Tax Info (in-app W-9 collection; full TIN is stored only in Xero)

    /// Whether the signed-in creator's W-9 is on file, and whether it's required
    /// (i.e., they're payout-eligible but haven't submitted one yet).
    func getW9Status() async throws -> W9StatusResponse {
        return try await get("/tax/w9/status")
    }

    /// Submit the creator's W-9. The full TIN is forwarded to Xero and never
    /// persisted on our servers. Releases any held payouts on success.
    func submitW9(_ body: [String: Any]) async throws -> W9SubmitResponse {
        return try await post("/tax/w9", body: body, authenticated: true)
    }
    
    // MARK: - Private Helpers
    
    private func get<T: Decodable>(_ endpoint: String, authenticated: Bool = true) async throws -> T {
        guard let url = URL(string: baseURL + endpoint) else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if authenticated, let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError.serverError(httpResponse.statusCode)
        }
        
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
    
    private func post<T: Decodable>(_ endpoint: String, body: [String: Any], authenticated: Bool = true) async throws -> T {
        guard let url = URL(string: baseURL + endpoint) else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        if authenticated, let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            // Surface the server's structured error body {error, message} so the
            // UI can show the specific reason (e.g. USPS address_not_deliverable).
            if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                throw APIError.requestFailed(
                    code: obj["error"] as? String,
                    message: obj["message"] as? String,
                    statusCode: httpResponse.statusCode)
            }
            throw APIError.serverError(httpResponse.statusCode)
        }
        
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
    
    private func put<T: Decodable>(_ endpoint: String, body: [String: Any]) async throws -> T {
        guard let url = URL(string: baseURL + endpoint) else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError.serverError(httpResponse.statusCode)
        }
        
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
    private func delete<T: Decodable>(_ endpoint: String) async throws -> T {
        guard let url = URL(string: baseURL + endpoint) else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError.serverError(httpResponse.statusCode)
        }
        
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
}

enum APIError: LocalizedError, Equatable {
    case invalidURL
    case invalidResponse
    case unauthorized
    case serverError(Int)
    case requestFailed(code: String?, message: String?, statusCode: Int)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid server response"
        case .unauthorized:
            return "Session expired. Please sign in again."
        case .serverError(let code):
            return "Server error (\(code))"
        case .requestFailed(_, let message, let statusCode):
            return message ?? "Request failed (\(statusCode))"
        }
    }
}

struct EmptyResponse: Decodable {}
