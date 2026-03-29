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
    @State private var showSettings = false
    @State private var showFilters = false
    @State private var expandedEntryId: Int? = nil
    @State private var autoExpandedTop = true
    
    // Pending filter state (applied only on "Apply")
    @State private var pendingCategory = "all"
    @State private var pendingSectors: Set<String> = []
    @State private var pendingFrequency = "any"
    @State private var pendingHideLoQ = true
    
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
                frequency: selectedFrequency
            )
        }
    }
    
    private func openFilters() {
        pendingCategory = selectedCategory
        pendingSectors = selectedSectors
        pendingFrequency = selectedFrequency
        pendingHideLoQ = hideLoQ
        showFilters = true
    }
    
    private func applyFilters() {
        selectedCategory = pendingCategory
        selectedSectors = pendingSectors
        selectedFrequency = pendingFrequency
        hideLoQ = pendingHideLoQ
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
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // ── Custom header (no nav bar pill) ──
                    AppHeaderRow(showSettings: $showSettings)
                    
                    // ── Period pills + Filter button row ──
                    HStack(spacing: 8) {
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
                        
                        // Filter button
                        Button(action: openFilters) {
                            ZStack(alignment: .topTrailing) {
                                Image(systemName: "line.3.horizontal.decrease")
                                    .font(.system(size: 16, weight: .semibold))
                                    .foregroundColor(activeFilterCount > 0 ? .primaryAccent : .textMuted)
                                    .frame(width: 36, height: 36)
                                    .background(
                                        RoundedRectangle(cornerRadius: 8)
                                            .fill(activeFilterCount > 0 ? Color.primaryAccent.opacity(0.15) : Color.cardBackground)
                                    )
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 8)
                                            .stroke(activeFilterCount > 0 ? Color.primaryAccent.opacity(0.4) : Color.cardBorder, lineWidth: 0.5)
                                    )
                                
                                if activeFilterCount > 0 {
                                    Text("\(activeFilterCount)")
                                        .font(.system(size: 9, weight: .bold))
                                        .foregroundColor(.appBackground)
                                        .frame(width: 16, height: 16)
                                        .background(Circle().fill(Color.primaryAccent))
                                        .offset(x: 4, y: -4)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    
                    // ── S&P 500 benchmark banner ──
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
                        
                        Text(selectedPeriod)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.textMuted)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Capsule().fill(Color.cardBorder.opacity(0.3)))
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
                                frequency: selectedFrequency
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
                        }
                    }
                    
                    // User info column
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.user.username)
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
                        }
                    }
                    
                    Spacer(minLength: 4)
                    
                    // Sparkline
                    SparklineView(
                        dataPoints: entry.sparklineData ?? [],
                        sp500Points: entry.sp500SparklineData ?? [],
                        isPositive: entry.returnPercent >= 0
                    )
                    .frame(width: 52, height: 26)
                    
                    // Return percent
                    Text(String(format: "%+.1f%%", entry.returnPercent))
                        .font(.system(size: 15, weight: .bold, design: .rounded).monospacedDigit())
                        .foregroundColor(entry.returnPercent >= 0 ? .gains : .losses)
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
            
            // Stats grid
            HStack(spacing: 0) {
                statCell(title: "Trades/wk", value: String(format: "%.1f", entry.avgTradesPerWeek ?? 0))
                statDivider
                statCell(title: "Stocks", value: "\(entry.uniqueStocks ?? 0)")
                statDivider
                statCell(title: "Large Cap", value: String(format: "%.0f%%", entry.largeCapPct ?? 0))
                statDivider
                statCell(title: "Age", value: formatAge(entry.accountAgeDays ?? 0))
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
            
            // Action buttons
            HStack(spacing: 10) {
                NavigationLink(destination: PortfolioDetailView(slug: entry.user.portfolioSlug ?? "")) {
                    HStack(spacing: 5) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.system(size: 11))
                        Text("View Portfolio")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundColor(.primaryAccent)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(Color.primaryAccent.opacity(0.4), lineWidth: 1)
                    )
                }
                
                Button {
                    Task { await subscriptionManager.subscribe(to: entry.user.id) }
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "bell.fill")
                            .font(.system(size: 11))
                        Text("Subscribe $9/mo")
                            .font(.system(size: 12, weight: .bold))
                    }
                    .foregroundColor(.appBackground)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 10).fill(Color.primaryAccent)
                    )
                }
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 12)
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
                         frequency: String = "any") async {
        isLoading = true
        error = nil
        
        do {
            let response = try await APIService.shared.getLeaderboard(
                period: period, category: category,
                activeEdge: activeEdge, industry: industry, frequency: frequency
            )
            entries = response.entries
            sp500Return = response.sp500Return ?? 0.0
            availableIndustries = response.availableIndustries
        } catch is CancellationError {
            // Silently ignore — happens naturally during pull-to-refresh
        } catch let urlError as URLError where urlError.code == .cancelled {
            // Silently ignore — iOS cancels in-flight request on refresh
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
}

struct LeaderboardView_Previews: PreviewProvider {
    static var previews: some View {
        LeaderboardView()
    }
}
