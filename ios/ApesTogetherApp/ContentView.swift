import SwiftUI

struct ContentView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @ObservedObject var deepLinkManager = DeepLinkManager.shared
    
    @State private var carouselComplete = false
    @State private var showEarnNudge = false
    @State private var showAddStocks = false
    @State private var subscribedToUsername: String = ""
    
    var body: some View {
        Group {
            if authManager.isAuthenticated {
                if showEarnNudge {
                    // Post-subscribe earn nudge (referral flow step 4)
                    EarnNudgeView(
                        subscribedToUsername: subscribedToUsername,
                        onAddStocks: {
                            showEarnNudge = false
                            showAddStocks = true
                        },
                        onSkip: {
                            showEarnNudge = false
                            deepLinkManager.completeOnboarding()
                        }
                    )
                } else if showAddStocks {
                    // Add stocks screen
                    AddStocksView(
                        headline: "Add Your Stocks",
                        subheadline: "Share your trades and earn from every subscriber",
                        showSkip: true,
                        onComplete: {
                            showAddStocks = false
                            deepLinkManager.completeOnboarding()
                        }
                    )
                    .environmentObject(authManager)
                } else {
                    MainTabView()
                }
            } else if let slug = deepLinkManager.pendingPortfolioSlug {
                // Referral flow: show portfolio preview
                ReferralPreviewView(slug: slug, onSkip: {
                    deepLinkManager.pendingPortfolioSlug = nil
                    carouselComplete = false
                })
                .environmentObject(authManager)
            } else if !deepLinkManager.hasCompletedOnboarding && !carouselComplete {
                // First launch: welcome carousel
                WelcomeCarouselView(isComplete: $carouselComplete)
            } else {
                // Standard login
                LoginView()
            }
        }
        .onChange(of: authManager.isAuthenticated) { newValue in
            if newValue {
                // User just authenticated
                if let slug = deepLinkManager.pendingPortfolioSlug {
                    // Came from referral — navigate to that portfolio to subscribe
                    deepLinkManager.pendingPortfolioSlug = nil
                    subscribedToUsername = ""
                    // Navigate to the portfolio in the main tab view
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        NotificationCenter.default.post(
                            name: .openPortfolio,
                            object: nil,
                            userInfo: ["slug": slug]
                        )
                    }
                }
                deepLinkManager.completeOnboarding()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .openPortfolio)) { notification in
            if let slug = notification.userInfo?["slug"] as? String {
                authManager.navigateToPortfolio(slug: slug)
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .didSubscribe)) { notification in
            if let username = notification.userInfo?["username"] as? String {
                subscribedToUsername = username
                showEarnNudge = true
            }
        }
    }
}

struct MainTabView: View {
    @State private var selectedTab = 0
    
    init() {
        // Configure tab bar appearance
        let appearance = UITabBarAppearance()
        appearance.configureWithOpaqueBackground()
        appearance.backgroundColor = UIColor(Color.appBackground)
        appearance.stackedLayoutAppearance.selected.iconColor = UIColor(Color.primaryAccent)
        appearance.stackedLayoutAppearance.selected.titleTextAttributes = [.foregroundColor: UIColor(Color.primaryAccent)]
        appearance.stackedLayoutAppearance.normal.iconColor = UIColor(Color.textSecondary)
        appearance.stackedLayoutAppearance.normal.titleTextAttributes = [.foregroundColor: UIColor(Color.textSecondary)]
        UITabBar.appearance().standardAppearance = appearance
        UITabBar.appearance().scrollEdgeAppearance = appearance
    }
    
    var body: some View {
        TabView(selection: $selectedTab) {
            LeaderboardView()
                .tabItem {
                    Label("Leaderboard", systemImage: "trophy.fill")
                }
                .tag(0)
            
            MyPortfolioView()
                .tabItem {
                    Label("Portfolio", systemImage: "chart.pie.fill")
                }
                .tag(1)
            
            SubscriptionsView()
                .tabItem {
                    Label("Following", systemImage: "bell.fill")
                }
                .tag(2)
        }
        .accentColor(.primaryAccent)
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .environmentObject(AuthenticationManager())
            .environmentObject(SubscriptionManager())
    }
}
