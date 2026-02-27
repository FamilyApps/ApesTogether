import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @Environment(\.dismiss) var dismiss
    @State private var showingSignOutAlert = false
    
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
                        
                        // App section
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "App")
                            
                            VStack(spacing: 0) {
                                SettingsLinkRow(
                                    icon: "globe",
                                    label: "Web Dashboard",
                                    url: "https://apestogether.ai"
                                )
                                AccentDivider()
                                SettingsLinkRow(
                                    icon: "hand.raised",
                                    label: "Privacy Policy",
                                    url: "https://apestogether.ai/privacy"
                                )
                                AccentDivider()
                                SettingsLinkRow(
                                    icon: "doc.text",
                                    label: "Terms of Service",
                                    url: "https://apestogether.ai/terms"
                                )
                            }
                            .cardStyle(padding: 0)
                        }
                        
                        // Support section
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "Support")
                            
                            VStack(spacing: 0) {
                                SettingsLinkRow(
                                    icon: "envelope",
                                    label: "Contact Support",
                                    url: "mailto:support@apestogether.ai"
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
        }
    }
}

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

struct SettingsView_Previews: PreviewProvider {
    static var previews: some View {
        SettingsView()
            .environmentObject(AuthenticationManager())
    }
}
