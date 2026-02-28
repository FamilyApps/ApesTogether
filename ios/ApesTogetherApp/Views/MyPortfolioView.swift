import SwiftUI

struct MyPortfolioView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @State private var showAddStocks = false
    @State private var showSettings = false
    @State private var showShareSheet = false
    
    private var personalURL: String {
        if let slug = authManager.currentUser?.portfolioSlug {
            return "https://apestogether.ai/p/\(slug)"
        }
        return "https://apestogether.ai"
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 20) {
                    if let user = authManager.currentUser, let slug = user.portfolioSlug {
                        VStack(spacing: 0) {
                            PortfolioDetailView(slug: slug)
                            
                            // Share portfolio button
                            Button {
                                showShareSheet = true
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: "square.and.arrow.up")
                                    Text("Share Portfolio")
                                }
                                .font(.subheadline.weight(.semibold))
                                .foregroundColor(.primaryAccent)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .stroke(Color.primaryAccent.opacity(0.4), lineWidth: 1)
                                )
                            }
                            .padding(.horizontal, 16)
                            .padding(.bottom, 8)
                        }
                    } else {
                        Spacer()
                        
                        VStack(spacing: 24) {
                            EmptyStateView(
                                icon: "dollarsign.circle",
                                title: "Start Earning",
                                message: "Add your stocks to join the leaderboard and earn from every subscriber who follows your trades."
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
            .appNavBar(showSettings: $showSettings)
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
            .sheet(isPresented: $showAddStocks) {
                AddStocksView(
                    headline: "Add Your Stocks",
                    subheadline: "Share your trades and earn from every subscriber",
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
            .sheet(isPresented: $showShareSheet) {
                ShareSheet(items: [
                    "Check out my portfolio on Apes Together! 🦍📈\n\(personalURL)"
                ])
            }
        }
        .navigationViewStyle(.stack)
    }
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

struct MyPortfolioView_Previews: PreviewProvider {
    static var previews: some View {
        MyPortfolioView()
            .environmentObject(AuthenticationManager())
            .environmentObject(SubscriptionManager())
    }
}
