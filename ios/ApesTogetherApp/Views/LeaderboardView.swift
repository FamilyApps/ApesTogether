import SwiftUI
import Combine
import Charts

// MARK: - Leaderboard View

struct LeaderboardView: View {
    @StateObject private var viewModel = LeaderboardViewModel()
    @State private var selectedPeriod = "1W"
    @State private var selectedCategory = "all"
    @State private var selectedSectors: Set<String> = []
    @State private var selectedFrequency = "any"
    @State private var hideLoQ = true
    // Persisted across launches so power users don't have to re-enable it.
    @AppStorage("leaderboard_hide_fractional") private var hideFractional: Bool = false
    @State private var showSettings = false
    @State private var showFilters = false
    @State private var expandedEntryId: Int? = nil
    @State private var autoExpandedTop = true
    
    // Pending filter state (applied only on "Apply")
    @State private var pendingCategory = "all"
    @State private var pendingSectors: Set<String> = []
    @State private var pendingFrequency = "any"
    @State private var pendingHideLoQ = true
    @State private var pendingHideFractional = false
    
    private let periods = ["1D", "1W", "1M", "3M", "YTD", "1Y"]
    
    // 11 GICS sectors
    static let gicsSectors = [
        "Technology", "Healthcare", "Financials", "Consumer Discretionary",
        "Communication Services", "Industrials", "Consumer Staples",
        "Energy", "Utilities", "Real Estate", "Materials"
    ]
    
    private var activeFilterCount: Int {
        var count = 0
        if selectedCategory != "all" { count += 1 }
        if !selectedSectors.isEmpty { count += 1 }
        if selectedFrequency != "any" { count += 1 }
        if !hideLoQ { count += 1 }
        if hideFractional { count += 1 }
        return count
    }
    
    private func isExpanded(_ entry: LeaderboardEntry) -> Bool {
        if let explicit = expandedEntryId {
            return explicit == entry.id
        }
        if autoExpandedTop && entry.rank == 1 {
            return true
        }
        return false
    }
    
    private var sectorFilterParam: String {
        selectedSectors.isEmpty ? "all" : selectedSectors.sorted().joined(separator: ",")
    }
    
    private func reloadLeaderboard() {
        Task {
            await viewModel.loadLeaderboard(
                period: selectedPeriod, category: selectedCategory,
                activeEdge: hideLoQ, industry: sectorFilterParam,
                frequency: selectedFrequency, hideFractional: hideFractional
            )
        }
    }
    
    private func openFilters() {
        pendingCategory = selectedCategory
        pendingSectors = selectedSectors
        pendingFrequency = selectedFrequency
        pendingHideLoQ = hideLoQ
        pendingHideFractional = hideFractional
        showFilters = true
    }
    
    private func applyFilters() {
        selectedCategory = pendingCategory
        selectedSectors = pendingSectors
        selectedFrequency = pendingFrequency
        hideLoQ = pendingHideLoQ
        hideFractional = pendingHideFractional
        showFilters = false
        expandedEntryId = nil
        autoExpandedTop = true
        reloadLeaderboard()
    }
    
    private func resetFilters() {
        pendingCategory = "all"
        pendingSectors = []
        pendingFrequency = "any"
        pendingHideLoQ = true
        pendingHideFractional = false
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // ── Custom header (no nav bar pill) ──
                    AppHeaderRow(showSettings: $showSettings)
                    
                    // ── Period pills (full-width, no filter icon) ──
                    // The filter button moved down to the S&P banner row so
                    // the period selector reads more clearly and replaces
                    // the duplicative selected-period capsule next to S&P.
                    HStack(spacing: 0) {
                        ForEach(periods, id: \.self) { period in
                            Button {
                                selectedPeriod = period
                                expandedEntryId = nil
                                autoExpandedTop = true
                                reloadLeaderboard()
                            } label: {
                                Text(period)
                                    .font(.system(size: 13, weight: .bold))
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 8)
                                    .background(selectedPeriod == period ? Color.primaryAccent : Color.clear)
                                    .foregroundColor(selectedPeriod == period ? .appBackground : .textMuted)
                                    .cornerRadius(8)
                            }
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    
                    // ── S&P 500 benchmark banner + Filters button ──
                    // The Filters button replaces the previous selected-period
                    // capsule on the right (which duplicated the highlighted
                    // pill above). Industry-standard text label "Filters" with
                    // a numeric badge when any non-default filter is active.
                    HStack(spacing: 10) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.primaryAccent)
                        
                        Text("S&P 500")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.textSecondary)
                        
