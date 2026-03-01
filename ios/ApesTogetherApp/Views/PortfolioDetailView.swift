import SwiftUI
import Combine
import Charts

struct PortfolioDetailView: View {
    let slug: String
    @StateObject private var viewModel = PortfolioDetailViewModel()
    @EnvironmentObject var subscriptionManager: SubscriptionManager
    @State private var tradeSheet: TradeSheetInfo?
    @State private var showBuySheet = false
    @State private var showAddStocks = false
    
    struct TradeSheetInfo: Identifiable {
        let id = UUID()
        let ticker: String
        let type: TradeSheetView.TradeType
        let currentQuantity: Double
    }
    
    var body: some View {
        ZStack {
            Color.appBackground.ignoresSafeArea()
            
            ScrollView {
                VStack(spacing: 16) {
                    if viewModel.isLoading && viewModel.portfolio == nil {
                        ProgressView()
                            .tint(.primaryAccent)
                            .padding(.top, 100)
                    } else if let portfolio = viewModel.portfolio {
                        
                        // ── Performance Chart Card ──
                        PerformanceChartView(
                            chartData: viewModel.chartData,
                            portfolioReturn: viewModel.portfolioReturn,
                            sp500Return: viewModel.sp500Return,
                            selectedPeriod: viewModel.selectedPeriod,
                            onPeriodChange: { period in
                                viewModel.selectedPeriod = period
                                Task { await viewModel.loadChart(slug: slug) }
                            }
                        )
                        .padding(.horizontal, 16)
                        
                        // ── Buy / Sell Buttons ──
                        if portfolio.isOwner {
                            HStack(spacing: 12) {
                                Button {
                                    showAddStocks = true
                                } label: {
                                    HStack(spacing: 6) {
                                        Image(systemName: "plus.circle.fill")
                                            .font(.system(size: 16))
                                        Text("Buy")
                                            .fontWeight(.bold)
                                    }
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 14)
                                    .background(Color.gains)
                                    .foregroundColor(.white)
                                    .cornerRadius(12)
                                }
                                
                                Button {
                                    showBuySheet = true
                                } label: {
                                    HStack(spacing: 6) {
                                        Image(systemName: "minus.circle.fill")
                                            .font(.system(size: 16))
                                        Text("Sell")
                                            .fontWeight(.bold)
                                    }
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 14)
                                    .background(Color.losses.opacity(0.15))
                                    .foregroundColor(.losses)
                                    .cornerRadius(12)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12)
                                            .stroke(Color.losses.opacity(0.3), lineWidth: 1)
                                    )
                                }
                            }
                            .padding(.horizontal, 16)
                        }
                        
                        // ── Holdings Section ──
                        if let holdings = portfolio.holdings, !holdings.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack {
                                    SectionHeader(title: "Holdings")
                                    Spacer()
                                    Text("\(holdings.count) stocks")
                                        .font(.caption)
                                        .foregroundColor(.textMuted)
                                }
                                .padding(.horizontal, 16)
                                
                                if portfolio.isOwner {
                                    // Swipe hint
                                    HStack(spacing: 4) {
                                        Image(systemName: "hand.draw")
                                            .font(.system(size: 10))
                                        Text("Swipe right to buy, left to sell")
                                            .font(.system(size: 10))
                                    }
                                    .foregroundColor(.textMuted)
                                    .padding(.horizontal, 16)
                                }
                                
                                VStack(spacing: 0) {
                                    ForEach(Array(holdings.enumerated()), id: \.element.id) { index, holding in
                                        if portfolio.isOwner {
                                            SwipeableHoldingRow(
                                                holding: holding,
                                                onBuy: {
                                                    tradeSheet = TradeSheetInfo(
                                                        ticker: holding.ticker,
                                                        type: .buy,
                                                        currentQuantity: holding.quantity
                                                    )
                                                },
                                                onSell: {
                                                    tradeSheet = TradeSheetInfo(
                                                        ticker: holding.ticker,
                                                        type: .sell,
                                                        currentQuantity: holding.quantity
                                                    )
                                                }
                                            )
                                        } else {
                                            HoldingRow(holding: holding)
                                        }
                                        if index < holdings.count - 1 {
                                            AccentDivider()
                                        }
                                    }
                                }
                                .cardStyle(padding: 0)
                                .padding(.horizontal, 16)
                            }
                            
