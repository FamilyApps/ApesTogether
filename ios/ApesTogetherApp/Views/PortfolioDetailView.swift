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
                        
                        // ── Hero Header ──
                        if !portfolio.isOwner {
                            PortfolioHeroCard(portfolio: portfolio)
                                .padding(.horizontal, 16)
                        }
                        
                        // ── Leaderboard Badges ──
                        if let badges = portfolio.leaderboardBadges, !badges.isEmpty {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 8) {
                                    ForEach(badges) { badge in
                                        LeaderboardBadgePill(badge: badge)
                                    }
                                }
                                .padding(.horizontal, 16)
                            }
                        }
                        
                        // ── Performance Chart Card ──
                        PerformanceChartView(
                            chartData: viewModel.chartData,
                            portfolioReturn: viewModel.portfolioReturn,
                            sp500Return: viewModel.sp500Return,
                            selectedPeriod: viewModel.selectedPeriod,
                            onPeriodChange: { period in
                                viewModel.selectedPeriod = period
                                Task { await viewModel.loadChart(slug: slug) }
                            },
                            portfolioLabel: portfolio.isOwner ? "Your Portfolio" : portfolio.owner.username,
                            leaderboardEligible: viewModel.leaderboardEligible,
                            daysActive: viewModel.daysActive,
                            daysRequired: viewModel.daysRequired,
                            eligibleDate: viewModel.eligibleDate
                        )
                        .padding(.horizontal, 16)
                        
                        // ── Stats Grid (non-owner view) ──
                        if !portfolio.isOwner {
                            PortfolioStatsGrid(portfolio: portfolio)
                                .padding(.horizontal, 16)
                        }
                        
                        // ── Sector Allocation ──
                        if let mix = portfolio.industryMix, !mix.isEmpty {
                            SectorAllocationCard(industryMix: mix)
                                .padding(.horizontal, 16)
                        }
                        
                        // ── Action Buttons (non-owner: Subscribe + Share) ──
                        if !portfolio.isOwner && !portfolio.isSubscribed {
                            HStack(spacing: 10) {
                                Button {
                                    Task { await subscriptionManager.subscribe(to: portfolio.owner.id) }
                                } label: {
                                    HStack(spacing: 6) {
                                        Image(systemName: "crown.fill")
                                            .font(.system(size: 13))
                                        Text("Try Free, then $\(String(format: "%.0f", portfolio.subscriptionPrice))/mo")
                                            .font(.system(size: 14, weight: .bold))
                                    }
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 13)
                                    .background(Color.primaryAccent)
                                    .foregroundColor(.white)
                                    .cornerRadius(12)
                                }
                                .disabled(subscriptionManager.isProcessing)
                                
                                ShareLink(
                                    item: URL(string: "https://apestogether.ai/p/\(portfolio.owner.portfolioSlug ?? slug)")!,
                                    subject: Text("\(portfolio.owner.username)'s Portfolio"),
                                    message: Text("Check out \(portfolio.owner.username)'s stock portfolio on ApesTogether!")
                                ) {
                                    HStack(spacing: 5) {
                                        Image(systemName: "square.and.arrow.up")
                                            .font(.system(size: 13))
                                        Text("Share")
                                            .font(.system(size: 14, weight: .semibold))
                                    }
                                    .foregroundColor(.textSecondary)
                                    .padding(.vertical, 13)
                                    .padding(.horizontal, 20)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12)
                                            .stroke(Color.white.opacity(0.08), lineWidth: 1)
                                    )
                                }
                            }
                            .padding(.horizontal, 16)
                        }
                        
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
                            // ── Blurred Holdings Teaser ──
                            BlurredHoldingsTeaser(
                                username: portfolio.owner.username,
                                subscriptionPrice: portfolio.subscriptionPrice,
                                onSubscribe: {
                                    Task { await subscriptionManager.subscribe(to: portfolio.owner.id) }
                                },
                                isProcessing: subscriptionManager.isProcessing
                            )
                            .padding(.horizontal, 16)
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
        .toolbar {
            if let portfolio = viewModel.portfolio, !portfolio.isOwner {
                ToolbarItem(placement: .navigationBarTrailing) {
                    ShareLink(
                        item: URL(string: "https://apestogether.ai/p/\(portfolio.owner.portfolioSlug ?? slug)")!,
                        subject: Text("\(portfolio.owner.username)'s Portfolio"),
                        message: Text("Check out \(portfolio.owner.username)'s portfolio on ApesTogether!")
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14))
                            .foregroundColor(.primaryAccent)
                    }
                }
            }
        }
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
                Text("$\(String(format: "%.2f", holding.totalValue))")
                    .font(.subheadline.bold())
                    .foregroundColor(.textPrimary)
                if let gain = holding.gainPercent {
                    Text(String(format: "%+.1f%%", gain))
                        .font(.caption.weight(.semibold))
                        .foregroundColor(gain >= 0 ? .gains : .losses)
                } else {
                    Text("$\(String(format: "%.2f", holding.displayPrice)) avg")
                        .font(.caption)
                        .foregroundColor(.textMuted)
                }
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
    @Published var selectedPeriod: String = "1W"
    @Published var isLoadingChart = false
    
    // Leaderboard eligibility
    @Published var leaderboardEligible: Bool = true
    @Published var daysActive: Int = 0
    @Published var daysRequired: Int = 0
    @Published var eligibleDate: String?
    
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
            chartData = response.chartData.enumerated().map { idx, point in
                var p = point
                p.index = idx
                return p
            }
            portfolioReturn = response.portfolioReturn
            sp500Return = response.sp500Return
            
            // Update leaderboard eligibility
            leaderboardEligible = response.leaderboardEligible ?? true
            daysActive = response.daysActive ?? 0
            daysRequired = response.daysRequired ?? 0
            eligibleDate = response.eligibleDate
        } catch {
            // Chart errors are non-fatal, just show empty chart
            chartData = []
            portfolioReturn = 0
            sp500Return = 0
            leaderboardEligible = true
        }
        
        isLoadingChart = false
    }
}

