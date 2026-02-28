import SwiftUI
import Combine

struct SubscriptionsView: View {
    @StateObject private var viewModel = SubscriptionsViewModel()
    @State private var showSettings = false
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: 24) {
                        // My Subscribers section
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                SectionHeader(title: "My Subscribers")
                                Spacer()
                                Text("\(viewModel.subscriberCount)")
                                    .font(.title2.bold())
                                    .foregroundColor(.primaryAccent)
                            }
                            
                            if viewModel.subscribers.isEmpty {
                                HStack {
                                    Image(systemName: "person.badge.plus")
                                        .foregroundColor(.primaryAccent.opacity(0.6))
                                        .font(.title3)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("No subscribers yet")
                                            .font(.subheadline.weight(.medium))
                                            .foregroundColor(.textPrimary)
                                        Text("Share your portfolio to attract subscribers")
                                            .font(.caption)
                                            .foregroundColor(.textSecondary)
                                    }
                                    Spacer()
                                }
                                .padding()
                                .cardStyle(padding: 0)
                            } else {
                                VStack(spacing: 0) {
                                    ForEach(viewModel.subscribers) { sub in
                                        HStack {
                                            Image(systemName: "person.circle.fill")
                                                .foregroundColor(.primaryAccent)
                                                .font(.title3)
                                            Text(sub.subscriber?.username ?? "User")
                                                .font(.subheadline.weight(.medium))
                                                .foregroundColor(.textPrimary)
                                            Spacer()
                                            Text("Since \(formatShortDate(sub.createdAt))")
                                                .font(.caption)
                                                .foregroundColor(.textMuted)
                                        }
                                        .padding()
                                        if sub.id != viewModel.subscribers.last?.id {
                                            AccentDivider()
                                        }
                                    }
                                }
                                .cardStyle(padding: 0)
                            }
                        }
                        
                        // My Subscriptions section
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "My Subscriptions")
                            
                            if viewModel.subscriptions.isEmpty {
                                HStack {
                                    Image(systemName: "star.circle")
                                        .foregroundColor(.primaryAccent.opacity(0.6))
                                        .font(.title3)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("No subscriptions yet")
                                            .font(.subheadline.weight(.medium))
                                            .foregroundColor(.textPrimary)
                                        Text("Subscribe to traders from the leaderboard to get real-time alerts")
                                            .font(.caption)
                                            .foregroundColor(.textSecondary)
                                    }
                                    Spacer()
                                }
                                .padding()
                                .cardStyle(padding: 0)
                            } else {
                                VStack(spacing: 0) {
                                    ForEach(viewModel.subscriptions) { subscription in
                                        if let owner = subscription.portfolioOwner {
                                            NavigationLink(destination: PortfolioDetailView(slug: owner.portfolioSlug ?? "")) {
                                                SubscriptionRow(subscription: subscription, viewModel: viewModel)
                                            }
                                            .buttonStyle(PlainButtonStyle())
                                            if subscription.id != viewModel.subscriptions.last?.id {
                                                AccentDivider()
                                            }
                                        }
                                    }
                                }
                                .cardStyle(padding: 0)
                            }
                        }
                    }
                    .padding()
                }
                .refreshable {
                    await viewModel.loadSubscriptions()
                }
            }
            .appNavBar(showSettings: $showSettings)
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
            .onAppear {
                if viewModel.subscriptions.isEmpty && viewModel.subscribers.isEmpty {
                    Task {
                        await viewModel.loadSubscriptions()
                    }
                }
            }
            .overlay(
                Group {
                    if viewModel.isLoading && viewModel.subscriptions.isEmpty && viewModel.subscribers.isEmpty {
                        ProgressView()
                            .tint(.primaryAccent)
                    }
                }
            )
        }
    }
    
    private func formatShortDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: dateString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateFormat = "MMM d"
            return displayFormatter.string(from: date)
        }
        return dateString
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
    @Published var subscribers: [Subscriber] = []
    @Published var subscriberCount: Int = 0
    @Published var isLoading = false
    @Published var error: String?
    
    func loadSubscriptions() async {
        isLoading = true
        
        do {
            let response = try await APIService.shared.getSubscriptions()
            subscriptions = response.subscriptionsMade
            subscribers = response.subscribers
            subscriberCount = response.subscriberCount
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
