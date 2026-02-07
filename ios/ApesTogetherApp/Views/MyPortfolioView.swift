import SwiftUI

struct MyPortfolioView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 20) {
                    if let user = authManager.currentUser, let slug = user.portfolioSlug {
                        PortfolioDetailView(slug: slug)
                    } else {
                        Spacer()
                        EmptyStateView(
                            icon: "chart.pie",
                            title: "No Portfolio",
                            message: "Add stocks on the web to see your portfolio here."
                        )
                        Spacer()
                    }
                }
            }
            .navigationTitle("My Portfolio")
        }
        .navigationViewStyle(.stack)
    }
}

struct MyPortfolioView_Previews: PreviewProvider {
    static var previews: some View {
        MyPortfolioView()
            .environmentObject(AuthenticationManager())
            .environmentObject(SubscriptionManager())
    }
}
