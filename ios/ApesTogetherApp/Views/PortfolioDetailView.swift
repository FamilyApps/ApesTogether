import SwiftUI

struct PortfolioDetailView: View {
    let slug: String
    @StateObject private var viewModel = PortfolioDetailViewModel()
    @EnvironmentObject var subscriptionManager: SubscriptionManager
    
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                if viewModel.isLoading {
                    ProgressView()
                        .padding(.top, 100)
                } else if let portfolio = viewModel.portfolio {
                    // Header
                    VStack(spacing: 8) {
                        Text(portfolio.owner.username)
                            .font(.title.bold())
                        
                        HStack(spacing: 16) {
                            Label("\(portfolio.subscriberCount)", systemImage: "person.2.fill")
                            Text("$\(String(format: "%.2f", portfolio.subscriptionPrice))/mo")
                        }
                        .foregroundColor(.secondary)
                    }
                    .padding()
                    
                    Divider()
                    
                    // Holdings section
                    if let holdings = portfolio.holdings {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Holdings")
                                .font(.headline)
                                .padding(.horizontal)
                            
                            ForEach(holdings) { holding in
                                HoldingRow(holding: holding)
                            }
                        }
                        
                        Divider()
                        
                        // Recent trades
                        if let trades = portfolio.recentTrades, !trades.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Recent Trades")
                                    .font(.headline)
                                    .padding(.horizontal)
                                
                                ForEach(trades) { trade in
                                    TradeRow(trade: trade)
                                }
                            }
                        }
                    } else {
                        // Subscription prompt
                        VStack(spacing: 16) {
                            Image(systemName: "lock.fill")
                                .font(.system(size: 50))
                                .foregroundColor(.secondary)
                            
                            Text(portfolio.previewMessage ?? "Subscribe to view holdings")
                                .foregroundColor(.secondary)
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
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(Color.green)
                                .foregroundColor(.white)
                                .cornerRadius(12)
                            }
                            .padding(.horizontal, 40)
                            .disabled(subscriptionManager.isProcessing)
                        }
                        .padding(.vertical, 40)
                    }
                } else if let error = viewModel.error {
                    Text(error)
                        .foregroundColor(.secondary)
                        .padding()
                }
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadPortfolio(slug: slug)
        }
    }
}

struct HoldingRow: View {
    let holding: Holding
    
    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(holding.ticker)
                    .font(.headline)
                Text("\(Int(holding.quantity)) shares")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            VStack(alignment: .trailing) {
                Text("$\(String(format: "%.2f", holding.purchasePrice))")
                    .font(.subheadline)
                Text("avg cost")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }
}

struct TradeRow: View {
    let trade: Trade
    
    var body: some View {
        HStack {
            Circle()
                .fill(trade.type.lowercased() == "buy" ? Color.green : Color.red)
                .frame(width: 8, height: 8)
            
            VStack(alignment: .leading) {
                Text("\(trade.type.uppercased()) \(trade.ticker)")
                    .font(.subheadline.bold())
                Text(formatDate(trade.timestamp))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            VStack(alignment: .trailing) {
                Text("\(Int(trade.quantity)) @ $\(String(format: "%.2f", trade.price))")
                    .font(.subheadline)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 4)
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
