import SwiftUI

struct SubscriptionsView: View {
    @StateObject private var viewModel = SubscriptionsViewModel()
    
    var body: some View {
        NavigationView {
            List {
                if viewModel.subscriptions.isEmpty && !viewModel.isLoading {
                    VStack(spacing: 16) {
                        Image(systemName: "bell.slash")
                            .font(.system(size: 50))
                            .foregroundColor(.secondary)
                        Text("No Subscriptions")
                            .font(.title2.bold())
                        Text("Subscribe to traders from the leaderboard to get real-time alerts when they trade.")
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()
                    .listRowBackground(Color.clear)
                } else {
                    ForEach(viewModel.subscriptions) { subscription in
                        if let owner = subscription.portfolioOwner {
                            NavigationLink(destination: PortfolioDetailView(slug: owner.portfolioSlug ?? "")) {
                                SubscriptionRow(subscription: subscription, viewModel: viewModel)
                            }
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Following")
            .refreshable {
                await viewModel.loadSubscriptions()
            }
            .task {
                if viewModel.subscriptions.isEmpty {
                    await viewModel.loadSubscriptions()
                }
            }
            .overlay {
                if viewModel.isLoading && viewModel.subscriptions.isEmpty {
                    ProgressView()
                }
            }
        }
    }
}

struct SubscriptionRow: View {
    let subscription: SubscriptionMade
    @ObservedObject var viewModel: SubscriptionsViewModel
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(subscription.portfolioOwner?.username ?? "Unknown")
                    .font(.headline)
                
                HStack {
                    Text(subscription.status.capitalized)
                        .font(.caption)
                        .foregroundColor(subscription.status == "active" ? .green : .secondary)
                    
                    if let expires = subscription.expiresAt {
                        Text("• Expires \(formatDate(expires))")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            
            Spacer()
            
            // Notification toggle
            Toggle("", isOn: Binding(
                get: { subscription.pushNotificationsEnabled },
                set: { newValue in
                    Task {
                        await viewModel.toggleNotifications(subscriptionId: subscription.id, enabled: newValue)
                    }
                }
            ))
            .labelsHidden()
        }
        .padding(.vertical, 4)
    }
    
    private func formatDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: dateString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateStyle = .short
            return displayFormatter.string(from: date)
        }
        return dateString
    }
}

@MainActor
class SubscriptionsViewModel: ObservableObject {
    @Published var subscriptions: [SubscriptionMade] = []
    @Published var isLoading = false
    @Published var error: String?
    
    func loadSubscriptions() async {
        isLoading = true
        
        do {
            let response = try await APIService.shared.getSubscriptions()
            subscriptions = response.subscriptionsMade
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
    
    func toggleNotifications(subscriptionId: Int, enabled: Bool) async {
        do {
            try await APIService.shared.updateNotificationSettings(subscriptionId: subscriptionId, enabled: enabled)
            
            if let index = subscriptions.firstIndex(where: { $0.id == subscriptionId }) {
                var updated = subscriptions[index]
                subscriptions[index] = SubscriptionMade(
                    id: updated.id,
                    portfolioOwner: updated.portfolioOwner,
                    status: updated.status,
                    expiresAt: updated.expiresAt,
                    pushNotificationsEnabled: enabled
                )
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct SubscriptionsView_Previews: PreviewProvider {
    static var previews: some View {
        SubscriptionsView()
            .environmentObject(SubscriptionManager())
    }
}