// MARK: - Leaderboard Badge Pill

struct LeaderboardBadgePill: View {
    let badge: LeaderboardBadge
    
    private var icon: String {
        switch badge.rank {
        case 1: return "🥇"
        case 2: return "🥈"
        case 3: return "🥉"
        default: return "🏆"
        }
    }
    
    private var label: String {
        if badge.type == "sector", let sector = badge.sector {
            return "#\(badge.rank) \(sector) (\(badge.period))"
        }
        return "#\(badge.rank) Overall (\(badge.period))"
    }
    
    private var pillColor: Color {
        switch badge.rank {
        case 1: return Color(hex: "FFD700")
        case 2: return Color(hex: "C0C0C0")
        case 3: return Color(hex: "CD7F32")
        default: return Color.primaryAccent
        }
    }
    
    var body: some View {
        HStack(spacing: 4) {
            Text(icon).font(.system(size: 12))
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.textPrimary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(pillColor.opacity(0.15))
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(pillColor.opacity(0.4), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 20))
    }
}

// MARK: - Portfolio Hero Card

struct PortfolioHeroCard: View {
    let portfolio: PortfolioResponse
    
    private var accountAgeText: String {
        let days = portfolio.accountAgeDays ?? 0
        if days >= 365 {
            let years = days / 365
            let months = (days % 365) / 30
            return "\(years)y \(months)m"
        } else if days >= 30 {
            return "\(days / 30) month\(days / 30 > 1 ? "s" : "")"
        } else {
            return "\(days) day\(days != 1 ? "s" : "")"
        }
    }
    
