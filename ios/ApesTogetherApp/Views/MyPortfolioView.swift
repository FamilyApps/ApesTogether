import SwiftUI

struct MyPortfolioView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    
    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                if let user = authManager.currentUser, let slug = user.portfolioSlug {
                    PortfolioDetailView(slug: slug)
                } else {
                    VStack(spacing: 16) {
                        Image(systemName: "chart.pie")
                            .font(.system(size: 50))
                            .foregroundColor(.secondary)
                        Text("No Portfolio")
                            .font(.title2.bold())
                        Text("Add stocks on the web to see your portfolio here.")
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()
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
