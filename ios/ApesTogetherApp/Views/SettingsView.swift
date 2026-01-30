import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @State private var showingSignOutAlert = false
    
    var body: some View {
        NavigationStack {
            List {
                // Account section
                Section("Account") {
                    if let user = authManager.currentUser {
                        HStack {
                            Text("Email")
                            Spacer()
                            Text(user.email)
                                .foregroundColor(.secondary)
                        }
                        
                        HStack {
                            Text("Username")
                            Spacer()
                            Text(user.username)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                
                // App section
                Section("App") {
                    Link(destination: URL(string: "https://apestogether.ai")!) {
                        Label("Web Dashboard", systemImage: "globe")
                    }
                    
                    Link(destination: URL(string: "https://apestogether.ai/privacy")!) {
                        Label("Privacy Policy", systemImage: "hand.raised")
                    }
                    
                    Link(destination: URL(string: "https://apestogether.ai/terms")!) {
                        Label("Terms of Service", systemImage: "doc.text")
                    }
                }
                
                // Support section
                Section("Support") {
                    Link(destination: URL(string: "mailto:support@apestogether.ai")!) {
                        Label("Contact Support", systemImage: "envelope")
                    }
                }
                
                // Sign out
                Section {
                    Button(role: .destructive) {
                        showingSignOutAlert = true
                    } label: {
                        Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                }
                
                // Version
                Section {
                    HStack {
                        Text("Version")
                        Spacer()
                        Text(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Settings")
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

#Preview {
    SettingsView()
        .environmentObject(AuthenticationManager())
}
