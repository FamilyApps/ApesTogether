import SwiftUI

@MainActor
class DeepLinkManager: ObservableObject {
    static let shared = DeepLinkManager()
    
    @Published var pendingPortfolioSlug: String?
    @Published var hasCompletedOnboarding: Bool
    
    private let onboardingKey = "hasCompletedOnboarding"
    
    private init() {
        self.hasCompletedOnboarding = UserDefaults.standard.bool(forKey: onboardingKey)
    }
    
    func completeOnboarding() {
        hasCompletedOnboarding = true
        UserDefaults.standard.set(true, forKey: onboardingKey)
    }
    
    func handleUniversalLink(_ url: URL) {
        // Parse apestogether.ai/p/{slug}
        guard let host = url.host,
              host.contains("apestogether.ai") else { return }
        
        let pathComponents = url.pathComponents
        // pathComponents: ["/", "p", "{slug}"]
        if pathComponents.count >= 3 && pathComponents[1] == "p" {
            let slug = pathComponents[2]
            pendingPortfolioSlug = slug
        }
    }
    
    func consumePendingSlug() -> String? {
        let slug = pendingPortfolioSlug
        pendingPortfolioSlug = nil
        return slug
    }
}
