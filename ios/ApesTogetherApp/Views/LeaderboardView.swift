import SwiftUI
import Combine
import Charts

struct LeaderboardView: View {
    @StateObject private var viewModel = LeaderboardViewModel()
    @State private var selectedPeriod = "7D"
    @State private var selectedCategory = "all"
    @State private var selectedIndustry = "all"
    @State private var selectedFrequency = "any"
    @State private var activeEdge = true
    @State private var sortBySubscribers = false
    @State private var showFilters = false
    @State private var showSettings = false
    @State private var expandedEntryId: Int? = nil
    
    let periods = ["1D", "5D", "7D", "1M", "3M", "YTD", "1Y"]
    let categories: [(key: String, label: String)] = [
        ("all", "All"),
        ("large_cap", "Large Cap"),
        ("small_cap", "Small Cap")
    ]
    let frequencies: [(key: String, label: String)] = [
        ("any", "Any"),
        ("day_trader", "Day Traders"),
        ("moderate", "Moderate")
    ]
    
    init() {
        let appearance = UINavigationBarAppearance()
        appearance.configureWithOpaqueBackground()
        appearance.backgroundColor = UIColor(Color.appBackground)
        appearance.titleTextAttributes = [.foregroundColor: UIColor(Color.textPrimary)]
        appearance.largeTitleTextAttributes = [.foregroundColor: UIColor(Color.textPrimary)]
        UINavigationBar.appearance().standardAppearance = appearance
        UINavigationBar.appearance().scrollEdgeAppearance = appearance
    }
    
    private var activeFilterCount: Int {
        var count = 0
        if selectedCategory != "all" { count += 1 }
        if selectedIndustry != "all" { count += 1 }
        if selectedFrequency != "any" { count += 1 }
        if !activeEdge { count += 1 }
        if sortBySubscribers { count += 1 }
        return count
    }
    
    private var sortedEntries: [LeaderboardEntry] {
        if sortBySubscribers {
            return viewModel.entries.sorted { $0.subscriberCount > $1.subscriberCount }
        }
        return viewModel.entries
    }
    
