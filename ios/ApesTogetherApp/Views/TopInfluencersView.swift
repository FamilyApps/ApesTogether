import SwiftUI
import Combine
import Charts

struct TopInfluencersView: View {
    @StateObject private var viewModel = TopInfluencersViewModel()
    @State private var selectedIndustry = "all"
    @State private var showFilters = false
    @State private var showSettings = false
    
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
        selectedIndustry != "all" ? 1 : 0
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // Header
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Top Influencers")
                                .font(.title3.bold())
                                .foregroundColor(.textPrimary)
                            Text("Ranked by subscriber count")
                                .font(.caption)
                                .foregroundColor(.textMuted)
                        }
                        Spacer()
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(Color.cardBackground.opacity(0.5))
                    
                    Rectangle()
                        .fill(Color.cardBorder.opacity(0.5))
                        .frame(height: 0.5)
                    
                    // Filter bar
                    HStack(spacing: 12) {
                        Button {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                showFilters.toggle()
                            }
                        } label: {
                            HStack(spacing: 5) {
                                Image(systemName: "slider.horizontal.3")
                                    .font(.caption)
                                Text("Industry")
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
                        
                        // Active filter chip
                        if activeFilterCount > 0 && !showFilters {
                            HStack(spacing: 4) {
                                Text(selectedIndustry)
                                    .font(.caption.weight(.medium))
                                Button {
                                    selectedIndustry = "all"
                                    Task { await viewModel.loadInfluencers(industry: "all") }
                                } label: {
                                    Image(systemName: "xmark")
                                        .font(.system(size: 8, weight: .bold))
                                }
                            }
                            .foregroundColor(.primaryAccent)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(Capsule().fill(Color.primaryAccent.opacity(0.1)))
                        }
                        
                        Spacer()
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    
                    // Expandable filter panel
                    if showFilters {
                        VStack(alignment: .leading, spacing: 14) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("INDUSTRY")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundColor(.textMuted)
                                    .tracking(0.5)
                                
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 8) {
                                        IndustryFilterChip(label: "All", isSelected: selectedIndustry == "all") {
                                            selectedIndustry = "all"
                                            Task { await viewModel.loadInfluencers(industry: "all") }
                                        }
                                        
                                        ForEach(viewModel.availableIndustries, id: \.self) { industry in
                                            IndustryFilterChip(label: industry, isSelected: selectedIndustry == industry) {
                                                selectedIndustry = industry
                                                Task { await viewModel.loadInfluencers(industry: industry) }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            if activeFilterCount > 0 {
                                Button {
                                    selectedIndustry = "all"
                                    Task { await viewModel.loadInfluencers(industry: "all") }
                                } label: {
                                    HStack(spacing: 4) {
                                        Image(systemName: "arrow.counterclockwise")
                                            .font(.system(size: 10))
                                        Text("Reset filters")
                                            .font(.caption)
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
                    
                    AccentDivider()
                    
                    // List
                    if viewModel.isLoading && viewModel.entries.isEmpty {
                        Spacer()
                        ProgressView()
                            .tint(.primaryAccent)
                        Spacer()
                    } else if let error = viewModel.error {
                        Spacer()
                        EmptyStateView(
                            icon: "exclamationmark.triangle",
                            title: "Error",
                            message: error,
                            action: {
                                Task { await viewModel.loadInfluencers(industry: selectedIndustry) }
                            },
                            actionLabel: "Retry"
                        )
                        Spacer()
                    } else if viewModel.entries.isEmpty {
                        Spacer()
                        EmptyStateView(
                            icon: "star.circle",
                            title: "No Influencers Yet",
                            message: "As traders gain subscribers, the top influencers will appear here. Share your portfolio to be the first!"
                        )
                        Spacer()
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 0) {
                                ForEach(viewModel.entries) { entry in
                                    NavigationLink(destination: PortfolioDetailView(slug: entry.user.portfolioSlug ?? "")) {
                                        InfluencerRow(entry: entry)
                                    }
                                    .buttonStyle(PlainButtonStyle())
                                    
                                    if entry.id != viewModel.entries.last?.id {
                                        AccentDivider()
                                            .padding(.leading, 50)
                                    }
                                }
                            }
                            .padding(.top, 8)
                        }
                        .refreshable {
                            await viewModel.loadInfluencers(industry: selectedIndustry)
                        }
                    }
                }
            }
            .appNavBar(showSettings: $showSettings)
            .onAppear {
                if viewModel.entries.isEmpty {
                    Task { await viewModel.loadInfluencers(industry: selectedIndustry) }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
        }
    }
}

// MARK: - Industry Filter Chip

struct IndustryFilterChip: View {
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

// MARK: - Influencer Row

struct InfluencerRow: View {
    let entry: InfluencerEntry
    
    var body: some View {
        HStack(spacing: 12) {
            // Rank badge
            ZStack {
                Circle()
                    .fill(entry.rank <= 3 ? Color.primaryAccent.opacity(0.15) : Color.cardBackground)
                    .frame(width: 36, height: 36)
                
                if entry.rank <= 3 {
                    Text(["\u{1F947}", "\u{1F948}", "\u{1F949}"][entry.rank - 1])
                        .font(.system(size: 16))
                } else {
                    Text("\(entry.rank)")
                        .font(.subheadline.weight(.bold))
                        .foregroundColor(.textSecondary)
                }
            }
            
            // User info
            VStack(alignment: .leading, spacing: 4) {
                Text(entry.user.username)
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(.textPrimary)
                    .lineLimit(1)
                
                // Industry tags
                if !entry.topIndustries.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(entry.topIndustries.prefix(2)) { industry in
                            Text(shortenIndustry(industry.name))
                                .font(.system(size: 9, weight: .medium))
                                .foregroundColor(.primaryAccent)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(
                                    Capsule().fill(Color.primaryAccent.opacity(0.1))
                                )
                        }
                    }
                } else {
                    HStack(spacing: 4) {
                        Image(systemName: "chart.bar.fill")
                            .font(.system(size: 8))
                        Text("\(entry.uniqueStocks) stocks")
                            .font(.caption2)
                    }
                    .foregroundColor(.textMuted)
                }
            }
            
            Spacer()
            
            // Subscriber count
            VStack(alignment: .trailing, spacing: 2) {
                HStack(spacing: 4) {
                    Image(systemName: "person.2.fill")
                        .font(.system(size: 10))
                    Text("\(entry.subscriberCount)")
                        .font(.system(size: 16, weight: .bold, design: .rounded).monospacedDigit())
                }
                .foregroundColor(.primaryAccent)
                
                Text("subscribers")
                    .font(.system(size: 9))
                    .foregroundColor(.textMuted)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
    }
    
    private func shortenIndustry(_ name: String) -> String {
        let map: [String: String] = [
            "AUTO MANUFACTURERS": "Auto",
            "CONSUMER ELECTRONICS": "Tech",
            "SOFTWARE": "Software",
            "SEMICONDUCTORS": "Chips",
            "INTERNET": "Internet",
            "BANKS": "Finance",
            "CREDIT SERVICES": "Finance",
            "INSURANCE": "Insurance",
            "DRUG MANUFACTURERS": "Pharma",
            "HEALTHCARE PLANS": "Health",
            "ETF - Index Fund": "ETF",
            "TECHNOLOGY": "Tech",
            "FINANCIAL": "Finance",
            "HEALTHCARE": "Health",
        ]
        
        for (key, short) in map {
            if name.uppercased().contains(key.uppercased()) {
                return short
            }
        }
        
        // Truncate long names
        if name.count > 10 {
            return String(name.prefix(8)) + "…"
        }
        return name
    }
}

// MARK: - View Model

@MainActor
class TopInfluencersViewModel: ObservableObject {
    @Published var entries: [InfluencerEntry] = []
    @Published var availableIndustries: [String] = []
    @Published var isLoading = false
    @Published var error: String?
    
    func loadInfluencers(industry: String = "all") async {
        isLoading = true
        error = nil
        
        do {
            let response = try await APIService.shared.getTopInfluencers(industry: industry)
            entries = response.entries
            // Only update available industries on first load (unfiltered)
            if industry == "all" || availableIndustries.isEmpty {
                availableIndustries = response.availableIndustries
            }
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
}

struct TopInfluencersView_Previews: PreviewProvider {
    static var previews: some View {
        TopInfluencersView()
    }
}