                            // ── Recent Trades ──
                            if let trades = portfolio.recentTrades, !trades.isEmpty {
                                VStack(alignment: .leading, spacing: 10) {
                                    SectionHeader(title: "Recent Trades")
                                        .padding(.horizontal, 16)
                                    
                                    VStack(spacing: 0) {
                                        ForEach(Array(trades.prefix(5).enumerated()), id: \.element.id) { index, trade in
                                            TradeRow(trade: trade)
                                            if index < min(trades.count, 5) - 1 {
                                                AccentDivider()
                                            }
                                        }
                                    }
                                    .cardStyle(padding: 0)
                                    .padding(.horizontal, 16)
                                }
                            }
                        } else if portfolio.holdings == nil {
                            // Subscription prompt for non-owners
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
                        } else {
                            // Owner with no holdings
                            VStack(spacing: 16) {
                                EmptyStateView(
                                    icon: "chart.line.uptrend.xyaxis",
                                    title: "No Holdings Yet",
                                    message: "Add your first stocks to start tracking performance"
                                )
                                Button {
                                    showAddStocks = true
                                } label: {
                                    Text("Add Your Stocks")
                                }
                                .buttonStyle(PrimaryButtonStyle())
                                .padding(.horizontal, 40)
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
                await viewModel.loadChart(slug: slug)
            }
        }
        .sheet(item: $tradeSheet) { info in
            TradeSheetView(
                ticker: info.ticker,
                tradeType: info.type,
                currentQuantity: info.currentQuantity,
                onComplete: {
                    Task {
                        await viewModel.loadPortfolio(slug: slug)
                        await viewModel.loadChart(slug: slug)
                    }
                }
            )
            .presentationDetents([.medium])
        }
        .sheet(isPresented: $showAddStocks) {
            AddStocksView(
                headline: "Buy Stocks",
                subheadline: "Add new positions to your portfolio",
                showSkip: false,
                onComplete: {
                    showAddStocks = false
                    Task {
                        await viewModel.loadPortfolio(slug: slug)
                        await viewModel.loadChart(slug: slug)
                    }
                }
            )
        }
        .sheet(isPresented: $showBuySheet) {
            SellPickerSheet(
                holdings: viewModel.portfolio?.holdings ?? [],
                onSelect: { holding in
                    showBuySheet = false
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        tradeSheet = TradeSheetInfo(
                            ticker: holding.ticker,
                            type: .sell,
                            currentQuantity: holding.quantity
                        )
                    }
                }
            )
            .presentationDetents([.medium])
        }
    }
}

// MARK: - Swipeable Holding Row (Robinhood-style)

struct SwipeableHoldingRow: View {
    let holding: Holding
    let onBuy: () -> Void
    let onSell: () -> Void
    @State private var offset: CGFloat = 0
    @State private var showingAction: SwipeAction = .none
    
    enum SwipeAction {
        case none, buy, sell
    }
    
    private let swipeThreshold: CGFloat = 80
    
