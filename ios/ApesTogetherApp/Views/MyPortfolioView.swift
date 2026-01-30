import SwiftUI

struct MyPortfolioView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                if let user = authManager.currentUser, let slug = user.portfolioSlug {
                    PortfolioDetailView(slug: slug)
                } else {
                    ContentUnavailableView(
                        "No Portfolio",
                        systemImage: "chart.pie",
                        description: Text("Add stocks on the web to see your portfolio here.")
                    )
                }
            }
            .navigationTitle("My Portfolio")
        }
    }
}

#Preview {
    MyPortfolioView()
        .environmentObject(AuthenticationManager())
        .environmentObject(SubscriptionManager())
}
