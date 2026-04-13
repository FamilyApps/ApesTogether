import SwiftUI
import Combine

@MainActor
class DeepLinkManager: ObservableObject {
    static let shared = DeepLinkManager()
    
    @Published var pendingPortfolioSlug: String?
    @Published var pendingPeriod: String?
    @Published var hasCompletedOnboarding: Bool
    
    private let onboardingKey = "hasCompletedOnboarding"
    private let validPeriods: Set<String> = ["1D", "1W", "1M", "3M", "YTD", "1Y"]
    
    private init() {
        self.hasCompletedOnboarding = UserDefaults.standard.bool(forKey: onboardingKey)
    }
    
    func completeOnboarding() {
        hasCompletedOnboarding = true
        UserDefaults.standard.set(true, forKey: onboardingKey)
    }
    
    func handleUniversalLink(_ url: URL) {
        // Parse apestogether.ai/p/{slug}?period=1W
        guard let host = url.host,
              host.contains("apestogether.ai") else { return }
        
        let pathComponents = url.pathComponents
        // pathComponents: ["/", "p", "{slug}"]
        if pathComponents.count >= 3 && pathComponents[1] == "p" {
            let slug = pathComponents[2]
            pendingPortfolioSlug = slug
            
            // Parse ?period= query parameter
            if let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
               let periodParam = components.queryItems?.first(where: { $0.name == "period" })?.value,
               validPeriods.contains(periodParam.uppercased()) {
                pendingPeriod = periodParam.uppercased()
            } else {
                pendingPeriod = nil
            }
        }
    }
    
    func consumePendingSlug() -> (slug: String, period: String?)? {
        guard let slug = pendingPortfolioSlug else { return nil }
        let period = pendingPeriod
        pendingPortfolioSlug = nil
        pendingPeriod = nil
        return (slug, period)
    }
}