                        Text(String(format: "%+.2f%%", viewModel.sp500Return))
                            .font(.system(size: 15, weight: .bold, design: .rounded))
                            .foregroundColor(viewModel.sp500Return >= 0 ? .gains : .losses)
                        
                        Spacer()
                        
                        Button(action: openFilters) {
                            HStack(spacing: 6) {
                                Text("Filters")
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(activeFilterCount > 0 ? .primaryAccent : .textSecondary)
                                if activeFilterCount > 0 {
                                    Text("\(activeFilterCount)")
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundColor(.appBackground)
                                        .frame(minWidth: 18, minHeight: 18)
                                        .padding(.horizontal, 4)
                                        .background(Capsule().fill(Color.primaryAccent))
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(
                                Capsule()
                                    .fill(activeFilterCount > 0 ? Color.primaryAccent.opacity(0.12) : Color.cardBorder.opacity(0.3))
                            )
                            .overlay(
                                Capsule()
                                    .stroke(activeFilterCount > 0 ? Color.primaryAccent.opacity(0.4) : Color.clear, lineWidth: 0.5)
                            )
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(Color.cardBackground)
                    .overlay(
                        VStack {
                            Spacer()
                            Rectangle().fill(Color.cardBorder.opacity(0.3)).frame(height: 0.5)
                        }
                    )
                    
                    // ── Leaderboard list ──
                    if viewModel.isLoading && viewModel.entries.isEmpty {
                        Spacer()
                        ProgressView().tint(.primaryAccent)
                        Spacer()
                    } else if let error = viewModel.error {
                        Spacer()
                        EmptyStateView(
                            icon: "exclamationmark.triangle", title: "Error", message: error,
                            action: { reloadLeaderboard() }, actionLabel: "Retry"
                        )
                        Spacer()
                    } else if viewModel.entries.isEmpty {
                        Spacer()
                        EmptyStateView(
                            icon: "trophy", title: "No Rankings Yet",
                            message: "Rankings are calculated during market hours.\nCheck back soon!",
                            action: { reloadLeaderboard() }, actionLabel: "Refresh"
                        )
                        Spacer()
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 8) {
                                ForEach(viewModel.entries) { entry in
                                    LeaderboardCard(
                                        entry: entry,
                                        isExpanded: isExpanded(entry),
                                        selectedPeriod: selectedPeriod,
                                        onTap: {
                                            withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
                                                autoExpandedTop = false
                                                expandedEntryId = expandedEntryId == entry.id ? nil : entry.id
                                            }
                                        }
                                    )
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                        }
                        .refreshable {
                            await viewModel.loadLeaderboard(
                                period: selectedPeriod, category: selectedCategory,
                                activeEdge: hideLoQ, industry: sectorFilterParam,
                                frequency: selectedFrequency, hideFractional: hideFractional
                            )
                        }
                    }
                }
            }
            .appNavBar(showSettings: $showSettings)
            .onAppear {
                if viewModel.entries.isEmpty { reloadLeaderboard() }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
            .sheet(isPresented: $showFilters) {
                FilterSheet(
                    category: $pendingCategory,
                    sectors: $pendingSectors,
                    frequency: $pendingFrequency,
                    hideLoQ: $pendingHideLoQ,
                    hideFractional: $pendingHideFractional,
                    allSectors: LeaderboardView.gicsSectors,
                    onApply: applyFilters,
                    onReset: resetFilters
                )
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
            }
        }
    }
}

// MARK: - Filter Sheet

struct FilterSheet: View {
    @Binding var category: String
    @Binding var sectors: Set<String>
    @Binding var frequency: String
    @Binding var hideLoQ: Bool
    @Binding var hideFractional: Bool
    let allSectors: [String]
    let onApply: () -> Void
    let onReset: () -> Void
    @Environment(\.dismiss) private var dismiss
    
    private var allSectorsSelected: Bool { sectors.isEmpty }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        
                        // ── Quality ──
                        filterSection(title: "Quality") {
                            VStack(spacing: 12) {
                                Toggle(isOn: $hideLoQ) {
                                    HStack(spacing: 8) {
                                        Image(systemName: hideLoQ ? "checkmark.shield.fill" : "shield")
                                            .foregroundColor(.primaryAccent)
                                            .font(.system(size: 14))
                                        Text("Hide low quality")
                                            .font(.system(size: 14, weight: .medium))
                                            .foregroundColor(.textPrimary)
                                    }
                                }
                                .tint(.primaryAccent)
                                
                                Toggle(isOn: $hideFractional) {
                                    HStack(spacing: 8) {
                                        Image(systemName: hideFractional ? "chart.pie.fill" : "chart.pie")
                                            .foregroundColor(.primaryAccent)
                                            .font(.system(size: 14))
                                        Text("Hide fractional shares")
                                            .font(.system(size: 14, weight: .medium))
                                            .foregroundColor(.textPrimary)
                                    }
                                }
                                .tint(.primaryAccent)
                            }
                        }
                        
