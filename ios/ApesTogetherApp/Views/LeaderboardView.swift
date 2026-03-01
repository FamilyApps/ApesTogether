import SwiftUI
import Combine

struct LeaderboardView: View {
    @StateObject private var viewModel = LeaderboardViewModel()
    @State private var selectedPeriod = "7D"
    @State private var selectedCategory = "all"
    @State private var showFilters = false
    @State private var showSettings = false
    
    let periods = ["1D", "5D", "7D", "1M", "3M", "YTD", "1Y"]
    let categories: [(key: String, label: String)] = [
        ("all", "All"),
        ("large_cap", "Large Cap"),
        ("small_cap", "Small Cap")
    ]
    
    init() {
        // Configure navigation bar appearance
        let appearance = UINavigationBarAppearance()
        appearance.configureWithOpaqueBackground()
        appearance.backgroundColor = UIColor(Color.appBackground)
        appearance.titleTextAttributes = [.foregroundColor: UIColor(Color.textPrimary)]
        appearance.largeTitleTextAttributes = [.foregroundColor: UIColor(Color.textPrimary)]
        UINavigationBar.appearance().standardAppearance = appearance
        UINavigationBar.appearance().scrollEdgeAppearance = appearance
    }
    
    private var activeFilterCount: Int {
        selectedCategory != "all" ? 1 : 0
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // Time period segmented control
                    VStack(spacing: 0) {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(periods, id: \.self) { period in
                                    Button {
                                        selectedPeriod = period
                                        Task {
                                            await viewModel.loadLeaderboard(period: period, category: selectedCategory)
                                        }
                                    } label: {
                                        Text(period)
                                            .font(.caption.weight(.bold))
                                            .padding(.horizontal, 14)
                                            .padding(.vertical, 7)
                                            .background(
                                                selectedPeriod == period
                                                    ? Color.primaryAccent
                                                    : Color.clear
                                            )
                                            .foregroundColor(
                                                selectedPeriod == period
                                                    ? .appBackground
                                                    : .textSecondary
                                            )
                                            .cornerRadius(8)
                                    }
                                }
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                        }
                        .background(Color.cardBackground.opacity(0.5))
                        
                        // Thin separator
                        Rectangle()
                            .fill(Color.cardBorder.opacity(0.5))
                            .frame(height: 0.5)
                    }
                    
