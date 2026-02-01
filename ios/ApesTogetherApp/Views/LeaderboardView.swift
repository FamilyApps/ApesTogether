import SwiftUI

struct LeaderboardView: View {
    @StateObject private var viewModel = LeaderboardViewModel()
    @State private var selectedPeriod = "7D"
    
    let periods = ["1D", "5D", "7D", "1M", "3M", "YTD", "1Y"]
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Period selector
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(periods, id: \.self) { period in
                            Button {
                                selectedPeriod = period
                                Task {
                                    await viewModel.loadLeaderboard(period: period)
                                }
                            } label: {
                                Text(period)
                                    .font(.subheadline.weight(.semibold))
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 8)
                                    .background(selectedPeriod == period ? Color.green : Color.gray.opacity(0.2))
                                    .foregroundColor(selectedPeriod == period ? .white : .primary)
                                    .cornerRadius(20)
                            }
                        }
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 12)
                }
                .background(Color(.systemBackground))
                
                Divider()
                
                // Leaderboard list
                if viewModel.isLoading && viewModel.entries.isEmpty {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if let error = viewModel.error {
                    Spacer()
                    Text(error)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        Task {
                            await viewModel.loadLeaderboard(period: selectedPeriod)
                        }
                    }
                    .padding()
                    Spacer()
                } else {
                    List(viewModel.entries) { entry in
                        NavigationLink(destination: PortfolioDetailView(slug: entry.user.portfolioSlug ?? "")) {
                            LeaderboardRow(entry: entry)
                        }
                    }
                    .listStyle(.plain)
                    .refreshable {
                        await viewModel.loadLeaderboard(period: selectedPeriod)
                    }
                }
            }
            .navigationTitle("Leaderboard")
            .task {
                if viewModel.entries.isEmpty {
                    await viewModel.loadLeaderboard(period: selectedPeriod)
                }
            }
        }
    }
}

struct LeaderboardRow: View {
    let entry: LeaderboardEntry
    
    var body: some View {
        HStack(spacing: 12) {
            // Rank
            Text("\(entry.rank)")
                .font(.headline)
                .foregroundColor(.secondary)
                .frame(width: 30)
            
            // User info
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.user.username)
                    .font(.headline)
                
                HStack(spacing: 4) {
                    Image(systemName: "person.2.fill")
                        .font(.caption2)
                    Text("\(entry.subscriberCount)")
                        .font(.caption)
                }
                .foregroundColor(.secondary)
            }
            
            Spacer()
            
            // Return percentage
            Text(String(format: "%+.2f%%", entry.returnPercent))
                .font(.headline.monospacedDigit())
                .foregroundColor(entry.returnPercent >= 0 ? .green : .red)
        }
        .padding(.vertical, 4)
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
