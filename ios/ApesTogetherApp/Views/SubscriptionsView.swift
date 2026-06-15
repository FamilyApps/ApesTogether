import SwiftUI
import Combine
import UserNotifications

struct SubscriptionsView: View {
    @StateObject private var viewModel = SubscriptionsViewModel()
    @EnvironmentObject var subscriptionManager: SubscriptionManager
    @State private var showSettings = false
    @Environment(\.scenePhase) private var scenePhase

    /// Clear the app icon badge and the system-level delivered notifications
    /// list. Called when the user opens the Subscriptions tab, since the Trade
    /// Alerts list at the bottom of this view is the in-app destination that
    /// surfaces those notifications. After viewing them here, the iOS home-
    /// screen badge should reset to zero (matches user expectations and is
    /// standard behavior for inbox-style screens).
    private func clearNotificationBadge() {
        Task {
            // iOS 16+ unified API (deployment target is 16.0).
            try? await UNUserNotificationCenter.current().setBadgeCount(0)
        }
        // Also remove delivered notifications from Notification Center so the
        // user doesn't see a stale pile when they next swipe down. Pending /
        // scheduled notifications are NOT touched.
        UNUserNotificationCenter.current().removeAllDeliveredNotifications()
    }
    
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
            .alert("Manage Subscription", isPresented: $viewModel.showCancelConfirm) {
                Button("Not Now", role: .cancel) {}
                Button("Manage") {
                    Task { await subscriptionManager.openManageSubscriptions() }
                }
            } message: {
                if let label = viewModel.managingSlotLabel {
                    Text("We'll open your App Store subscription settings. To cancel this one, choose the entry labeled “Trader Subscription \(label).” Canceling stops future billing — you'll keep access until your current billing period ends.")
                } else {
                    Text("We'll open your App Store subscription settings, where you can cancel. Canceling there stops future billing — you'll keep access until your current billing period ends.")
                }
            }
            .onAppear {
                // Clear the iOS home-screen badge each time the user opens
                // this tab. The Trade Alerts list below is the in-app
                // surface for the notifications that incremented the badge,
                // so the badge should reset on every view (not just the
                // first one). See clearNotificationBadge() docs above.
                clearNotificationBadge()

                // Always reload on appear (not only when empty) so switching
                // back to this tab picks up new trade alerts. loadAll() leaves
                // existing data in place while fetching, and the loading
                // overlay only shows when the lists are empty, so there's no
                // spinner flash on a background refresh.
                Task { await viewModel.loadAll() }
            }
            .onChange(of: scenePhase) { newPhase in
                // Reopening the app from the background (e.g. after tapping a
                // trade-alert push) doesn't fire onAppear, so refresh here too
                // — new alerts then appear without a manual pull-to-refresh.
                if newPhase == .active {
                    clearNotificationBadge()
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
                            Text(sub.subscriber?.publicName ?? "User")
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
                                        Text(formatAlertTimestamp(date))
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
        if let date = parseBackendDate(dateString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateFormat = "MMM d"
            return displayFormatter.string(from: date)
        }
        return dateString
    }
    
    private func formatRelativeDate(_ dateString: String) -> String {
        guard let date = parseBackendDate(dateString) else { return dateString }
        let interval = Date().timeIntervalSince(date)
        if interval < 60 { return "just now" }
        if interval < 3600 { return "\(Int(interval / 60))m ago" }
        if interval < 86400 { return "\(Int(interval / 3600))h ago" }
        if interval < 604800 { return "\(Int(interval / 86400))d ago" }
        let displayFormatter = DateFormatter()
        displayFormatter.dateFormat = "MMM d"
        return displayFormatter.string(from: date)
    }

    /// Trade Alerts timestamp: a friendly relative prefix (for items < 1 week
    /// old) followed by the exact calendar date and time down to the minute,
    /// e.g. "3d ago · May 28, 5:33 PM". Older items drop the redundant relative
    /// prefix and show the absolute date/time only. The year is appended when
    /// the alert is not from the current year.
    private func formatAlertTimestamp(_ dateString: String) -> String {
        guard let date = parseBackendDate(dateString) else { return dateString }
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US")
        let sameYear = Calendar.current.isDate(date, equalTo: Date(), toGranularity: .year)
        df.dateFormat = sameYear ? "MMM d, h:mm a" : "MMM d, yyyy, h:mm a"
        let absolute = df.string(from: date)

        let interval = Date().timeIntervalSince(date)
        let relative: String?
        if interval < 60 { relative = "just now" }
        else if interval < 3600 { relative = "\(Int(interval / 60))m ago" }
        else if interval < 86400 { relative = "\(Int(interval / 3600))h ago" }
        else if interval < 604800 { relative = "\(Int(interval / 86400))d ago" }
        else { relative = nil }

        if let relative = relative { return "\(relative) · \(absolute)" }
        return absolute
    }
}

// MARK: - Date parsing

/// Robustly parses backend ISO-8601 timestamps. The backend emits 6-digit
/// microsecond precision (e.g. "2026-05-28T17:33:38.761915Z"), which a bare
/// `ISO8601DateFormatter` rejects outright — and even `.withFractionalSeconds`
/// only accepts 3 digits. Without this, every caller fell back to printing the
/// raw ISO string in the Trade Alerts list.
fileprivate func parseBackendDate(_ s: String) -> Date? {
    let withFrac = ISO8601DateFormatter()
    withFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let d = withFrac.date(from: s) { return d }

    let plain = ISO8601DateFormatter()
    plain.formatOptions = [.withInternetDateTime]
    if let d = plain.date(from: s) { return d }

    // Strip the fractional component (any number of digits) and retry, since
    // the formatters above can't handle microsecond precision.
    if let dot = s.range(of: #"\.\d+"#, options: .regularExpression) {
        let stripped = s.replacingCharacters(in: dot, with: "")
        if let d = plain.date(from: stripped) { return d }
    }

    // Fallback for timezone-LESS timestamps, e.g. subscription expires_at
    // ("2026-06-11T02:54:44.082000") or "2026-06-11T02:54:44". Every branch
    // above relies on ISO8601DateFormatter, which REQUIRES a trailing 'Z' or
    // offset and rejects these outright — that's why the renewal date rendered
    // as a raw ISO string. The backend emits these as naive UTC, so parse with
    // a fixed-format UTC DateFormatter. Microseconds are first truncated to
    // milliseconds since DateFormatter's 'S' field only handles 3 digits.
    let normalized = s.replacingOccurrences(
        of: #"\.(\d{3})\d+"#, with: ".$1", options: .regularExpression
    )
    let utc = DateFormatter()
    utc.locale = Locale(identifier: "en_US_POSIX")
    utc.timeZone = TimeZone(identifier: "UTC")
    for fmt in ["yyyy-MM-dd'T'HH:mm:ss.SSS", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd"] {
        utc.dateFormat = fmt
        if let d = utc.date(from: normalized) { return d }
    }
    return nil
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
                    Text(subscription.portfolioOwner?.publicName ?? "Unknown")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.textPrimary)
                    