                        // ── Market Cap ──
                        filterSection(title: "Market Cap") {
                            HStack(spacing: 10) {
                                filterOption(label: "All", isSelected: category == "all") {
                                    category = "all"
                                }
                                filterOption(label: "Large Cap", isSelected: category == "large_cap") {
                                    category = "large_cap"
                                }
                                filterOption(label: "Small Cap", isSelected: category == "small_cap") {
                                    category = "small_cap"
                                }
                            }
                        }
                        
                        // ── Trading Frequency ──
                        filterSection(title: "Trading Frequency") {
                            HStack(spacing: 10) {
                                filterOption(label: "Any", isSelected: frequency == "any") {
                                    frequency = "any"
                                }
                                filterOption(label: "Day Traders", isSelected: frequency == "day_trader") {
                                    frequency = "day_trader"
                                }
                                filterOption(label: "Moderate", isSelected: frequency == "moderate") {
                                    frequency = "moderate"
                                }
                            }
                        }
                        
                        // ── Sector (GICS) ──
                        filterSection(title: "Sector") {
                            VStack(spacing: 0) {
                                // "All Sectors" row
                                Button {
                                    sectors = []
                                } label: {
                                    HStack(spacing: 10) {
                                        Image(systemName: allSectorsSelected ? "checkmark.circle.fill" : "circle")
                                            .font(.system(size: 18))
                                            .foregroundColor(allSectorsSelected ? .primaryAccent : .textMuted)
                                        Text("All Sectors")
                                            .font(.system(size: 14, weight: .semibold))
                                            .foregroundColor(.textPrimary)
                                        Spacer()
                                    }
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 10)
                                    .background(
                                        RoundedRectangle(cornerRadius: 10)
                                            .fill(allSectorsSelected ? Color.primaryAccent.opacity(0.1) : Color.cardBackground)
                                    )
                                }
                                
                                ForEach(allSectors, id: \.self) { sector in
                                    let isSelected = sectors.contains(sector)
                                    Button {
                                        if isSelected {
                                            sectors.remove(sector)
                                        } else {
                                            sectors.insert(sector)
                                        }
                                    } label: {
                                        HStack(spacing: 10) {
                                            Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                                                .font(.system(size: 18))
                                                .foregroundColor(isSelected ? .primaryAccent : .textMuted)
                                            Text(sector)
                                                .font(.system(size: 14, weight: .medium))
                                                .foregroundColor(.textPrimary)
                                            Spacer()
                                        }
                                        .padding(.horizontal, 14)
                                        .padding(.vertical, 10)
                                    }
                                }
                            }
                            .background(
                                RoundedRectangle(cornerRadius: 12)
                                    .fill(Color.cardBackground)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.cardBorder, lineWidth: 0.5)
                            )
                        }
                        
                        Spacer(minLength: 80)
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 16)
                }
                
                // ── Bottom Apply bar ──
                VStack {
                    Spacer()
                    HStack(spacing: 12) {
                        Button(action: onReset) {
                            Text("Reset")
                                .font(.system(size: 15, weight: .semibold))
                                .foregroundColor(.textSecondary)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.cardBorder, lineWidth: 1)
                                )
                        }
                        
                        Button(action: onApply) {
                            Text("Apply Filters")
                                .font(.system(size: 15, weight: .bold))
                                .foregroundColor(.appBackground)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(
                                    RoundedRectangle(cornerRadius: 12)
                                        .fill(Color.primaryAccent)
                                )
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 16)
                    .background(
                        Color.appBackground
                            .shadow(color: .black.opacity(0.3), radius: 8, y: -4)
                    )
                }
            }
            .navigationTitle("Filters")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textMuted)
                            .font(.system(size: 20))
                    }
                }
            }
        }
    }
    
    private func filterSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(.textMuted)
                .textCase(.uppercase)
                .tracking(0.8)
            content()
        }
    }
    
    private func filterOption(label: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(isSelected ? .appBackground : .textSecondary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(isSelected ? Color.primaryAccent : Color.cardBackground)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(isSelected ? Color.clear : Color.cardBorder, lineWidth: 0.5)
                )
        }
    }
}

