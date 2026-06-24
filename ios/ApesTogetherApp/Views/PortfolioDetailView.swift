import SwiftUI
import Combine
import Charts

struct PortfolioDetailView: View {
    let slug: String
    var initialPeriod: String? = nil
    var onPeriodChanged: ((String) -> Void)? = nil
    @StateObject private var viewModel = PortfolioDetailViewModel()
    @EnvironmentObject var subscriptionManager: SubscriptionManager
    @Environment(\.scenePhase) private var scenePhase
    @State private var tradeSheet: TradeSheetInfo?
    @State private var showBuySheet = false
    @State private var showAddStocks = false

    // ── Phase D: portfolio resizer state ────────────────────────────────
    // The scale sheet is presented when the subscriber taps "Set Investment
    // Size" on a subscribed portfolio. `scaleAmountInput` is a dollar
    // string (the TextField binds to it directly) — sanitized to Double
    // only at submit time so the user can type freely.
    @State private var showScaleSheet = false
    @State private var scaleAmountInput: String = ""
    @State private var scaleIsSaving = false
    @State private var scaleError: String?
    
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
                                onPeriodChanged?(period)
                                Task { await viewModel.loadChart(slug: slug) }
                            },
                            portfolioLabel: portfolio.isOwner ? "Your Portfolio" : portfolio.owner.publicName,
                            leaderboardEligible: viewModel.leaderboardEligible,
                            daysActive: viewModel.daysActive,
                            daysRequired: viewModel.daysRequired,
                            eligibleDate: viewModel.eligibleDate
                        )
                        .padding(.horizontal, 16)
                        
                        // ── Action Buttons (non-owner: Subscribe + Share) ──
                        // Placed immediately under the chart so the conversion
                        // CTA is visible above the fold without scrolling past
                        // the stats grid + sector allocation.
                        if !portfolio.isOwner && !portfolio.isSubscribed {
                            VStack(spacing: 10) {
                                // W7: when the creator isn't accepting new
                                // subscribers, swap the plan toggle + Subscribe
                                // CTA for explanatory copy (Share stays). The
                                // purchase is blocked server-side regardless.
                                if portfolio.acceptsNewSubscribers == false {
                                    Text("This trader isn't accepting new subscribers right now.")
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundColor(.textMuted)
                                        .multilineTextAlignment(.center)
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 8)
                                } else {
                                    // Compact plan toggle
                                    CompactPlanToggle(subscriptionManager: subscriptionManager)
                                }
                                
                                HStack(spacing: 10) {
                                    if portfolio.acceptsNewSubscribers != false {
                                    Button {
                                        Task {
                        await subscriptionManager.subscribe(
                            to: portfolio.owner.id,
                            username: portfolio.owner.publicName,
                            slug: portfolio.owner.portfolioSlug
                        )
                    }
                                    } label: {
                                        HStack(spacing: 6) {
                                            Image(systemName: "crown.fill")
                                                .font(.system(size: 13))
                                            Text(subscriptionManager.selectedPlan == .annual
                                                 ? "Try Free for 7 Days, then $69/yr"
                                                 : "Try Free for 7 Days, then $\(String(format: "%.0f", portfolio.subscriptionPrice))/mo")
                                                .font(.system(size: 14, weight: .bold))
                                        }
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 13)
                                        .background(Color.primaryAccent)
                                        .foregroundColor(.white)
                                        .cornerRadius(12)
                                    }
                                    .disabled(subscriptionManager.isProcessing)
                                    }
                                    
                                    ShareLink(
                                        item: URL(string: "https://apestogether.ai/p/\(portfolio.owner.portfolioSlug ?? slug)?period=\(viewModel.selectedPeriod)")!,
                                        subject: Text("\(portfolio.owner.publicName)'s Portfolio"),
                                        message: Text("Check out \(portfolio.owner.publicName)'s stock portfolio on ApesTogether!")
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
                            }
                            .padding(.horizontal, 16)
                        }
                        
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
                        
                        // ── Phase D: Portfolio Resizer Card (subscriber-only) ──
                        // Renders one of two states:
                        //   • No scale set yet → "Adjust Portfolio Size" CTA
                        //   • Scale active     → badge with current $ + Edit/Clear
                        // Hidden for the portfolio owner viewing their own page
                        // and for non-subscribers (where the holdings are blurred
                        // anyway).
                        if portfolio.isSubscribed && !portfolio.isOwner,
                           let subscriptionId = portfolio.subscriptionId {
                            ScaleCard(
                                scale: portfolio.scale,
                                onTapEdit: {
                                    scaleAmountInput = portfolio.scale
                                        .map { String(format: "%.0f", $0.targetDollars) } ?? ""
                                    scaleError = nil
                                    showScaleSheet = true
                                },
                                onTapClear: {
                                    Task { await viewModel.clearScale(slug: slug, subscriptionId: subscriptionId) }
                                }
                            )
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
                                                portfolioValue: portfolio.portfolioValue,
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
                                            HoldingRow(holding: holding, portfolioValue: portfolio.portfolioValue)
                                        }
                                        if index < holdings.count - 1 {
                                            AccentDivider()
                                        }
                                    }
                                    // Cash line (only when there's actual cash on hand).
                                    if let cash = portfolio.cashBalance, cash > 0.005 {
                                        AccentDivider()
                                        CashRow(cashBalance: cash, portfolioValue: portfolio.portfolioValue)
                                    }
                                }
                                .cardStyle(padding: 0)
                                .padding(.horizontal, 16)

                                // ── Phase D: below-1-share footnote ──
                                // Appears only in floor mode (prefer_fractional=false)
                                // when scaling produces sub-1-share positions that
                                // get dropped from the visible holdings list.
                                if let count = portfolio.belowOneShareCount, count > 0 {
                                    HStack(spacing: 6) {
                                        Image(systemName: "info.circle")
                                            .font(.system(size: 11))
                                        Text("\(count) position\(count == 1 ? "" : "s") below 1 share at this scale — enable Show Fractional Shares in Settings to see them.")
                                            .font(.system(size: 11))
                                    }
                                    .foregroundColor(.textMuted)
                                    .padding(.horizontal, 16)
                                }
                            }
                            
                            // ── Recent Trades ──
                            if let trades = portfolio.recentTrades, !trades.isEmpty {
                                VStack(alignment: .leading, spacing: 10) {
                                    SectionHeader(title: "Recent Trades")
                                        .padding(.horizontal, 16)
                                    
                                    VStack(spacing: 0) {
                                        ForEach(Array(trades.prefix(15).enumerated()), id: \.element.id) { index, trade in
                                            TradeRow(trade: trade)
                                            if index < min(trades.count, 15) - 1 {
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
                                username: portfolio.owner.publicName,
                                subscriptionManager: subscriptionManager,
                                onSubscribe: {
                                    Task {
                        await subscriptionManager.subscribe(
                            to: portfolio.owner.id,
                            username: portfolio.owner.publicName,
                            slug: portfolio.owner.portfolioSlug
                        )
                    }
                                }
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
                        item: URL(string: "https://apestogether.ai/p/\(portfolio.owner.portfolioSlug ?? slug)?period=\(viewModel.selectedPeriod)")!,
                        subject: Text("\(portfolio.owner.publicName)'s Portfolio"),
                        message: Text("Check out \(portfolio.owner.publicName)'s portfolio on ApesTogether!")
                    ) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.system(size: 14))
                            .foregroundColor(.primaryAccent)
                    }
                }
            }
        }
        .onAppear {
            if let period = initialPeriod {
                viewModel.selectedPeriod = period
            }
            Task {
                await viewModel.loadPortfolio(slug: slug)
                await viewModel.loadChart(slug: slug)
            }
        }
        .refreshable {
            // Pull-to-refresh. Holdings are scaled server-side from the
            // creator's CURRENT positions, so a reload reflects a rebalance.
            await viewModel.loadPortfolio(slug: slug)
            await viewModel.loadChart(slug: slug)
        }
        .onChange(of: scenePhase) { newPhase in
            // Reopening from the background (e.g. after a trade-alert push)
            // doesn't fire onAppear, so reload here too. loadPortfolio keeps
            // the existing holdings on screen while fetching (the spinner only
            // shows when there's no portfolio yet), so there's no flash.
            if newPhase == .active {
                Task {
                    await viewModel.loadPortfolio(slug: slug)
                    await viewModel.loadChart(slug: slug)
                }
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
            .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $showAddStocks) {
            AddStocksView(
                headline: "Buy Stocks",
                subheadline: "Add new positions to your portfolio",
                showSkip: false,
                submitLabel: "Buy",
                submitTint: .gains,
                intent: "buy",
                autofocusTicker: true,
                onComplete: {
                    showAddStocks = false
                    Task {
                        await viewModel.loadPortfolio(slug: slug)
                        await viewModel.loadChart(slug: slug)
                    }
                }
            )
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
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
        // ── Phase D: scale-setting sheet ────────────────────────────────────
        .sheet(isPresented: $showScaleSheet) {
            SetScaleSheet(
                ownerName: viewModel.portfolio?.owner.publicName ?? "this portfolio",
                creatorPortfolioValue: viewModel.portfolio?.scale?.unscaledPortfolioValue
                    ?? viewModel.portfolio?.portfolioValue,
                currentTargetDollars: viewModel.portfolio?.scale?.targetDollars,
                amount: $scaleAmountInput,
                isSaving: $scaleIsSaving,
                errorText: $scaleError,
                onCancel: { showScaleSheet = false },
                onSubmit: { dollars in
                    guard let subscriptionId = viewModel.portfolio?.subscriptionId else { return }
                    Task {
                        scaleIsSaving = true
                        scaleError = nil
                        let ok = await viewModel.setScale(
                            slug: slug,
                            subscriptionId: subscriptionId,
                            targetDollars: dollars
                        )
                        scaleIsSaving = false
                        if ok {
                            showScaleSheet = false
                        } else {
                            scaleError = viewModel.error ?? "Failed to set scale"
                        }
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
    let portfolioValue: Double?
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
            HoldingRow(holding: holding, portfolioValue: portfolioValue)
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
                                        Text("\(holding.formattedQuantity) share\(holding.quantity == 1 ? "" : "s")")
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

/// Two-line holdings card.
///
/// Top row:    [TICKER badge]  TICKER                                 $TotalValue   X.X% port
///             quantity shares · $X.XX avg                            +$X.XX (+X.X%)
///
/// `portfolioValue` is the OWNER's total portfolio value, used to compute
/// the position's share of the portfolio. It's optional; if nil the
/// percent is hidden gracefully.
struct HoldingRow: View {
    let holding: Holding
    let portfolioValue: Double?

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
                // Quantity + average cost on the same subtitle line so both
                // pieces of info stay co-located. Cost basis only renders
                // when we actually have it (purchasePrice > 0).
                Text(quantityAndAvgLine)
                    .font(.caption)
                    .foregroundColor(.textSecondary)
            }
            .padding(.leading, 4)
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 4) {
                // Top-right line: total value + (in muted text) % of portfolio.
                HStack(spacing: 6) {
                    Text("$\(String(format: "%.2f", holding.totalValue))")
                        .font(.subheadline.bold())
                        .foregroundColor(.textPrimary)
                    if let pct = holding.percentOfPortfolio(portfolioValue) {
                        Text(formattedPortfolioPct(pct))
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(.textMuted)
                    }
                }
                // Bottom-right line: $ gain · % gain (color-coded). Falls back
                // to a neutral "-" if cost basis is missing.
                if let gainPct = holding.gainPercent, let gainDol = holding.gainDollars {
                    Text("\(formattedSignedDollars(gainDol)) (\(String(format: "%+.1f%%", gainPct)))")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(gainPct >= 0 ? .gains : .losses)
                } else {
                    Text("—")
                        .font(.caption)
                        .foregroundColor(.textMuted)
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    private var quantityAndAvgLine: String {
        let qtyPart = "\(holding.formattedQuantity) share\(holding.quantity == 1 ? "" : "s")"
        if holding.purchasePrice > 0 {
            return "\(qtyPart) · $\(String(format: "%.2f", holding.purchasePrice)) avg"
        }
        return qtyPart
    }

    private func formattedSignedDollars(_ value: Double) -> String {
        let sign = value >= 0 ? "+" : "-"
        return "\(sign)$\(String(format: "%.2f", abs(value)))"
    }

    private func formattedPortfolioPct(_ pct: Double) -> String {
        if pct < 1 { return "<1% port" }
        return String(format: "%.0f%% port", pct)
    }
}

// MARK: - Cash Row

/// Renders the user's available cash (cash_proceeds) as the last entry in
/// the Holdings list when present and > 0. Mirrors the visual structure of
/// `HoldingRow` so the list reads as one cohesive table.
struct CashRow: View {
    let cashBalance: Double
    let portfolioValue: Double?

    var body: some View {
        HStack {
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.primaryAccent.opacity(0.1))
                    .frame(width: 44, height: 44)
                Image(systemName: "dollarsign.circle.fill")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(.primaryAccent)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Cash")
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                Text("Available proceeds")
                    .font(.caption)
                    .foregroundColor(.textSecondary)
            }
            .padding(.leading, 4)

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                HStack(spacing: 6) {
                    Text("$\(String(format: "%.2f", cashBalance))")
                        .font(.subheadline.bold())
                        .foregroundColor(.textPrimary)
                    if let total = portfolioValue, total > 0 {
                        let pct = (cashBalance / total) * 100
                        Text(pct < 1 ? "<1% port" : String(format: "%.0f%% port", pct))
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(.textMuted)
                    }
                }
                Text("—")
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
    private var isPending: Bool { trade.isPending }
    
    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill((isPending ? Color.textMuted : (isBuy ? Color.gains : Color.losses)).opacity(0.15))
                    .frame(width: 32, height: 32)
                Image(systemName: isPending ? "clock.fill" : (isBuy ? "plus" : "minus"))
                    .font(.caption.weight(.bold))
                    .foregroundColor(isPending ? .textMuted : (isBuy ? .gains : .losses))
            }
            
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(trade.type.uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundColor(isBuy ? .gains : .losses)
                    Text(trade.ticker)
                        .font(.subheadline.bold())
                        .foregroundColor(.textPrimary)
                    if isPending {
                        Text("PENDING")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.textMuted)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Capsule().fill(Color.textMuted.opacity(0.15)))
                    }
                }
                Text(isPending ? "Executes at market open" : formatDate(trade.timestamp))
                    .font(.caption)
                    .foregroundColor(.textMuted)
            }
            
            Spacer()
            
            if isPending {
                Text("\(formatQuantity(trade.quantity)) shares")
                    .font(.subheadline)
                    .foregroundColor(.textSecondary)
            } else {
                Text("\(formatQuantity(trade.quantity)) @ $\(String(format: "%.2f", trade.price ?? 0))")
                    .font(.subheadline)
                    .foregroundColor(.textSecondary)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }
    
    private func formatDate(_ dateString: String) -> String {
        // Try standard ISO8601 first
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = isoFormatter.date(from: dateString)
        
        // Fallback without fractional seconds
        if date == nil {
            let basic = ISO8601DateFormatter()
            date = basic.date(from: dateString)
        }
        
        // Fallback: manual format for Python's isoformat() output (no timezone)
        // — assume UTC since the backend stores naive UTC datetimes.
        if date == nil {
            let manual = DateFormatter()
            manual.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
            manual.locale = Locale(identifier: "en_US_POSIX")
            manual.timeZone = TimeZone(identifier: "UTC")
            date = manual.date(from: dateString)
        }
        if date == nil {
            let manual = DateFormatter()
            manual.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            manual.locale = Locale(identifier: "en_US_POSIX")
            manual.timeZone = TimeZone(identifier: "UTC")
            date = manual.date(from: dateString)
        }
        
        if let date = date {
            // Always render in ET with explicit suffix so subscribers in
            // other tz's see the same wall-clock time the trader saw.
            // Format: "May 14, 1:43:27 PM ET"
            let displayFormatter = DateFormatter()
            displayFormatter.dateFormat = "MMM d, h:mm:ss a"
            displayFormatter.timeZone = TimeZone(identifier: "America/New_York")
            displayFormatter.locale = Locale(identifier: "en_US_POSIX")
            return displayFormatter.string(from: date) + " ET"
        }
        return dateString
    }
    
    private func formatQuantity(_ quantity: Double) -> String {
        if quantity == quantity.rounded() && quantity >= 1 {
            return String(format: "%.0f", quantity)
        } else if quantity >= 1 {
            return String(format: "%.2f", quantity)
        } else {
            // Fractional shares < 1: up to 4 decimals, trim trailing zeros
            let formatted = String(format: "%.4f", quantity)
            var result = formatted
            while result.hasSuffix("0") { result = String(result.dropLast()) }
            if result.hasSuffix(".") { result = String(result.dropLast()) }
            return result
        }
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

    // ── Phase D: portfolio resizer ──────────────────────────────────────
    /// Set the subscriber's scale (target dollar amount) for this
    /// portfolio. Reloads the portfolio on success so holdings + scale
    /// banner reflect the new state. Returns true on success.
    func setScale(slug: String, subscriptionId: Int, targetDollars: Double) async -> Bool {
        do {
            _ = try await APIService.shared.setSubscriptionScale(
                subscriptionId: subscriptionId,
                targetDollars: targetDollars
            )
            // Re-fetch the portfolio so scaled quantities/value populate.
            await loadPortfolio(slug: slug)
            return true
        } catch let APIError.serverError(code) {
            self.error = "Server error (\(code))"
            return false
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    /// Clear the subscriber's scale (return to unscaled view). Reloads
    /// the portfolio so the scale banner disappears immediately.
    func clearScale(slug: String, subscriptionId: Int) async {
        do {
            try await APIService.shared.clearSubscriptionScale(subscriptionId: subscriptionId)
            await loadPortfolio(slug: slug)
        } catch {
            self.error = error.localizedDescription
        }
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
        // Slimmed: dropped the 56pt gradient avatar and trimmed vertical
        // padding 16 → 10pt, spacing 8 → 4pt. Frees ~85pt so the chart +
        // Subscribe CTA + stats grid fit above the fold on iPhone 17 Pro.
        VStack(spacing: 4) {
            Text(portfolio.owner.publicName)
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
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
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
    @ObservedObject var subscriptionManager: SubscriptionManager
    let onSubscribe: () -> Void
    
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
                
                // Plan toggle pills
                HStack(spacing: 0) {
                    planPill(label: "Annual", sublabel: "$69/year", tag: "Save 36%", plan: .annual)
                    planPill(label: "Monthly", sublabel: "$9/month", tag: nil, plan: .monthly)
                }
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.white.opacity(0.06))
                )
                .padding(.horizontal, 16)
                
                // CTA button
                Button(action: onSubscribe) {
                    HStack(spacing: 6) {
                        Image(systemName: "crown.fill")
                            .font(.system(size: 13))
                        Text(subscriptionManager.selectedPlan == .annual
                             ? "Try Free for 7 Days, then $69/yr"
                             : "Try Free for 7 Days, then $9/mo")
                            .font(.system(size: 16, weight: .bold))
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Color.primaryAccent)
                    .cornerRadius(12)
                }
                .disabled(subscriptionManager.isProcessing)
                .padding(.horizontal, 16)
                
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
    
    private func planPill(label: String, sublabel: String, tag: String?, plan: SubscriptionManager.PlanType) -> some View {
        let isSelected = subscriptionManager.selectedPlan == plan
        return Button {
            withAnimation(.easeInOut(duration: 0.2)) {
                subscriptionManager.selectedPlan = plan
            }
        } label: {
            VStack(spacing: 3) {
                if let tag = tag {
                    Text(tag)
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(isSelected ? .white : .primaryAccent)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            Capsule().fill(isSelected ? Color.primaryAccent : Color.primaryAccent.opacity(0.15))
                        )
                }
                Text(label)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(isSelected ? .textPrimary : .textSecondary)
                Text(sublabel)
                    .font(.system(size: 11))
                    .foregroundColor(isSelected ? .textSecondary : .textMuted)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isSelected ? Color.white.opacity(0.1) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isSelected ? Color.primaryAccent : Color.clear, lineWidth: 1.5)
            )
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// MARK: - Phase D: Portfolio Resizer Components
// ─────────────────────────────────────────────────────────────────────────

/// Card shown above the Holdings list for subscribers. Two states:
///   • No scale set: gradient "Adjust Portfolio Size" CTA
///   • Scale active: badge with target_dollars + Edit/Clear actions
struct ScaleCard: View {
    let scale: PortfolioScale?
    let onTapEdit: () -> Void
    let onTapClear: () -> Void

    var body: some View {
        if let scale = scale {
            // Active-scale state
            HStack(spacing: 12) {
                Image(systemName: "scale.3d")
                    .font(.system(size: 18))
                    .foregroundColor(.primaryAccent)
                    .frame(width: 28)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Scaled to \(formatDollars(scale.targetDollars))")
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(.textPrimary)
                    Text("From " + formatDollars(scale.unscaledPortfolioValue) + " creator portfolio")
                        .font(.system(size: 11))
                        .foregroundColor(.textMuted)
                }
                Spacer()
                Button(action: onTapEdit) {
                    Text("Edit")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.primaryAccent)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.primaryAccent.opacity(0.5), lineWidth: 1)
                        )
                }
                Button(action: onTapClear) {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .padding(8)
                        .background(
                            Circle().fill(Color.white.opacity(0.05))
                        )
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .cardStyle(padding: 0)
        } else {
            // No-scale CTA
            Button(action: onTapEdit) {
                HStack(spacing: 10) {
                    Image(systemName: "scale.3d")
                        .font(.system(size: 16))
                    Text("Adjust Portfolio Size")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12))
                        .foregroundColor(.textMuted)
                }
                .foregroundColor(.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 14)
            }
            .cardStyle(padding: 0)
        }
    }

    private func formatDollars(_ value: Double) -> String {
        // Compact format: $10K, $1.2M, etc. Falls back to $X,XXX for
        // small values so the card doesn't say "$0K" for a $500 scale.
        if value >= 1_000_000 {
            return String(format: "$%.1fM", value / 1_000_000)
        }
        if value >= 10_000 {
            return String(format: "$%.0fK", value / 1_000)
        }
        if value >= 1_000 {
            return String(format: "$%.1fK", value / 1_000)
        }
        return "$" + String(format: "%.0f", value)
    }
}

/// Sheet presented when the subscriber taps "Adjust Portfolio Size" or
/// "Edit" on the ScaleCard. Lets them type a dollar amount, submits to
/// /subscriptions/<id>/scale, and dismisses on success.
struct SetScaleSheet: View {
    let ownerName: String
    let creatorPortfolioValue: Double?
    let currentTargetDollars: Double?
    @Binding var amount: String
    @Binding var isSaving: Bool
    @Binding var errorText: String?
    let onCancel: () -> Void
    let onSubmit: (Double) -> Void

    @FocusState private var inputFocused: Bool

    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()

                VStack(alignment: .leading, spacing: 20) {
                    // Headline
                    VStack(alignment: .leading, spacing: 6) {
                        Text(currentTargetDollars == nil
                             ? "Adjust portfolio size"
                             : "Update portfolio size")
                            .font(.title3.weight(.bold))
                            .foregroundColor(.textPrimary)
                        Text("All holdings on \(ownerName)'s portfolio will be scaled to match. The scale is frozen at the moment you set it.")
                            .font(.caption)
                            .foregroundColor(.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        // Compliance disclaimer per LAUNCH_PLAYBOOK.md — must be
                        // visible at the moment the user commits to a $ amount.
                        Text("For educational purposes only. This is not investment advice.")
                            .font(.caption2)
                            .foregroundColor(.textMuted)
                            .padding(.top, 2)
                    }

                    // Creator portfolio context
                    if let value = creatorPortfolioValue, value > 0 {
                        HStack {
                            Text("Creator portfolio")
                                .font(.caption)
                                .foregroundColor(.textMuted)
                            Spacer()
                            Text(String(format: "$%.0f", value))
                                .font(.caption.monospacedDigit())
                                .foregroundColor(.textSecondary)
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .cardStyle(padding: 0)
                    }

                    // Dollar input
                    HStack(spacing: 6) {
                        Text("$")
                            .font(.system(size: 28, weight: .bold))
                            .foregroundColor(.textSecondary)
                        TextField("0", text: $amount)
                            .keyboardType(.numberPad)
                            .font(.system(size: 32, weight: .bold))
                            .foregroundColor(.textPrimary)
                            .focused($inputFocused)
                            .onAppear {
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                                    inputFocused = true
                                }
                            }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 14)
                    .cardStyle(padding: 0)

                    if let err = errorText {
                        Text(err)
                            .font(.caption)
                            .foregroundColor(.losses)
                    }

                    Spacer()

                    // Submit
                    Button {
                        let dollars = Double(amount.replacingOccurrences(of: ",", with: ""))
                            ?? 0
                        guard dollars > 0 else {
                            errorText = "Enter a dollar amount greater than 0"
                            return
                        }
                        onSubmit(dollars)
                    } label: {
                        HStack {
                            if isSaving {
                                ProgressView()
                                    .tint(.white)
                                    .padding(.trailing, 6)
                            }
                            Text(isSaving ? "Saving..." : "Apply Scale")
                                .font(.system(size: 16, weight: .bold))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color.primaryAccent)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                    }
                    .disabled(isSaving)
                }
                .padding(20)
            }
            .navigationTitle("Portfolio Size")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel", action: onCancel)
                        .foregroundColor(.textSecondary)
                }
            }
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
