import SwiftUI
import Combine

struct SubscriptionsView: View {
    @StateObject private var viewModel = SubscriptionsViewModel()
    @State private var showSettings = false
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 0) {
                    AppHeaderRow(showSettings: $showSettings)
                    
                    ScrollView {
                        VStack(spacing: 24) {
                            // ── My Subscribers (creator view) ──
                            subscribersSection
                            
                            // ── My Subscriptions (subscriber view) ──
                            subscriptionsSection
                            
                            // ── Trade Notification History ──
                            notificationHistorySection
                        }
                        .padding()
                    }
                    .refreshable {
                        await viewModel.loadAll()
                    }
                }
            }
            .appNavBar(showSettings: $showSettings)
            .sheet(isPresented: $showSettings) { SettingsView() }
            .alert("Cancel Subscription", isPresented: $viewModel.showCancelConfirm) {
                Button("Keep Subscription", role: .cancel) {}
                Button("Cancel", role: .destructive) {
                    if let id = viewModel.pendingCancelId {
                        Task { await viewModel.cancelSubscription(id: id) }
                    }
                }
            } message: {
                Text("You'll lose access to this trader's portfolio and trade alerts. You can resubscribe anytime.")
            }
            .onAppear {
                if viewModel.subscriptions.isEmpty && viewModel.subscribers.isEmpty {
                    Task { await viewModel.loadAll() }
                }
            }
            .overlay(
                Group {
                    if viewModel.isLoading && viewModel.subscriptions.isEmpty && viewModel.subscribers.isEmpty {
                        ProgressView().tint(.primaryAccent)
                    }
                }
            )
        }
    }
    
    // MARK: - Subscribers Section
    
    private var subscribersSection: some View {
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
    }
    
    // MARK: - Subscriptions Section
    
    private var subscriptionsSection: some View {
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
                VStack(spacing: 10) {
                    ForEach(viewModel.subscriptions) { subscription in
                        SubscriptionCard(
                            subscription: subscription,
                            viewModel: viewModel
                        )
                    }
                }
            }
        }
    }
    
    // MARK: - Notification History Section
    
    private var notificationHistorySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: "Trade Alerts")
            
            if viewModel.notifications.isEmpty {
                HStack {
                    Image(systemName: "bell.slash")
                        .foregroundColor(.primaryAccent.opacity(0.6))
                        .font(.title3)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("No trade alerts yet")
                            .font(.subheadline.weight(.medium))
                            .foregroundColor(.textPrimary)
                        Text("You'll see trade notifications from your subscriptions here")
                            .font(.caption)
                            .foregroundColor(.textSecondary)
                    }
                    Spacer()
                }
                .padding()
                .cardStyle(padding: 0)
            } else {
                VStack(spacing: 0) {
                    ForEach(viewModel.notifications) { notif in
                        HStack(spacing: 10) {
                            Image(systemName: notif.type == "push" ? "bell.fill" : "envelope.fill")
                                .font(.system(size: 13))
                                .foregroundColor(.primaryAccent)
                                .frame(width: 28)
                            
                            VStack(alignment: .leading, spacing: 3) {
                                if let body = notif.body, !body.isEmpty {
                                    Text(body)
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundColor(.textPrimary)
                                        .lineLimit(2)
                                } else {
                                    Text("Trade alert from \(notif.traderUsername)")
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundColor(.textPrimary)
                                }
                                
                                HStack(spacing: 6) {
                                    Text(notif.traderUsername)
                                        .font(.system(size: 11, weight: .semibold))
                                        .foregroundColor(.primaryAccent)
                                    if let date = notif.createdAt {
                                        Text(formatRelativeDate(date))
                                            .font(.system(size: 10))
                                            .foregroundColor(.textMuted)
                                    }
                                }
                            }
                            
                            Spacer()
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        
                        if notif.id != viewModel.notifications.last?.id {
                            AccentDivider()
                        }
                    }
                }
                .cardStyle(padding: 0)
            }
        }
    }
    
    // MARK: - Helpers
    
    private func formatShortDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: dateString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateFormat = "MMM d"
            return displayFormatter.string(from: date)
        }
        return dateString
    }
    
    private func formatRelativeDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: dateString) else { return dateString }
        let interval = Date().timeIntervalSince(date)
        if interval < 60 { return "just now" }
        if interval < 3600 { return "\(Int(interval / 60))m ago" }
        if interval < 86400 { return "\(Int(interval / 3600))h ago" }
        if interval < 604800 { return "\(Int(interval / 86400))d ago" }
        let displayFormatter = DateFormatter()
        displayFormatter.dateFormat = "MMM d"
        return displayFormatter.string(from: date)
    }
}

