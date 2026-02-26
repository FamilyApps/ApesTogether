import SwiftUI
import Combine

struct PortfolioDetailView: View {
    let slug: String
    @StateObject private var viewModel = PortfolioDetailViewModel()
    @EnvironmentObject var subscriptionManager: SubscriptionManager
    
    var body: some View {
        ZStack {
            Color.appBackground.ignoresSafeArea()
            
            ScrollView {
                VStack(spacing: 20) {
                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.primaryAccent)
                            .padding(.top, 100)
                    } else if let portfolio = viewModel.portfolio {
                        // Header card
                        VStack(spacing: 12) {
                            Text(portfolio.owner.username)
                                .font(.title.bold())
                                .foregroundColor(.textPrimary)
                            
                            HStack(spacing: 20) {
                                HStack(spacing: 6) {
                                    Image(systemName: "person.2.fill")
                                        .foregroundColor(.primaryAccent)
                                    Text("\(portfolio.subscriberCount)")
                                        .foregroundColor(.textSecondary)
                                }
                                
                                HStack(spacing: 4) {
                                    Text("$\(String(format: "%.2f", portfolio.subscriptionPrice))")
                                        .foregroundColor(.primaryAccent)
                                        .fontWeight(.semibold)
                                    Text("/mo")
                                        .foregroundColor(.textMuted)
                                }
                            }
                            .font(.subheadline)
                        }
                        .padding(.vertical, 24)
                        .frame(maxWidth: .infinity)
                        .background(
                            LinearGradient(
                                colors: [Color.primaryAccent.opacity(0.1), Color.appBackground],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        
                        // Holdings section
                        if let holdings = portfolio.holdings {
                            VStack(alignment: .leading, spacing: 12) {
                                SectionHeader(title: "Holdings")
                                    .padding(.horizontal)
                                
                                VStack(spacing: 0) {
                                    ForEach(Array(holdings.enumerated()), id: \.element.id) { index, holding in
                                        HoldingRow(holding: holding)
                                        if index < holdings.count - 1 {
                                            AccentDivider()
                                        }
                                    }
                                }
                                .cardStyle(padding: 0)
                                .padding(.horizontal)
                            }
                            
                            // Recent trades
                            if let trades = portfolio.recentTrades, !trades.isEmpty {
                                VStack(alignment: .leading, spacing: 12) {
                                    SectionHeader(title: "Recent Trades")
                                        .padding(.horizontal)
                                    
                                    VStack(spacing: 0) {
                                        ForEach(Array(trades.enumerated()), id: \.element.id) { index, trade in
                                            TradeRow(trade: trade)
                                            if index < trades.count - 1 {
                                                AccentDivider()
                                            }
                                        }
                                    }
                                    .cardStyle(padding: 0)
                                    .padding(.horizontal)
                                }
                            }
                        } else {
                            // Subscription prompt
                            VStack(spacing: 20) {
                                ZStack {
                                    Circle()
                                        .fill(Color.primaryAccent.opacity(0.1))
                                        .frame(width: 80, height: 80)
                                    
                                    Image(systemName: "lock.fill")
                                        .font(.system(size: 32))
                                        .foregroundColor(.primaryAccent)
                                }
                                
                                Text(portfolio.previewMessage ?? "Subscribe to view holdings")
                                    .foregroundColor(.textSecondary)
                                    .multilineTextAlignment(.center)
                                
                                Button {
                                    Task {
                                        await subscriptionManager.subscribe(to: portfolio.owner.id)
                                    }
                                } label: {
                                    HStack {
                                        Text("Subscribe")
                                        Text("$\(String(format: "%.2f", portfolio.subscriptionPrice))/mo")
                                            .fontWeight(.semibold)
                                    }
                                }
                                .buttonStyle(PrimaryButtonStyle(isDisabled: subscriptionManager.isProcessing))
                                .padding(.horizontal, 40)
                                .disabled(subscriptionManager.isProcessing)
                            }
                            .padding(.vertical, 40)
                        }
                    } else if let error = viewModel.error {
                        EmptyStateView(
                            icon: "exclamationmark.triangle",
                            title: "Error",
                            message: error
                        )
                        .padding(.top, 60)
                    }
                }
                .padding(.bottom, 20)
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            Task {
                await viewModel.loadPortfolio(slug: slug)
            }
        }
    }
}

struct HoldingRow: View {
    let holding: Holding
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(holding.ticker)
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                Text("\(Int(holding.quantity)) shares")
                    .font(.caption)
                    .foregroundColor(.textSecondary)
            }
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 4) {
                Text("$\(String(format: "%.2f", holding.purchasePrice))")
                    .font(.subheadline)
                    .foregroundColor(.textPrimary)
                Text("avg cost")
                    .font(.caption)
                    .foregroundColor(.textMuted)
            }
        }
        .padding()
    }
}

struct TradeRow: View {
    let trade: Trade
    
    private var isBuy: Bool {
        trade.type.lowercased() == "buy"
    }
    
    var body: some View {
        HStack(spacing: 12) {
            // Trade type indicator
            ZStack {
                Circle()
                    .fill((isBuy ? Color.gains : Color.losses).opacity(0.15))
                    .frame(width: 32, height: 32)
                
                Image(systemName: isBuy ? "arrow.down.left" : "arrow.up.right")
                    .font(.caption.weight(.bold))
                    .foregroundColor(isBuy ? .gains : .losses)
            }
            
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(trade.type.uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundColor(isBuy ? .gains : .losses)
                    Text(trade.ticker)
                        .font(.subheadline.bold())
                        .foregroundColor(.textPrimary)
                }
                Text(formatDate(trade.timestamp))
                    .font(.caption)
                    .foregroundColor(.textMuted)
            }
            
            Spacer()
            
            Text("\(Int(trade.quantity)) @ $\(String(format: "%.2f", trade.price))")
                .font(.subheadline)
                .foregroundColor(.textSecondary)
        }
        .padding()
    }
    
    private func formatDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: dateString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateStyle = .short
            displayFormatter.timeStyle = .short
            return displayFormatter.string(from: date)
        }
        return dateString
    }
}

@MainActor
class PortfolioDetailViewModel: ObservableObject {
    @Published var portfolio: PortfolioResponse?
    @Published var isLoading = false
    @Published var error: String?
    
    func loadPortfolio(slug: String) async {
        guard !slug.isEmpty else {
            error = "Invalid portfolio"
            return
        }
        
        isLoading = true
        error = nil
        
        do {
            portfolio = try await APIService.shared.getPortfolio(slug: slug)
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
}

struct PortfolioDetailView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationView {
            PortfolioDetailView(slug: "test")
                .environmentObject(SubscriptionManager())
        }
    }
}