    var body: some View {
        ZStack {
            // Background actions
            HStack(spacing: 0) {
                // Buy (swipe right reveals green)
                HStack {
                    VStack(spacing: 4) {
                        Image(systemName: "plus.circle.fill")
                            .font(.system(size: 20))
                        Text("Buy")
                            .font(.caption.weight(.bold))
                    }
                    .foregroundColor(.white)
                    .frame(width: swipeThreshold)
                    Spacer()
                }
                .background(Color.gains)
                
                Spacer()
                
                // Sell (swipe left reveals red)
                HStack {
                    Spacer()
                    VStack(spacing: 4) {
                        Image(systemName: "minus.circle.fill")
                            .font(.system(size: 20))
                        Text("Sell")
                            .font(.caption.weight(.bold))
                    }
                    .foregroundColor(.white)
                    .frame(width: swipeThreshold)
                }
                .background(Color.losses)
            }
            
            // Foreground content
            HoldingRow(holding: holding)
                .background(Color.cardBackground)
                .offset(x: offset)
                .gesture(
                    DragGesture()
                        .onChanged { value in
                            offset = value.translation.width
                            if offset > swipeThreshold {
                                showingAction = .buy
                            } else if offset < -swipeThreshold {
                                showingAction = .sell
                            } else {
                                showingAction = .none
                            }
                        }
                        .onEnded { value in
                            withAnimation(.spring(response: 0.3)) {
                                if showingAction == .buy {
                                    onBuy()
                                } else if showingAction == .sell {
                                    onSell()
                                }
                                offset = 0
                                showingAction = .none
                            }
                        }
                )
        }
        .clipped()
    }
}

// MARK: - Sell Picker Sheet

struct SellPickerSheet: View {
    let holdings: [Holding]
    let onSelect: (Holding) -> Void
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(holdings) { holding in
                            Button {
                                onSelect(holding)
                            } label: {
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
                                    Image(systemName: "chevron.right")
                                        .foregroundColor(.textMuted)
                                        .font(.caption)
                                }
                                .padding()
                            }
                            AccentDivider()
                        }
                    }
                    .cardStyle(padding: 0)
                    .padding(.horizontal, 16)
                    .padding(.top, 16)
                }
            }
            .navigationTitle("Choose Stock to Sell")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textMuted)
                    }
                }
            }
        }
    }
}

// MARK: - Holding Row

struct HoldingRow: View {
    let holding: Holding
    
    var body: some View {
        HStack {
            // Ticker badge
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.primaryAccent.opacity(0.1))
                    .frame(width: 44, height: 44)
                Text(String(holding.ticker.prefix(2)))
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundColor(.primaryAccent)
            }
            
            VStack(alignment: .leading, spacing: 4) {
                Text(holding.ticker)
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                Text("\(Int(holding.quantity)) shares")
                    .font(.caption)
                    .foregroundColor(.textSecondary)
            }
            .padding(.leading, 4)
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 4) {
                Text("$\(String(format: "%.2f", holding.purchasePrice * holding.quantity))")
                    .font(.subheadline.bold())
                    .foregroundColor(.textPrimary)
                Text("$\(String(format: "%.2f", holding.purchasePrice)) avg")
                    .font(.caption)
                    .foregroundColor(.textMuted)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}

// MARK: - Trade Row

struct TradeRow: View {
    let trade: Trade
    
    private var isBuy: Bool {
        trade.type.lowercased() == "buy"
    }
    
    var body: some View {
        HStack(spacing: 12) {
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
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
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

// MARK: - View Model

@MainActor
class PortfolioDetailViewModel: ObservableObject {
    @Published var portfolio: PortfolioResponse?
    @Published var isLoading = false
    @Published var error: String?
    
    // Chart data
    @Published var chartData: [ChartPoint] = []
    @Published var portfolioReturn: Double = 0
    @Published var sp500Return: Double = 0
    @Published var selectedPeriod: String = "7D"
    @Published var isLoadingChart = false
    
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
    
    func loadChart(slug: String) async {
        guard !slug.isEmpty else { return }
        
        isLoadingChart = true
        
        do {
            let response = try await APIService.shared.getPortfolioChart(slug: slug, period: selectedPeriod)
            chartData = response.chartData
            portfolioReturn = response.portfolioReturn
            sp500Return = response.sp500Return
        } catch {
            // Chart errors are non-fatal, just show empty chart
            chartData = []
            portfolioReturn = 0
            sp500Return = 0
        }
        
        isLoadingChart = false
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