// MARK: - Leaderboard Card

struct LeaderboardCard: View {
    let entry: LeaderboardEntry
    let isExpanded: Bool
    let selectedPeriod: String
    let onTap: () -> Void
    @EnvironmentObject var subscriptionManager: SubscriptionManager
    
    private var rankGradient: LinearGradient? {
        switch entry.rank {
        case 1: return LinearGradient(colors: [Color(hex: "FFD700").opacity(0.12), Color.clear], startPoint: .topLeading, endPoint: .bottomTrailing)
        case 2: return LinearGradient(colors: [Color(hex: "C0C0C0").opacity(0.08), Color.clear], startPoint: .topLeading, endPoint: .bottomTrailing)
        case 3: return LinearGradient(colors: [Color(hex: "CD7F32").opacity(0.08), Color.clear], startPoint: .topLeading, endPoint: .bottomTrailing)
        default: return nil
        }
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // ── Compact row ──
            Button(action: onTap) {
                HStack(spacing: 10) {
                    // Rank badge + change indicator
                    HStack(spacing: 3) {
                        rankBadge
                        if let rc = entry.rankChange, rc != 0 {
                            Image(systemName: rc > 0 ? "arrowtriangle.up.fill" : "arrowtriangle.down.fill")
                                .font(.system(size: 7))
                                .foregroundColor(rc > 0 ? .gains : .losses)
                        } else {
                            Text("—")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(.textMuted.opacity(0.5))
                        }
                    }
                    
                    // User info column
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.user.publicName)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.textPrimary)
                            .lineLimit(1)
                        HStack(spacing: 6) {
                            HStack(spacing: 2) {
                                Image(systemName: "person.2.fill")
                                    .font(.system(size: 8))
                                Text("\(entry.subscriberCount)")
                                    .font(.system(size: 10, weight: .medium))
                            }
                            .foregroundColor(.textMuted)
                            
                            if let tpw = entry.avgTradesPerWeek, tpw > 0 {
                                HStack(spacing: 2) {
                                    Image(systemName: "arrow.left.arrow.right")
                                        .font(.system(size: 7))
                                    Text(String(format: "%.0f/wk", tpw))
                                        .font(.system(size: 10, weight: .medium))
                                }
                                .foregroundColor(.textMuted)
                            }
                            
                            // Founding Trader — one of the first 100 human
                            // traders. Compact chip on the stats line (not
                            // next to the name) so long usernames never
                            // truncate because of it. Mirrors Android's
                            // FoundingTraderChip in LeaderboardScreen.kt.
                            if entry.user.foundingTrader == true {
                                founderChip
                            }
                        }
                    }
                    
                    Spacer(minLength: 4)
                    
                    // Sparkline
                    SparklineView(
                        dataPoints: entry.sparklineData ?? [],
                        sp500Points: entry.sp500SparklineData ?? [],
                        isPositive: (entry.alphaVsSp500 ?? entry.returnPercent) >= 0
                    )
                    .frame(width: 52, height: 26)
                    
                    // Alpha vs S&P (main value prop)
                    VStack(alignment: .trailing, spacing: 1) {
                        let alpha = entry.alphaVsSp500 ?? (entry.returnPercent - (entry.sp500Return ?? 0))
                        Text(String(format: "%+.1f%%", alpha))
                            .font(.system(size: 15, weight: .bold, design: .rounded).monospacedDigit())
                            .foregroundColor(alpha >= 0 ? .gains : .losses)
                        Text("vs S&P")
                            .font(.system(size: 8, weight: .medium))
                            .foregroundColor(.textMuted)
                    }
                    .frame(minWidth: 56, alignment: .trailing)
                    