    private func reloadLeaderboard() {
        Task {
            await viewModel.loadLeaderboard(
                period: selectedPeriod, category: selectedCategory,
                activeEdge: activeEdge, industry: selectedIndustry,
                frequency: selectedFrequency
            )
        }
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // Time period selector
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(periods, id: \.self) { period in
                                Button {
                                    selectedPeriod = period
                                    reloadLeaderboard()
                                } label: {
                                    Text(period)
                                        .font(.caption.weight(.bold))
                                        .padding(.horizontal, 14)
                                        .padding(.vertical, 7)
                                        .background(selectedPeriod == period ? Color.primaryAccent : Color.clear)
                                        .foregroundColor(selectedPeriod == period ? .appBackground : .textSecondary)
                                        .cornerRadius(8)
                                }
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                    }
                    .background(Color.cardBackground.opacity(0.5))
                    
                    Rectangle().fill(Color.cardBorder.opacity(0.5)).frame(height: 0.5)
                    
                    // S&P 500 benchmark bar + filter button
                    HStack(spacing: 12) {
                        // Filter button
                        Button {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                showFilters.toggle()
                            }
                        } label: {
                            HStack(spacing: 5) {
                                Image(systemName: "slider.horizontal.3")
                                    .font(.caption)
                                Text("Filters")
                                    .font(.caption.weight(.semibold))
                                if activeFilterCount > 0 {
                                    Text("\(activeFilterCount)")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundColor(.appBackground)
                                        .frame(width: 16, height: 16)
                                        .background(Circle().fill(Color.primaryAccent))
                                }
                                Image(systemName: "chevron.down")
                                    .font(.system(size: 9, weight: .bold))
                                    .rotationEffect(.degrees(showFilters ? 180 : 0))
                            }
                            .foregroundColor(activeFilterCount > 0 ? .primaryAccent : .textMuted)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 7)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(activeFilterCount > 0 ? Color.primaryAccent.opacity(0.1) : Color.cardBackground)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(activeFilterCount > 0 ? Color.primaryAccent.opacity(0.3) : Color.cardBorder, lineWidth: 0.5)
                            )
                        }
                        
                        Spacer()
                        
                        // S&P 500 benchmark
                        HStack(spacing: 4) {
                            Text("S&P 500")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(.textMuted)
                            Text(String(format: "%+.2f%%", viewModel.sp500Return))
                                .font(.system(size: 11, weight: .bold, design: .rounded).monospacedDigit())
                                .foregroundColor(viewModel.sp500Return >= 0 ? .gains.opacity(0.7) : .losses.opacity(0.7))
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(
                            Capsule().fill(Color.cardBackground)
                        )
                        .overlay(
                            Capsule().stroke(Color.cardBorder, lineWidth: 0.5)
                        )
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    
                    // Expandable filter panel
                    if showFilters {
                        filterPanel
                    }
                    
                    AccentDivider()
                    
                    // Column headers
                    HStack(spacing: 0) {
                        Text("#")
                            .frame(width: 28, alignment: .center)
                        Text("Trader")
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.leading, 4)
                        Text("Chart")
                            .frame(width: 56, alignment: .center)
                        Text("Subs")
                            .frame(width: 40, alignment: .trailing)
                        Text("Gain")
                            .frame(width: 68, alignment: .trailing)
                    }
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(.textMuted)
                    .tracking(0.3)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .background(Color.cardBackground.opacity(0.3))
                    
                    // Leaderboard list
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
                            message: "Rankings are calculated during market hours. Check back soon!",
                            action: { reloadLeaderboard() }, actionLabel: "Refresh"
                        )
                        Spacer()
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 0) {
                                ForEach(sortedEntries) { entry in
                                    LeaderboardRow(
                                        entry: entry,
                                        isExpanded: expandedEntryId == entry.id,
                                        onTap: {
                                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                                expandedEntryId = expandedEntryId == entry.id ? nil : entry.id
                                            }
                                        }
                                    )
                                    
                                    if entry.id != sortedEntries.last?.id {
                                        AccentDivider().padding(.leading, 42)
                                    }
                                }
                            }
                        }
                        .refreshable {
                            await viewModel.loadLeaderboard(
                                period: selectedPeriod, category: selectedCategory,
                                activeEdge: activeEdge, industry: selectedIndustry,
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
        }
    }
    
    // MARK: - Filter Panel
    private var filterPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Active Edge toggle
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("ACTIVE EDGE™")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                    Text("Hide inactive and one-hit accounts")
                        .font(.system(size: 9))
                        .foregroundColor(.textMuted)
                }
                Spacer()
                Toggle("", isOn: $activeEdge)
                    .labelsHidden()
                    .tint(.primaryAccent)
                    .onChange(of: activeEdge) { _ in reloadLeaderboard() }
            }
            
            AccentDivider()
            
            // Sort by
            VStack(alignment: .leading, spacing: 8) {
                Text("SORT BY")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.textMuted)
                    .tracking(0.5)
                HStack(spacing: 8) {
                    FilterChip(label: "Performance", isSelected: !sortBySubscribers) {
                        sortBySubscribers = false
                    }
                    FilterChip(label: "Most Subscribers", isSelected: sortBySubscribers) {
                        sortBySubscribers = true
                    }
                }
            }
            
            // Category
            VStack(alignment: .leading, spacing: 8) {
                Text("MARKET CAP")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.textMuted)
                    .tracking(0.5)
                HStack(spacing: 8) {
                    ForEach(categories, id: \.key) { cat in
                        FilterChip(label: cat.label, isSelected: selectedCategory == cat.key) {
                            selectedCategory = cat.key
                            reloadLeaderboard()
                        }
                    }
                }
            }
            
            // Frequency
            VStack(alignment: .leading, spacing: 8) {
                Text("TRADING FREQUENCY")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.textMuted)
                    .tracking(0.5)
                HStack(spacing: 8) {
                    ForEach(frequencies, id: \.key) { freq in
                        FilterChip(label: freq.label, isSelected: selectedFrequency == freq.key) {
                            selectedFrequency = freq.key
                            reloadLeaderboard()
                        }
                    }
                }
            }
            
            // Industry (if available)
            if let industries = viewModel.availableIndustries, !industries.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("INDUSTRY")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            FilterChip(label: "All", isSelected: selectedIndustry == "all") {
                                selectedIndustry = "all"
                                reloadLeaderboard()
                            }
                            ForEach(industries, id: \.self) { ind in
                                FilterChip(label: ind, isSelected: selectedIndustry == ind) {
                                    selectedIndustry = ind
                                    reloadLeaderboard()
                                }
                            }
                        }
                    }
                }
            }
            
            // Reset
            if activeFilterCount > 0 {
                Button {
                    selectedCategory = "all"
                    selectedIndustry = "all"
                    selectedFrequency = "any"
                    activeEdge = true
                    sortBySubscribers = false
                    reloadLeaderboard()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.counterclockwise").font(.system(size: 10))
                        Text("Reset all filters").font(.caption)
                    }
                    .foregroundColor(.textMuted)
                }
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.cardBackground)
                .shadow(color: .black.opacity(0.08), radius: 8, y: 4)
        )
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
        .transition(.asymmetric(
            insertion: .opacity.combined(with: .scale(scale: 0.95, anchor: .top)),
            removal: .opacity
        ))
    }
}

// MARK: - Filter Chip