// MARK: - Subscription Card

struct SubscriptionCard: View {
    let subscription: SubscriptionMade
    @ObservedObject var viewModel: SubscriptionsViewModel
    
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "person.circle.fill")
                    .foregroundColor(.primaryAccent)
                    .font(.system(size: 28))
                
                VStack(alignment: .leading, spacing: 4) {
                    Text(subscription.portfolioOwner?.username ?? "Unknown")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.textPrimary)
                    
                    HStack(spacing: 8) {
                        StatusBadge(
                            text: subscription.status.capitalized,
                            color: subscription.status == "active" ? .gains : .textSecondary
                        )
                        if let expires = subscription.expiresAt {
                            Text("Renews \(formatDate(expires))")
                                .font(.system(size: 11))
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
            .padding(14)
            
            AccentDivider()
            
            // Action buttons
            HStack(spacing: 0) {
                if let owner = subscription.portfolioOwner {
                    NavigationLink(destination: PortfolioDetailView(slug: owner.portfolioSlug ?? "")) {
                        HStack(spacing: 5) {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .font(.system(size: 11))
                            Text("View Portfolio")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        .foregroundColor(.primaryAccent)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                    }
                }
                
                Rectangle().fill(Color.cardBorder.opacity(0.4)).frame(width: 0.5, height: 20)
                
                Button {
                    viewModel.pendingCancelId = subscription.id
                    viewModel.showCancelConfirm = true
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "xmark.circle")
                            .font(.system(size: 11))
                        Text("Cancel")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(.textMuted)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                }
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.cardBackground)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.cardBorder.opacity(0.4), lineWidth: 0.5)
        )
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

// MARK: - View Model

@MainActor
class SubscriptionsViewModel: ObservableObject {
    @Published var subscriptions: [SubscriptionMade] = []
    @Published var subscribers: [Subscriber] = []
    @Published var subscriberCount: Int = 0
    @Published var notifications: [NotificationItem] = []
    @Published var isLoading = false
    @Published var error: String?
    @Published var showCancelConfirm = false
    var pendingCancelId: Int?
    
    func loadAll() async {
        isLoading = true
        await loadSubscriptions()
        await loadNotifications()
        isLoading = false
    }
    
    func loadSubscriptions() async {
        do {
            let response = try await APIService.shared.getSubscriptions()
            subscriptions = response.subscriptionsMade
            subscribers = response.subscribers
            subscriberCount = response.subscriberCount
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    func loadNotifications() async {
        do {
            let response = try await APIService.shared.getNotificationHistory(limit: 30)
            notifications = response.notifications
        } catch {
            // Non-critical — just leave empty
        }
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
    
    func cancelSubscription(id: Int) async {
        do {
            let _ = try await APIService.shared.unsubscribe(subscriptionId: id)
            // Remove from local list or update status
            if let index = subscriptions.firstIndex(where: { $0.id == id }) {
                let updated = subscriptions[index]
                subscriptions[index] = SubscriptionMade(
                    id: updated.id,
                    portfolioOwner: updated.portfolioOwner,
                    status: "canceled",
                    expiresAt: updated.expiresAt,
                    pushNotificationsEnabled: updated.pushNotificationsEnabled
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