                    // Expand chevron
                    Image(systemName: "chevron.down")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .rotationEffect(.degrees(isExpanded ? 180 : 0))
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .contentShape(Rectangle())
            }
            .buttonStyle(PlainButtonStyle())
            
            // ── Expanded detail ──
            if isExpanded {
                expandedContent
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.cardBackground)
                .overlay(
                    Group {
                        if let grad = rankGradient {
                            RoundedRectangle(cornerRadius: 14).fill(grad)
                        }
                    }
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(
                    isExpanded ? Color.primaryAccent.opacity(0.25) : Color.cardBorder.opacity(0.4),
                    lineWidth: isExpanded ? 1 : 0.5
                )
        )
    }
    
    // MARK: - Founding Trader Chip
    /// Compact gold "FOUNDER" chip sized to sit inline with the 10pt stats
    /// line (subscribers + trades/wk) without changing the row height.
    private var founderChip: some View {
        let gold = Color(hex: "FFD700")
        return HStack(spacing: 2) {
            Image(systemName: "medal.fill")
                .font(.system(size: 8))
            Text("FOUNDER")
                .font(.system(size: 8, weight: .bold))
                .tracking(0.5)
        }
        .foregroundColor(gold)
        .padding(.horizontal, 5)
        .padding(.vertical, 1)
        .background(gold.opacity(0.14))
        .overlay(
            RoundedRectangle(cornerRadius: 7)
                .stroke(gold.opacity(0.45), lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: 7))
    }
    
    // MARK: - Rank Badge
    private var rankBadge: some View {
        ZStack {
            if entry.rank <= 3 {
                Circle()
                    .fill(entry.rank == 1 ? Color(hex: "FFD700").opacity(0.2) :
                          entry.rank == 2 ? Color(hex: "C0C0C0").opacity(0.2) :
                                            Color(hex: "CD7F32").opacity(0.2))
                    .frame(width: 30, height: 30)
                Text(entry.rank == 1 ? "🥇" : entry.rank == 2 ? "🥈" : "🥉")
                    .font(.system(size: 16))
            } else {
                Circle()
                    .fill(Color.cardBorder.opacity(0.3))
                    .frame(width: 30, height: 30)
                Text("\(entry.rank)")
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .foregroundColor(.textSecondary)
            }
        }
    }
    
    // MARK: - Expanded Content
    private var expandedContent: some View {
        VStack(spacing: 10) {
            Rectangle().fill(Color.cardBorder.opacity(0.3)).frame(height: 0.5)
                .padding(.horizontal, 14)
            
            // Stats row: Subscribers | Stocks | Trades/wk | Return
            HStack(spacing: 0) {
                statCell(title: "Subscribers", value: "\(entry.subscriberCount)")
                statDivider
                statCell(title: "Stocks", value: "\(entry.uniqueStocks ?? 0)")
                statDivider
                statCell(title: "Trades/wk", value: String(format: "%.1f", entry.avgTradesPerWeek ?? 0))
                statDivider
                statCell(title: "Return", value: String(format: "%+.1f%%", entry.returnPercent))
            }
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.appBackground.opacity(0.5))
            )
            .padding(.horizontal, 14)
            
            // Sector mix pills (by dollar value)
            if let mix = entry.industryMix, !mix.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("PORTFOLIO MIX")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.textMuted)
                        .tracking(0.6)
                        .padding(.horizontal, 14)
                    
                    // Stacked bar showing sector proportions
                    GeometryReader { geo in
                        HStack(spacing: 1) {
                            ForEach(Array(mix.sorted(by: { $0.value > $1.value })), id: \.key) { name, pct in
                                let width = max(geo.size.width * CGFloat(pct / 100.0), 2)
                                Rectangle()
                                    .fill(sectorColor(name))
                                    .frame(width: width)
                            }
                        }
                        .clipShape(Capsule())
                    }
                    .frame(height: 6)
                    .padding(.horizontal, 14)
                    
                    // Sector labels
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(Array(mix.sorted(by: { $0.value > $1.value })), id: \.key) { name, pct in
                                HStack(spacing: 4) {
                                    Circle()
                                        .fill(sectorColor(name))
                                        .frame(width: 6, height: 6)
                                    Text(name)
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundColor(.textSecondary)
                                    Text(String(format: "%.0f%%", pct))
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundColor(.textPrimary)
                                }
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(
                                    Capsule().fill(Color.cardBorder.opacity(0.3))
                                )
                            }
                        }
                        .padding(.horizontal, 14)
                    }
                }
            }
            
            // Action buttons (stacked vertically for consistent sizing)
            VStack(spacing: 8) {
                NavigationLink(destination: PortfolioDetailView(slug: entry.user.portfolioSlug ?? "", initialPeriod: selectedPeriod)) {
                    HStack(spacing: 5) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.system(size: 12))
                        Text("View Portfolio")
                            .font(.system(size: 13, weight: .semibold))
                    }
                    .foregroundColor(.primaryAccent)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(Color.primaryAccent.opacity(0.4), lineWidth: 1)
                    )
                }
                
                // Already-subscribed viewers only see "View Portfolio" above,
                // plus a subscribed marker — no plan toggle / Subscribe CTA.
                if entry.isSubscribed == true {
                    HStack(spacing: 5) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 12))
                        Text("Subscribed")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundColor(.primaryAccent)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
                } else if entry.acceptsNewSubscribers == false {
                    // W7: creator paused new subscriptions — explain instead of
                    // offering a Subscribe CTA (they still rank on the leaderboard).
                    Text("Not accepting new subscribers right now")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.textMuted)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                } else {
                    // Compact plan toggle
                    CompactPlanToggle(subscriptionManager: subscriptionManager)
                    
                    Button {
                        Task {
                            await subscriptionManager.subscribe(
                                to: entry.user.id,
                                username: entry.user.publicName,
                                slug: entry.user.portfolioSlug
                            )
                        }
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: "crown.fill")
                                .font(.system(size: 12))
                            Text(subscriptionManager.selectedPlan == .annual
                                 ? "Try Free for 7 Days, then $69/yr"
                                 : "Try Free for 7 Days, then $\(String(format: "%.0f", entry.subscriptionPrice))/mo")
                                .font(.system(size: 13, weight: .bold))
                        }
                        .foregroundColor(.appBackground)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 10).fill(Color.primaryAccent)
                        )
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 12)
        }
        .alert("Subscription", isPresented: Binding(
            get: { subscriptionManager.error != nil },
            set: { if !$0 { subscriptionManager.error = nil } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(subscriptionManager.error ?? "")
        }
    }
    
    private var statDivider: some View {
        Rectangle().fill(Color.cardBorder.opacity(0.4)).frame(width: 0.5, height: 28)
    }
    
    private func statCell(title: String, value: String) -> some View {
        VStack(spacing: 3) {
            Text(value)
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .foregroundColor(.textPrimary)
            Text(title)
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity)
    }
    
    private func formatAge(_ days: Int) -> String {
        if days < 30 { return "\(days)d" }
        if days < 365 { return "\(days / 30)mo" }
        return "\(days / 365)y"
    }
    
    private func sectorColor(_ sector: String) -> Color {
        switch sector.lowercased() {
        case let s where s.contains("tech"):        return Color(hex: "3B82F6")
        case let s where s.contains("health"):      return Color(hex: "22C55E")
        case let s where s.contains("financ"):      return Color(hex: "F59E0B")
        case let s where s.contains("consumer d"):  return Color(hex: "EC4899")
        case let s where s.contains("communicat"):  return Color(hex: "8B5CF6")
        case let s where s.contains("industrial"):  return Color(hex: "6366F1")
        case let s where s.contains("consumer s"):  return Color(hex: "14B8A6")
        case let s where s.contains("energy"):      return Color(hex: "EF4444")
        case let s where s.contains("utilit"):       return Color(hex: "64748B")
        case let s where s.contains("real"):         return Color(hex: "D97706")
        case let s where s.contains("material"):     return Color(hex: "78716C")
        default:                                      return Color(hex: "9CA3AF")
        }
    }
}