struct FilterChip: View {
    let label: String
    let isSelected: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(isSelected ? Color.primaryAccent : Color.cardBackground)
                .foregroundColor(isSelected ? .appBackground : .textSecondary)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isSelected ? Color.clear : Color.cardBorder, lineWidth: 0.5)
                )
        }
    }
}

// MARK: - Leaderboard Row

struct LeaderboardRow: View {
    let entry: LeaderboardEntry
    let isExpanded: Bool
    let onTap: () -> Void
    @EnvironmentObject var subscriptionManager: SubscriptionManager
    
    var body: some View {
        VStack(spacing: 0) {
            // Compact row (always visible)
            Button(action: onTap) {
                HStack(spacing: 0) {
                    // Rank
                    ZStack {
                        if entry.rank <= 3 {
                            Text(["\u{1F947}", "\u{1F948}", "\u{1F949}"][entry.rank - 1])
                                .font(.system(size: 14))
                        } else {
                            Text("\(entry.rank)")
                                .font(.system(size: 13, weight: .bold, design: .rounded))
                                .foregroundColor(.textSecondary)
                        }
                    }
                    .frame(width: 28)
                    
                    // Username
                    Text(entry.user.username)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.textPrimary)
                        .lineLimit(1)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.leading, 4)
                    
                    // Sparkline
                    SparklineView(
                        dataPoints: entry.sparklineData ?? [],
                        sp500Points: entry.sp500SparklineData ?? [],
                        isPositive: entry.returnPercent >= 0
                    )
                    .frame(width: 56, height: 24)
                    
                    // Subscriber count
                    Text("\(entry.subscriberCount)")
                        .font(.system(size: 11, weight: .medium, design: .rounded).monospacedDigit())
                        .foregroundColor(.textSecondary)
                        .frame(width: 40, alignment: .trailing)
                    
                    // Return percent
                    Text(String(format: "%+.2f%%", entry.returnPercent))
                        .font(.system(size: 13, weight: .bold, design: .rounded).monospacedDigit())
                        .foregroundColor(entry.returnPercent >= 0 ? .gains : .losses)
                        .frame(width: 68, alignment: .trailing)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 11)
                .contentShape(Rectangle())
            }
            .buttonStyle(PlainButtonStyle())
            
            // Expanded detail section
            if isExpanded {
                expandedContent
            }
        }
        .background(isExpanded ? Color.cardBackground.opacity(0.5) : Color.clear)
    }
    
    // MARK: - Expanded Detail
    private var expandedContent: some View {
        VStack(spacing: 12) {
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
                    .fill(Color.cardBackground)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(Color.cardBorder, lineWidth: 0.5)
                    )
            )
            
            // Industry mix (if available)
            if let mix = entry.industryMix, !mix.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("INDUSTRY MIX")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                    
                    HStack(spacing: 6) {
                        ForEach(Array(mix.sorted(by: { $0.value > $1.value }).prefix(4)), id: \.key) { name, pct in
                            HStack(spacing: 3) {
                                Text(name)
                                    .font(.system(size: 9, weight: .medium))
                                    .foregroundColor(.textSecondary)
                                Text(String(format: "%.0f%%", pct))
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundColor(.primaryAccent)
                            }
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                Capsule().fill(Color.primaryAccent.opacity(0.08))
                            )
                        }
                    }
                }
            }
            
            // Subscribe + View buttons
            HStack(spacing: 10) {
                NavigationLink(destination: PortfolioDetailView(slug: entry.user.portfolioSlug ?? "")) {
                    HStack(spacing: 4) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.system(size: 11))
                        Text("View Portfolio")
                            .font(.caption.weight(.semibold))
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
                    Task {
                        await subscriptionManager.subscribe(to: entry.user.id)
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "bell.fill")
                            .font(.system(size: 11))
                        Text("Subscribe $9/mo")
                            .font(.caption.weight(.bold))
                    }
                    .foregroundColor(.appBackground)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(Color.primaryAccent)
                    )
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.bottom, 12)
        .transition(.opacity.combined(with: .move(edge: .top)))
    }
    
    private var statDivider: some View {
        Rectangle()
            .fill(Color.cardBorder)
            .frame(width: 0.5, height: 28)
    }
    
    private func statCell(title: String, value: String) -> some View {
        VStack(spacing: 3) {
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundColor(.textPrimary)
            Text(title)
                .font(.system(size: 8, weight: .medium))
                .foregroundColor(.textMuted)
                .tracking(0.3)
        }
        .frame(maxWidth: .infinity)
    }
    
    private func formatAge(_ days: Int) -> String {
        if days < 30 { return "\(days)d" }
        if days < 365 { return "\(days / 30)mo" }
        return "\(days / 365)y"
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