                    HStack(spacing: 8) {
                        StatusBadge(
                            text: subscription.status.capitalized,
                            color: subscription.status == "active" ? .gains : .textSecondary
                        )
                        if let label = subscription.slotLabel {
                            Text("Trader Subscription \(label)")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(.textMuted)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.cardBorder.opacity(0.3))
                                .cornerRadius(4)
                        }
                        if let expires = subscription.expiresAt {
                            Text("Renews \(formatDate(expires))")
                                .font(.system(size: 11))
                                .foregroundColor(.textMuted)
                        }
                    }
                }
                
                Spacer()
                
                // Notification toggle
                HStack(spacing: 6) {
                    Image(systemName: subscription.pushNotificationsEnabled ? "bell.fill" : "bell.slash")
                        .font(.system(size: 12))
                        .foregroundColor(subscription.pushNotificationsEnabled ? .primaryAccent : .textMuted)
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
                    viewModel.managingSlotLabel = subscription.slotLabel
                    viewModel.showCancelConfirm = true
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "gearshape")
                            .font(.system(size: 11))
                        Text("Manage")
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
        if let date = parseBackendDate(dateString) {
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
    // The store slot label ("A".."T") of the subscription the user tapped
    // "Manage" on, so the confirm alert can name the exact store entry to cancel.
    @Published var managingSlotLabel: String?
    
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
                    pushNotificationsEnabled: enabled,
                    slot: updated.slot,
                    slotLabel: updated.slotLabel
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