                    // Filter bar — visually separated
                    HStack(spacing: 12) {
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
                        
                        // Active filter chips (shown inline when filter is applied)
                        if activeFilterCount > 0 && !showFilters {
                            HStack(spacing: 6) {
                                let label = categories.first(where: { $0.key == selectedCategory })?.label ?? ""
                                HStack(spacing: 4) {
                                    Text(label)
                                        .font(.caption.weight(.medium))
                                    Button {
                                        selectedCategory = "all"
                                        Task {
                                            await viewModel.loadLeaderboard(period: selectedPeriod, category: "all")
                                        }
                                    } label: {
                                        Image(systemName: "xmark")
                                            .font(.system(size: 8, weight: .bold))
                                    }
                                }
                                .foregroundColor(.primaryAccent)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(
                                    Capsule().fill(Color.primaryAccent.opacity(0.1))
                                )
                            }
                        }
                        
                        Spacer()
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    
                    // Expandable filter panel
                    if showFilters {
                        VStack(alignment: .leading, spacing: 14) {
                            // Category filter
                            VStack(alignment: .leading, spacing: 8) {
                                Text("PORTFOLIO TYPE")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundColor(.textMuted)
                                    .tracking(0.5)
                                
                                HStack(spacing: 8) {
                                    ForEach(categories, id: \.key) { cat in
                                        Button {
                                            selectedCategory = cat.key
                                            Task {
                                                await viewModel.loadLeaderboard(period: selectedPeriod, category: selectedCategory)
                                            }
                                        } label: {
                                            Text(cat.label)
                                                .font(.caption.weight(.semibold))
                                                .padding(.horizontal, 14)
                                                .padding(.vertical, 7)
                                                .background(
                                                    selectedCategory == cat.key
                                                        ? Color.primaryAccent
                                                        : Color.cardBackground
                                                )
                                                .foregroundColor(
                                                    selectedCategory == cat.key
                                                        ? .appBackground
                                                        : .textSecondary
                                                )
                                                .cornerRadius(8)
                                                .overlay(
                                                    RoundedRectangle(cornerRadius: 8)
                                                        .stroke(
                                                            selectedCategory == cat.key ? Color.clear : Color.cardBorder,
                                                            lineWidth: 0.5
                                                        )
                                                )
                                        }
                                    }
                                }
                            }
                            
                            // Reset button
                            if activeFilterCount > 0 {
                                Button {
                                    selectedCategory = "all"
                                    Task {
                                        await viewModel.loadLeaderboard(period: selectedPeriod, category: "all")
                                    }
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
                    
                    // Leaderboard list
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
                                Task {
                                    await viewModel.loadLeaderboard(period: selectedPeriod, category: selectedCategory)
                                }
                            },
                            actionLabel: "Retry"
                        )
                        Spacer()
                    } else if viewModel.entries.isEmpty {
                        Spacer()
                        EmptyStateView(
                            icon: "trophy",
                            title: "Leaderboard Coming Soon",
                            message: "As traders join and add their portfolios, the leaderboard will populate. Add your stocks to be among the first!"
                        )
                        Spacer()
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 0) {
                                ForEach(viewModel.entries) { entry in
                                    NavigationLink(destination: PortfolioDetailView(slug: entry.user.portfolioSlug ?? "")) {
                                        LeaderboardRow(entry: entry)
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
                            await viewModel.loadLeaderboard(period: selectedPeriod, category: selectedCategory)
                        }
                    }
                }
            }
            .appNavBar(showSettings: $showSettings)
            .onAppear {
                if viewModel.entries.isEmpty {
                    Task {
                        await viewModel.loadLeaderboard(period: selectedPeriod, category: selectedCategory)
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
        }
    }
}

struct LeaderboardRow: View {
    let entry: LeaderboardEntry
    
    var body: some View {
        HStack(spacing: 12) {
            // Rank badge
            ZStack {
                Circle()
                    .fill(entry.rank <= 3 ? Color.primaryAccent.opacity(0.15) : Color.cardBackground)
                    .frame(width: 36, height: 36)
                
                Text("\(entry.rank)")
                    .font(.subheadline.weight(.bold))
                    .foregroundColor(entry.rank <= 3 ? .primaryAccent : .textSecondary)
            }
            
            // User info
            VStack(alignment: .leading, spacing: 4) {
                Text(entry.user.username)
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                
                HStack(spacing: 4) {
                    Image(systemName: "person.2.fill")
                        .font(.caption2)
                    Text("\(entry.subscriberCount)")
                        .font(.caption)
                }
                .foregroundColor(.textSecondary)
            }
            
            Spacer()
            
            // Return percentage
            Text(String(format: "%+.2f%%", entry.returnPercent))
                .font(.headline.monospacedDigit())
                .foregroundColor(entry.returnPercent >= 0 ? .gains : .losses)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    Capsule()
                        .fill((entry.returnPercent >= 0 ? Color.gains : Color.losses).opacity(0.15))
                )
        }
        .padding(.horizontal)
        .padding(.vertical, 12)
    }
}

@MainActor
class LeaderboardViewModel: ObservableObject {
    @Published var entries: [LeaderboardEntry] = []
    @Published var isLoading = false
    @Published var error: String?
    
    func loadLeaderboard(period: String, category: String = "all") async {
        isLoading = true
        error = nil
        
        do {
            let response = try await APIService.shared.getLeaderboard(period: period, category: category)
            entries = response.entries
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
