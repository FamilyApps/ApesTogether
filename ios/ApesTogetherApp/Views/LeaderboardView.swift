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
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // Period selector
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(periods, id: \.self) { period in
                                Button {
                                    selectedPeriod = period
                                    Task {
                                        await viewModel.loadLeaderboard(period: period)
                                    }
                                } label: {
                                    Text(period)
                                }
                                .buttonStyle(PillButtonStyle(isSelected: selectedPeriod == period))
                            }
                        }
                        .padding(.horizontal)
                        .padding(.vertical, 12)
                    }
                    
                    // Filter toggle + category pills
                    HStack {
                        Button {
                            withAnimation(.easeInOut(duration: 0.25)) {
                                showFilters.toggle()
                            }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "line.3.horizontal.decrease.circle\(showFilters ? ".fill" : "")")
                                Text("Filters")
                                    .font(.subheadline.weight(.medium))
                                if selectedCategory != "all" {
                                    Circle()
                                        .fill(Color.primaryAccent)
                                        .frame(width: 6, height: 6)
                                }
                            }
                            .foregroundColor(showFilters ? .primaryAccent : .textSecondary)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(
                                Capsule()
                                    .fill(showFilters ? Color.primaryAccent.opacity(0.12) : Color.cardBackground)
                            )
                            .overlay(
                                Capsule()
                                    .stroke(showFilters ? Color.primaryAccent.opacity(0.3) : Color.cardBorder, lineWidth: 1)
                            )
                        }
                        
                        Spacer()
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 8)
                    
                    if showFilters {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Category")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.textMuted)
                            
                            HStack(spacing: 10) {
                                ForEach(categories, id: \.key) { cat in
                                    Button {
                                        selectedCategory = cat.key
                                        Task {
                                            await viewModel.loadLeaderboard(period: selectedPeriod, category: selectedCategory)
                                        }
                                    } label: {
                                        Text(cat.label)
                                    }
                                    .buttonStyle(PillButtonStyle(isSelected: selectedCategory == cat.key))
                                }
                            }
                        }
                        .padding(.horizontal)
                        .padding(.bottom, 12)
                        .transition(.opacity.combined(with: .move(edge: .top)))
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
                                    await viewModel.loadLeaderboard(period: selectedPeriod)
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
                            await viewModel.loadLeaderboard(period: selectedPeriod)
                        }
                    }
                }
            }
            .appNavBar(showSettings: $showSettings)
            .onAppear {
                if viewModel.entries.isEmpty {
                    Task {
                        await viewModel.loadLeaderboard(period: selectedPeriod)
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
