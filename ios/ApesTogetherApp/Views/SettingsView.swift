import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @Environment(\.dismiss) var dismiss
    @State private var showingSignOutAlert = false
    @State private var showingDeleteAlert = false
    // W7: "Allow New Subscribers". Loaded from /settings/portfolio-preferences
    // on appear; persists back via PUT. OFF blocks NEW subscriptions only —
    // existing subscribers keep access and the profile stays on the leaderboard.
    @State private var acceptsNewSubscribers = true
    @State private var acceptsNewSubscribersLoaded = false
    @State private var showTOS = false
    @State private var showPrivacy = false
    @State private var showFAQ = false
    @State private var urlCopied = false
    @State private var showTaxInfo = false

    // Phase D portfolio display preference. Default true so scaled
    // subscriber views show up to 5-decimal fractional shares; flipping
    // it off floors to whole shares and surfaces a "below 1 share"
    // footnote. Loaded from /settings/portfolio-preferences on appear.
    @State private var preferFractional = true
    @State private var preferFractionalLoaded = false
    
    private var personalURL: String {
        if let slug = authManager.currentUser?.portfolioSlug {
            return "https://apestogether.ai/p/\(slug)"
        }
        return "https://apestogether.ai"
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: 24) {
                        // Account section
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "Account")
                            
                            VStack(spacing: 0) {
                                if let user = authManager.currentUser {
                                    SettingsRow(label: "Email", value: user.email)
                                    AccentDivider()
                                    SettingsRow(label: "Username", value: user.username)
                                }
                            }
                            .cardStyle(padding: 0)
                        }
                        
                        // Personal Link section
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "Your Portfolio Link")
                            
                            VStack(spacing: 12) {
                                HStack {
                                    Text(personalURL)
                                        .font(.caption)
                                        .foregroundColor(.primaryAccent)
                                        .lineLimit(1)
                                    Spacer()
                                    Button {
                                        UIPasteboard.general.string = personalURL
                                        urlCopied = true
                                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                                            urlCopied = false
                                        }
                                    } label: {
                                        HStack(spacing: 4) {
                                            Image(systemName: urlCopied ? "checkmark" : "doc.on.doc")
                                            Text(urlCopied ? "Copied!" : "Copy")
                                        }
                                        .font(.caption.weight(.semibold))
                                        .foregroundColor(.appBackground)
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 6)
                                        .background(Color.primaryAccent)
                                        .cornerRadius(8)
                                    }
                                }
                                .padding()
                            }
                            .cardStyle(padding: 0)
                        }
                        
                        // Preferences section
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "Preferences")
                            
                            VStack(spacing: 0) {
                                HStack {
                                    Image(systemName: "person.2.fill")
                                        .foregroundColor(.primaryAccent)
                                        .frame(width: 24)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("Allow New Subscribers")
                                            .foregroundColor(.textPrimary)
                                        Text("When off, you still appear on the leaderboard but no one new can subscribe")
                                            .font(.caption2)
                                            .foregroundColor(.textMuted)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                    Spacer()
                                    Toggle("", isOn: $acceptsNewSubscribers)
                                        .toggleStyle(SwitchToggleStyle(tint: Color.primaryAccent))
                                        .labelsHidden()
                                        .disabled(!acceptsNewSubscribersLoaded)
                                        .onChange(of: acceptsNewSubscribers) { newValue in
                                            // Skip the initial set when load fires
                                            guard acceptsNewSubscribersLoaded else { return }
                                            Task { await saveAcceptsNewSubscribers(newValue) }
                                        }
                                }
                                .padding()

                                AccentDivider()

                                // Phase D: show fractional shares in scaled
                                // subscribed-portfolio views. Persists to
                                // User.extra_data via PUT /settings/portfolio-preferences.
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Image(systemName: "chart.pie.fill")
                                            .foregroundColor(.primaryAccent)
                                            .frame(width: 24)
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text("Show Fractional Shares")
                                                .foregroundColor(.textPrimary)
                                            Text("In scaled portfolio views")
                                                .font(.caption2)
                                                .foregroundColor(.textMuted)
                                        }
                                        Spacer()
                                        Toggle("", isOn: $preferFractional)
                                            .toggleStyle(SwitchToggleStyle(tint: Color.primaryAccent))
                                            .labelsHidden()
                                            .disabled(!preferFractionalLoaded)
                                            .onChange(of: preferFractional) { newValue in
                                                // Skip the initial set when loaded fires
                                                guard preferFractionalLoaded else { return }
                                                Task { await savePreferFractional(newValue) }
                                            }
                                    }
                                }
                                .padding()
                            }
                            .cardStyle(padding: 0)
                        }
                        
                        // Payments section
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "Payments")
                            
                            VStack(spacing: 0) {
                                SettingsNavRow(
                                    icon: "clock.arrow.circlepath",
                                    label: "Payment History"
                                ) {
                                    // TODO: Navigate to payment history
                                }
                                AccentDivider()
                                SettingsNavRow(
                                    icon: "doc.text.fill",
                                    label: "Tax Info"
                                ) {
                                    showTaxInfo = true
                                }
                            }
                            .cardStyle(padding: 0)
                        }
                        
                        // Help & Legal section
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "Help & Legal")
                            
                            VStack(spacing: 0) {
                                SettingsNavRow(
                                    icon: "questionmark.circle",
                                    label: "FAQ"
                                ) {
                                    showFAQ = true
                                }
                                AccentDivider()
                                SettingsNavRow(
                                    icon: "doc.text",
                                    label: "Terms of Service"
                                ) {
                                    showTOS = true
                                }
                                AccentDivider()
                                SettingsNavRow(
                                    icon: "hand.raised",
                                    label: "Privacy Policy"
                                ) {
                                    showPrivacy = true
                                }
                                AccentDivider()
                                SettingsLinkRow(
                                    icon: "envelope",
                                    label: "Contact Support",
                                    url: "mailto:support@apestogether.ai"
                                )
                                AccentDivider()
                                SettingsLinkRow(
                                    icon: "globe",
                                    label: "Web Dashboard",
                                    url: "https://apestogether.ai"
                                )
                            }
                            .cardStyle(padding: 0)
                        }
                        
                        // Sign out button
                        Button {
                            showingSignOutAlert = true
                        } label: {
                            HStack {
                                Image(systemName: "rectangle.portrait.and.arrow.right")
                                Text("Sign Out")
                            }
                            .foregroundColor(.losses)
                        }
                        .buttonStyle(SecondaryButtonStyle())
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.losses.opacity(0.5), lineWidth: 1)
                        )
                        
                        // Delete account button
                        Button {
                            showingDeleteAlert = true
                        } label: {
                            Text("Delete Account")
                                .font(.subheadline)
                                .foregroundColor(.textMuted)
                        }
                        .padding(.top, -8)
                        
                        // Version
                        Text("Version \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")")
                            .font(.caption)
                            .foregroundColor(.textMuted)
                    }
                    .padding()
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textSecondary)
                    }
                }
            }
            .alert("Sign Out", isPresented: $showingSignOutAlert) {
                Button("Cancel", role: .cancel) {}
                Button("Sign Out", role: .destructive) {
                    authManager.signOut()
                }
            } message: {
                Text("Are you sure you want to sign out?")
            }
            .alert("Delete Account", isPresented: $showingDeleteAlert) {
                Button("Cancel", role: .cancel) {}
                Button("Delete", role: .destructive) {
                    Task {
                        await deleteAccount()
                    }
                }
            } message: {
                Text("This will permanently delete your account, portfolio data, and all subscriptions. This action cannot be undone.")
            }
            .sheet(isPresented: $showTOS) {
                LegalTextView(title: "Terms of Service", content: tosText)
            }
            .sheet(isPresented: $showPrivacy) {
                LegalTextView(title: "Privacy Policy", content: privacyText)
            }
            .sheet(isPresented: $showFAQ) {
                FAQView()
            }
            .sheet(isPresented: $showTaxInfo) {
                TaxInfoView()
                    .environmentObject(authManager)
            }
            .task {
                await loadPreferences()
            }
        }
    }
    
    private func deleteAccount() async {
        do {
            try await APIService.shared.deleteAccount()
            authManager.signOut()
        } catch {
            print("Failed to delete account: \(error)")
        }
    }

    // ── Phase D: portfolio display preferences ──────────────────────────
    // Load on settings appear so the toggle reflects the server state.
    // The `preferFractionalLoaded` flag gates the .onChange handler so
    // SwiftUI's initial state set doesn't trigger an unnecessary PUT.
    private func loadPreferences() async {
        do {
            let prefs = try await APIService.shared.getPortfolioPreferences()
            await MainActor.run {
                preferFractional = prefs.preferFractional
                preferFractionalLoaded = true
                acceptsNewSubscribers = prefs.acceptsNewSubscribers ?? true
                acceptsNewSubscribersLoaded = true
            }
        } catch {
            // Failure isn't critical — toggles stay at default (true) but
            // disabled so the user knows they didn't load. Log for debug.
            print("Failed to load portfolio preferences: \(error)")
            await MainActor.run {
                preferFractionalLoaded = true
                acceptsNewSubscribersLoaded = true
            }
        }
    }

    private func savePreferFractional(_ newValue: Bool) async {
        do {
            _ = try await APIService.shared.updatePortfolioPreferences(preferFractional: newValue)
        } catch {
            // Roll back on failure so the toggle state matches the server.
            print("Failed to update portfolio preferences: \(error)")
            await MainActor.run {
                preferFractional = !newValue
            }
        }
    }

    private func saveAcceptsNewSubscribers(_ newValue: Bool) async {
        do {
            _ = try await APIService.shared.updatePortfolioPreferences(acceptsNewSubscribers: newValue)
        } catch {
            // Roll back on failure so the toggle matches the server.
            print("Failed to update Allow New Subscribers: \(error)")
            await MainActor.run {
                acceptsNewSubscribers = !newValue
            }
        }
    }
}

