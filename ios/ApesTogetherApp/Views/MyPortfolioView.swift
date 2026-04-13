import SwiftUI
import Combine

struct MyPortfolioView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @State private var showAddStocks = false
    @State private var showSettings = false
    @State private var showShareSheet = false
    @State private var shareImage: UIImage?
    @StateObject private var shareViewModel = ShareDataViewModel()
    
    private var personalURL: String {
        if let slug = authManager.currentUser?.portfolioSlug {
            return "https://apestogether.ai/p/\(slug)?period=\(shareViewModel.selectedPeriod)"
        }
        return "https://apestogether.ai"
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // ── Custom header (no nav bar pill) ──
                    AppHeaderRow(showSettings: $showSettings)
                    
                    if let user = authManager.currentUser, let slug = user.portfolioSlug {
                        VStack(spacing: 0) {
                            PortfolioDetailView(slug: slug, onPeriodChanged: { period in
                                shareViewModel.selectedPeriod = period
                            })
                            
                            // Share button
                            Button {
                                generateAndShare(slug: slug)
                            } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: "square.and.arrow.up")
                                        .font(.system(size: 14))
                                    Text("Share Performance")
                                        .font(.subheadline.weight(.semibold))
                                }
                                .foregroundColor(.appBackground)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(Color.primaryAccent)
                                )
                            }
                            .padding(.horizontal, 16)
                            .padding(.bottom, 8)
                            
                            FeaturePollView()
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
                if let image = shareImage {
                    ShareSheet(items: [
                        image,
                        "Check out my portfolio on Apes Together! 🦍📈\n\(personalURL)" as Any
                    ])
                } else {
                    ShareSheet(items: [
                        "Check out my portfolio on Apes Together! 🦍📈\n\(personalURL)"
                    ])
                }
            }
            .onAppear {
                if let slug = authManager.currentUser?.portfolioSlug {
                    Task { await shareViewModel.loadData(slug: slug) }
                }
            }
        }
        .navigationViewStyle(.stack)
    }
    
    private func generateAndShare(slug: String) {
        guard let user = authManager.currentUser else {
            showShareSheet = true
            return
        }
        
        if #available(iOS 16.0, *) {
            shareImage = ShareCardGenerator.shared.generatePortfolioCard(
                username: user.username,
                portfolioReturn: shareViewModel.portfolioReturn,
                sp500Return: shareViewModel.sp500Return,
                chartData: shareViewModel.chartData,
                holdingsCount: shareViewModel.holdingsCount,
                subscriberCount: shareViewModel.subscriberCount,
                period: shareViewModel.selectedPeriod,
                slug: slug
            )
        }
        
        showShareSheet = true
    }
}

// MARK: - Share Data View Model

@MainActor
class ShareDataViewModel: ObservableObject {
    @Published var portfolioReturn: Double = 0
    @Published var sp500Return: Double = 0
    @Published var chartData: [ChartPoint] = []
    @Published var holdingsCount: Int = 0
    @Published var subscriberCount: Int = 0
    @Published var selectedPeriod: String = "1W"
    
    func loadData(slug: String) async {
        do {
            let portfolio = try await APIService.shared.getPortfolio(slug: slug)
            holdingsCount = portfolio.holdings?.count ?? 0
            subscriberCount = portfolio.subscriberCount
        } catch {}
        
        do {
            let chart = try await APIService.shared.getPortfolioChart(slug: slug, period: selectedPeriod)
            chartData = chart.chartData.enumerated().map { idx, point in
                var p = point
                p.index = idx
                return p
            }
            portfolioReturn = chart.portfolioReturn
            sp500Return = chart.sp500Return
        } catch {}
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

// MARK: - Share after Trade helper

struct PostTradeSharePrompt: View {
    let username: String
    let ticker: String
    let tradeType: String
    let quantity: Int
    let price: Double
    let slug: String
    let onDismiss: () -> Void
    
    @State private var showShareSheet = false
    @State private var shareImage: UIImage?
    
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 44))
                .foregroundColor(.primaryAccent)
            
            Text("Trade Executed!")
                .font(.title3.bold())
                .foregroundColor(.textPrimary)
            
            Text("\(tradeType.uppercased()) \(quantity) \(ticker) @ $\(String(format: "%.2f", price))")
                .font(.subheadline)
                .foregroundColor(.textSecondary)
            
            Button {
                if #available(iOS 16.0, *) {
                    shareImage = ShareCardGenerator.shared.generateTradeCard(
                        username: username,
                        ticker: ticker,
                        tradeType: tradeType,
                        quantity: quantity,
                        price: price,
                        slug: slug
                    )
                }
                showShareSheet = true
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "square.and.arrow.up")
                    Text("Share This Trade")
                }
            }
            .buttonStyle(PrimaryButtonStyle())
            .padding(.horizontal, 20)
            
            Button("Done") {
                onDismiss()
            }
            .font(.subheadline)
            .foregroundColor(.textSecondary)
        }
        .padding(24)
        .sheet(isPresented: $showShareSheet) {
            if let image = shareImage {
                ShareSheet(items: [image, "I just traded \(ticker) on Apes Together! \u{1F98D}" as Any])
            }
        }
    }
}