// MARK: - View Model

@MainActor
class LeaderboardViewModel: ObservableObject {
    @Published var entries: [LeaderboardEntry] = []
    @Published var sp500Return: Double = 0.0
    @Published var availableIndustries: [String]?
    @Published var isLoading = false
    @Published var error: String?
    
    func loadLeaderboard(period: String, category: String = "all",
                         activeEdge: Bool = true, industry: String = "all",
                         frequency: String = "any", hideFractional: Bool = false) async {
        isLoading = true
        error = nil
        
        do {
            let response = try await APIService.shared.getLeaderboard(
                period: period, category: category,
                activeEdge: activeEdge, industry: industry, frequency: frequency,
                hideFractional: hideFractional
            )
            entries = response.entries
            sp500Return = response.sp500Return ?? 0.0
            availableIndustries = response.availableIndustries
        } catch is CancellationError {
            // Silently ignore — happens naturally during pull-to-refresh
        } catch let urlError as URLError where urlError.code == .cancelled {
            // Silently ignore — iOS cancels in-flight request on refresh
        } catch {
            // Ignore any cancellation-like errors (can be wrapped in various ways)
            let desc = error.localizedDescription.lowercased()
            if !desc.contains("cancelled") && !desc.contains("canceled") {
                self.error = error.localizedDescription
            }
        }
        
        isLoading = false
    }
}

struct LeaderboardView_Previews: PreviewProvider {
    static var previews: some View {
        LeaderboardView()
    }
}