    var body: some View {
        VStack(spacing: 8) {
            // Avatar
            ZStack {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [Color.primaryAccent, Color(hex: "059669")],
                            startPoint: .topLeading, endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 56, height: 56)
                    .shadow(color: Color.primaryAccent.opacity(0.3), radius: 12)
                
                Text(String(portfolio.owner.username.prefix(1)).uppercased())
                    .font(.system(size: 22, weight: .bold, design: .rounded))
                    .foregroundColor(.white)
            }
            
            Text(portfolio.owner.username)
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(.textPrimary)
            
            HStack(spacing: 4) {
                Text("Member for \(accountAgeText)")
                Text("·")
                Text("\(portfolio.subscriberCount) subscriber\(portfolio.subscriberCount != 1 ? "s" : "")")
            }
            .font(.system(size: 12))
            .foregroundColor(.textSecondary)
            
            // Portfolio value
            if let value = portfolio.portfolioValue, value > 0 {
                Text("$\(formatLargeNumber(value))")
                    .font(.system(size: 28, weight: .heavy, design: .rounded))
                    .foregroundColor(.textPrimary)
                    .padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .cardStyle()
    }
    
    private func formatLargeNumber(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 2
        formatter.minimumFractionDigits = 2
        return formatter.string(from: NSNumber(value: value)) ?? String(format: "%.2f", value)
    }
}

// MARK: - Portfolio Stats Grid

struct PortfolioStatsGrid: View {
    let portfolio: PortfolioResponse
    
    var body: some View {
        HStack(spacing: 1) {
            StatCell(value: "\(portfolio.numStocks ?? 0)", label: "Stocks")
            StatCell(value: String(format: "%.1f", portfolio.avgTradesPerWeek ?? 0), label: "Trades/Wk")
            StatCell(value: String(format: "%.0f%%", portfolio.largeCapPct ?? 0), label: "Large Cap")
        }
        .background(Color.white.opacity(0.06))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.06), lineWidth: 1)
        )
    }
}

private struct StatCell: View {
    let value: String
    let label: String
    
    var body: some View {
        VStack(spacing: 3) {
            Text(value)
                .font(.system(size: 18, weight: .bold, design: .rounded))
                .foregroundColor(.textPrimary)
            Text(label)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.textMuted)
                .textCase(.uppercase)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(Color.cardBackground)
    }
}

// MARK: - Sector Allocation Card

struct SectorAllocationCard: View {
    let industryMix: [String: Double]
    
    private let barColors: [Color] = [
        Color(hex: "10b981"), Color(hex: "3b82f6"), Color(hex: "f59e0b"),
        Color(hex: "ef4444"), Color(hex: "8b5cf6"), Color(hex: "ec4899"),
        Color(hex: "06b6d4"), Color(hex: "f97316"), Color(hex: "14b8a6"),
        Color(hex: "a855f7"), Color(hex: "6366f1")
    ]
    
    private var sortedSectors: [(String, Double)] {
        industryMix.sorted { $0.value > $1.value }.filter { $0.value >= 1.0 }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Sector Allocation")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.textPrimary)
            
            ForEach(Array(sortedSectors.enumerated()), id: \.element.0) { index, sector in
                HStack(spacing: 10) {
                    Text(sector.0)
                        .font(.system(size: 12))
                        .foregroundColor(.textSecondary)
                        .frame(width: 90, alignment: .leading)
                        .lineLimit(1)
                    
                    GeometryReader { geo in
                        RoundedRectangle(cornerRadius: 4)
                            .fill(barColors[index % barColors.count])
                            .frame(width: geo.size.width * CGFloat(sector.1 / 100.0))
                    }
                    .frame(height: 8)
                    
                    Text(String(format: "%.1f%%", sector.1))
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.textPrimary)
                        .frame(width: 42, alignment: .trailing)
                }
            }
        }
        .padding(16)
        .cardStyle()
    }
}

// MARK: - Blurred Holdings Teaser

struct BlurredHoldingsTeaser: View {
    let username: String
    let subscriptionPrice: Double
    let onSubscribe: () -> Void
    let isProcessing: Bool
    
    private let fakeHoldings: [(String, String, String, Bool)] = [
        ("AAPL", "$8,329", "+13.6%", true),
        ("NVDA", "$9,193", "+27.1%", true),
        ("TSLA", "$6,303", "-9.2%", false),
        ("AMZN", "$3,729", "+31.0%", true),
        ("MSFT", "$7,426", "+22.0%", true),
    ]
    
