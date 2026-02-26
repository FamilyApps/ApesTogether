import SwiftUI
import Combine

struct SubscriptionsView: View {
    @StateObject private var viewModel = SubscriptionsViewModel()
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                if viewModel.subscriptions.isEmpty && !viewModel.isLoading {
                    EmptyStateView(
                        icon: "bell.slash",
                        title: "No Subscriptions",
                        message: "Subscribe to traders from the leaderboard to get real-time alerts when they trade."
                    )
                } else {
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(viewModel.subscriptions) { subscription in
                                if let owner = subscription.portfolioOwner {
                                    NavigationLink(destination: PortfolioDetailView(slug: owner.portfolioSlug ?? "")) {
                                        SubscriptionRow(subscription: subscription, viewModel: viewModel)
                                    }
                                    .buttonStyle(PlainButtonStyle())
                                }
                            }
                        }
                        .padding()
                    }
                    .refreshable {
                        await viewModel.loadSubscriptions()
                    }
                }
            }
            .navigationTitle("Following")
            .onAppear {
                if viewModel.subscriptions.isEmpty {
                    Task {
                        await viewModel.loadSubscriptions()
                    }
                }
            }
            .overlay(
                Group {
                    if viewModel.isLoading && viewModel.subscriptions.isEmpty {
                        ProgressView()
                            .tint(.primaryAccent)
                    }
                }
            )
        }
    }
}

struct SubscriptionRow: View {
    let subscription: SubscriptionMade
    @ObservedObject var viewModel: SubscriptionsViewModel
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 6) {
                Text(subscription.portfolioOwner?.username ?? "Unknown")
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                
                HStack(spacing: 8) {
                    StatusBadge(
                        text: subscription.status.capitalized,
                        color: subscription.status == "active" ? .gains : .textSecondary
                    )
                    
                    if let expires = subscription.expiresAt {
                        Text("Expires \(formatDate(expires))")
                            .font(.caption)
                            .foregroundColor(.textMuted)
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
            .toggleStyle(SwitchToggleStyle(tint: Color.primaryAccent))
            .labelsHidden()
        }
        .padding()
        .cardStyle(padding: 0)
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
                let updated = subscriptions[index]
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
