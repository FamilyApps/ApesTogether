import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @Environment(\.dismiss) var dismiss
    @State private var showingSignOutAlert = false
    @State private var showingDeleteAlert = false
    @State private var allowSubscribers = true
    @State private var showTOS = false
    @State private var showPrivacy = false
    @State private var showFAQ = false
    @State private var urlCopied = false
    
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
                                    Text("Allow Subscribers")
                                        .foregroundColor(.textPrimary)
                                    Spacer()
                                    Toggle("", isOn: $allowSubscribers)
                                        .toggleStyle(SwitchToggleStyle(tint: Color.primaryAccent))
                                        .labelsHidden()
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
                                    label: "1099-NEC Tax Form"
                                ) {
                                    // TODO: Navigate to 1099-NEC retrieval
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
        ("What is Apes Together?", "Apes Together is a portfolio tracking platform that lets you track your investments, share your portfolio with others, and earn money when people subscribe to follow your trades."),
        ("How do I earn money?", "When you add your stocks and enable subscribers, other users can pay to subscribe to your portfolio. You earn 70% of every subscription payment."),
        ("Is this investment advice?", "No. Apes Together is strictly an educational and informational platform. No content on the platform constitutes investment advice. All users make their own independent investment decisions."),
        ("How do I get paid?", "Payments are disbursed monthly via check from Family Apps LLC. You must submit a W-9 form to receive payments."),
        ("What is the 1099-NEC?", "If you earn $600 or more in a calendar year, Family Apps LLC will issue you a 1099-NEC tax form for reporting your earnings to the IRS."),
        ("How do I cancel my subscription?", "You can manage your subscriptions through your Apple ID settings or through the Subscriptions tab in the app."),
        ("How do I delete my account?", "Go to Settings and tap 'Delete Account' at the bottom. This action is permanent and cannot be undone."),
        ("Who can use this app?", "Apes Together is available to users located in the United States who are U.S. tax residents.")
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
