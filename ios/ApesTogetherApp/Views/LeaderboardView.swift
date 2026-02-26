import SwiftUI
import Combine

struct LeaderboardView: View {
    @StateObject private var viewModel = LeaderboardViewModel()
    @State private var selectedPeriod = "7D"
    
    let periods = ["1D", "5D", "7D", "1M", "3M", "YTD", "1Y"]
    
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
            .navigationTitle("Leaderboard")
            .onAppear {
                if viewModel.entries.isEmpty {
                    Task {
                        await viewModel.loadLeaderboard(period: selectedPeriod)
                    }
                }
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
    
    func loadLeaderboard(period: String) async {
        isLoading = true
        error = nil
        
        do {
            let response = try await APIService.shared.getLeaderboard(period: period)
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