// MARK: - Helper Views

struct SettingsRow: View {
    let label: String
    let value: String
    
    var body: some View {
        HStack {
            Text(label)
                .foregroundColor(.textPrimary)
            Spacer()
            Text(value)
                .foregroundColor(.textSecondary)
        }
        .padding()
    }
}

struct SettingsNavRow: View {
    let icon: String
    let label: String
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(.primaryAccent)
                    .frame(width: 24)
                Text(label)
                    .foregroundColor(.textPrimary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundColor(.textMuted)
            }
            .padding()
        }
    }
}

struct SettingsLinkRow: View {
    let icon: String
    let label: String
    let url: String
    
    var body: some View {
        Link(destination: URL(string: url)!) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(.primaryAccent)
                    .frame(width: 24)
                Text(label)
                    .foregroundColor(.textPrimary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundColor(.textMuted)
            }
            .padding()
        }
    }
}

// MARK: - Legal Text View

struct LegalTextView: View {
    let title: String
    let content: String
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                ScrollView {
                    Text(content)
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .padding()
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textSecondary)
                    }
                }
            }
        }
    }
}

// MARK: - FAQ View

struct FAQView: View {
    @Environment(\.dismiss) var dismiss
    
    let faqItems: [(question: String, answer: String)] = [
        ("What is ApesTogether?", "ApesTogether is a portfolio tracking platform that lets you track your investments, share your portfolio with others, and earn money when people subscribe to follow your trades."),
        ("How do I earn money?", "When you add your stocks and enable subscribers, other users can pay to subscribe to your portfolio. You earn 85% of proceeds after app store fees."),
        ("Is this investment advice?", "No. ApesTogether is strictly an educational and informational platform. No content on the platform constitutes investment advice. All users make their own independent investment decisions."),
        ("How do I get paid?", "Payments are disbursed monthly via check from Family Apps LLC. You must submit a W-9 form to receive payments."),
        ("What is the 1099-NEC?", "If you earn $600 or more in a calendar year, Family Apps LLC will issue you a 1099-NEC tax form for reporting your earnings to the IRS."),
        ("How do I cancel my subscription?", "You can manage your subscriptions through your Apple ID settings or through the Subscriptions tab in the app."),
        ("How do I delete my account?", "Go to Settings and tap 'Delete Account' at the bottom. This action is permanent and cannot be undone."),
        ("Who can use this app?", "ApesTogether is available to users located in the United States who are U.S. tax residents.")
    ]
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: 16) {
                        ForEach(Array(faqItems.enumerated()), id: \.offset) { _, item in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(item.question)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundColor(.textPrimary)
                                Text(item.answer)
                                    .font(.caption)
                                    .foregroundColor(.textSecondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding()
                            .cardStyle(padding: 0)
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("FAQ")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textSecondary)
                    }
                }
            }
        }
    }
}

struct SettingsView_Previews: PreviewProvider {
    static var previews: some View {
        SettingsView()
            .environmentObject(AuthenticationManager())
    }
}
