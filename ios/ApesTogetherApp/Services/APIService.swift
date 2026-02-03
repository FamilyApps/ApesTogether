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
    
    func registerDeviceToken(_ token: String) async {
        let body: [String: Any] = [
            "token": token,
            "platform": "ios",
            "device_id": UIDevice.current.identifierForVendor?.uuidString ?? "",
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0",
            "os_version": UIDevice.current.systemVersion
        ]
        
        do {
            let _: EmptyResponse = try await post("/device/register", body: body, authenticated: true)
        } catch {
            print("Failed to register device token: \(error)")
        }
    }
    
    // MARK: - Leaderboard
    
    func getLeaderboard(period: String = "7D", category: String = "all", limit: Int = 50) async throws -> LeaderboardResponse {
        return try await get("/leaderboard?period=\(period)&category=\(category)&limit=\(limit)", authenticated: false)
    }
    
    // MARK: - Portfolio
    
    func getPortfolio(slug: String) async throws -> PortfolioResponse {
        return try await get("/portfolio/\(slug)")
    }
    
    // MARK: - Subscriptions
    
    func getSubscriptions() async throws -> SubscriptionsResponse {
        return try await get("/subscriptions")
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
}

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case serverError(Int)
    
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
        }
    }
}

struct EmptyResponse: Decodable {}