    var body: some View {
        ZStack {
            // Blurred fake holdings
            VStack(spacing: 0) {
                HStack {
                    Text("Holdings")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.textPrimary)
                    Spacer()
                }
                .padding(.horizontal, 14)
                .padding(.top, 14)
                .padding(.bottom, 10)
                
                ForEach(fakeHoldings, id: \.0) { ticker, value, gain, isPositive in
                    HStack {
                        ZStack {
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color.primaryAccent.opacity(0.1))
                                .frame(width: 36, height: 36)
                            Text(String(ticker.prefix(2)))
                                .font(.system(size: 12, weight: .bold))
                                .foregroundColor(.primaryAccent)
                        }
                        
                        VStack(alignment: .leading, spacing: 2) {
                            Text(ticker)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(.textPrimary)
                            Text("42 shares")
                                .font(.system(size: 11))
                                .foregroundColor(.textMuted)
                        }
                        .padding(.leading, 4)
                        
                        Spacer()
                        
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(value)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(.textPrimary)
                            Text(gain)
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(isPositive ? .gains : .losses)
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    
                    if ticker != fakeHoldings.last?.0 {
                        Divider().background(Color.white.opacity(0.06))
                    }
                }
            }
            .blur(radius: 6)
            .opacity(0.4)
            
            // Overlay CTA
            VStack(spacing: 16) {
                ZStack {
                    Circle()
                        .fill(Color.primaryAccent.opacity(0.15))
                        .frame(width: 56, height: 56)
                    Image(systemName: "bell.badge.fill")
                        .font(.system(size: 24))
                        .foregroundColor(.primaryAccent)
                }
                
                Text("See every trade, instantly")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(.textPrimary)
                
                // Benefits list
                VStack(alignment: .leading, spacing: 6) {
                    benefitRow("Real-time buy & sell alerts")
                    benefitRow("Full position details & history")
                    benefitRow("Exact holdings breakdown")
                }
                .frame(maxWidth: 240)
                
                // Trial timeline
                VStack(spacing: 4) {
                    HStack(spacing: 0) {
                        VStack(spacing: 2) {
                            Circle().fill(Color.primaryAccent).frame(width: 8, height: 8)
                            Text("Today").font(.system(size: 10, weight: .semibold)).foregroundColor(.primaryAccent)
                            Text("Free").font(.system(size: 9)).foregroundColor(.textSecondary)
                        }
                        Rectangle().fill(Color.primaryAccent.opacity(0.3)).frame(height: 2)
                        VStack(spacing: 2) {
                            Circle().fill(Color.textSecondary.opacity(0.5)).frame(width: 8, height: 8)
                            Text("Day 30").font(.system(size: 10, weight: .semibold)).foregroundColor(.textSecondary)
                            Text("$\(String(format: "%.0f", subscriptionPrice))/mo").font(.system(size: 9)).foregroundColor(.textSecondary)
                        }
                    }
                    .frame(maxWidth: 200)
                    
                    Text("Cancel anytime — we'll remind you before the trial ends")
                        .font(.system(size: 10))
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                        .padding(.top, 4)
                }
                .padding(.vertical, 8)
                
                // CTA button
                Button(action: onSubscribe) {
                    HStack(spacing: 6) {
                        Image(systemName: "crown.fill")
                            .font(.system(size: 13))
                        Text("Start Free Trial")
                            .font(.system(size: 16, weight: .bold))
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Color.primaryAccent)
                    .cornerRadius(12)
                }
                .disabled(isProcessing)
                .padding(.horizontal, 16)
                
                // Price disclosure (Apple requirement: most prominent)
                Text("1 month free, then $\(String(format: "%.0f", subscriptionPrice))/month")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.textSecondary)
                
                // Legal links
                HStack(spacing: 12) {
                    Link("Terms of Use", destination: URL(string: "https://apestogether.ai/terms-of-service")!)
                    Text("·").foregroundColor(.textSecondary)
                    Link("Privacy Policy", destination: URL(string: "https://apestogether.ai/privacy-policy")!)
                }
                .font(.system(size: 10))
                .foregroundColor(.textSecondary)
            }
            .padding(.vertical, 20)
        }
        .cardStyle()
    }
    
    private func benefitRow(_ text: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 14))
                .foregroundColor(.primaryAccent)
            Text(text)
                .font(.system(size: 13))
                .foregroundColor(.textPrimary)
        }
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
