import SwiftUI

struct MyPortfolioView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @State private var showAddStocks = false
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 20) {
                    if let user = authManager.currentUser, let slug = user.portfolioSlug {
                        PortfolioDetailView(slug: slug)
                    } else {
                        Spacer()
                        
                        VStack(spacing: 24) {
                            EmptyStateView(
                                icon: "dollarsign.circle",
                                title: "Start Earning",
                                message: "Add your stocks to join the leaderboard and earn $5.40/month per subscriber who follows your trades."
                            )
                            
                            Button {
                                showAddStocks = true
                            } label: {
                                Text("Add Your Stocks")
                            }
                            .buttonStyle(PrimaryButtonStyle())
                            .padding(.horizontal, 40)
                        }
                        
                        Spacer()
                    }
                }
            }
            .navigationTitle("My Portfolio")
            .sheet(isPresented: $showAddStocks) {
                AddStocksView(
                    headline: "Add Your Stocks",
                    subheadline: "Share your trades and earn $5.40/month per subscriber",
                    showSkip: false,
                    onComplete: {
                        showAddStocks = false
                        Task {
                            await authManager.refreshUserData()
                        }
                    }
                )
                .environmentObject(authManager)
            }
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
