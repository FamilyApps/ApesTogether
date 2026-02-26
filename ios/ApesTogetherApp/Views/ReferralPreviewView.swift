import SwiftUI
import AuthenticationServices

struct ReferralPreviewView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @ObservedObject var deepLinkManager = DeepLinkManager.shared
    
    let slug: String
    let onSkip: () -> Void
    
    @State private var portfolio: PortfolioResponse?
    @State private var isLoading = true
    @State private var loadError: String?
    
    var body: some View {
        ZStack {
            LinearGradient.heroGradient
                .ignoresSafeArea()
            
            VStack(spacing: 0) {
                // Top bar
                HStack {
                    Spacer()
                    Button("Explore app") {
                        onSkip()
                    }
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(.textSecondary)
                }
                .padding(.horizontal, 24)
                .padding(.top, 16)
                
                Spacer()
                
                if isLoading {
                    ProgressView()
                        .tint(.primaryAccent)
                } else if let portfolio = portfolio {
                    // Portfolio preview content
                    VStack(spacing: 24) {
                        // User avatar circle
                        ZStack {
                            Circle()
                                .fill(Color.primaryAccent.opacity(0.15))
                                .frame(width: 80, height: 80)
                            
                            Text(String(portfolio.owner.username.prefix(1)).uppercased())
                                .font(.system(size: 32, weight: .bold))
                                .foregroundColor(.primaryAccent)
                        }
                        
                        // Username and stats
                        VStack(spacing: 8) {
                            Text(portfolio.owner.username)
                                .font(.title.bold())
                                .foregroundColor(.textPrimary)
                            
                            HStack(spacing: 16) {
                                HStack(spacing: 4) {
                                    Image(systemName: "person.2.fill")
                                        .font(.caption)
                                    Text("\(portfolio.subscriberCount) subscribers")
                                        .font(.subheadline)
                                }
                                .foregroundColor(.textSecondary)
                            }
                        }
                        
                        // Value prop card
                        VStack(spacing: 16) {
                            Image(systemName: "bell.badge.fill")
                                .font(.system(size: 36))
                                .foregroundColor(.primaryAccent)
                            
                            Text("Get real-time trade alerts")
                                .font(.headline)
                                .foregroundColor(.textPrimary)
                            
                            Text("Know the moment \(portfolio.owner.username) buys or sells. Never miss a move.")
                                .font(.subheadline)
                                .foregroundColor(.textSecondary)
                                .multilineTextAlignment(.center)
                        }
                        .padding(24)
                        .cardStyle()
                        .padding(.horizontal, 20)
                    }
                } else if let error = loadError {
                    EmptyStateView(
                        icon: "exclamationmark.triangle",
                        title: "Couldn't Load Portfolio",
                        message: error,
                        action: {
                            Task { await loadPortfolio() }
                        },
                        actionLabel: "Retry"
                    )
                }
                
                Spacer()
                
                // CTA
                VStack(spacing: 16) {
                    if !authManager.isAuthenticated {
                        Text("Sign in to subscribe for $9/mo")
                            .font(.subheadline)
                            .foregroundColor(.textSecondary)
                        
                        SignInWithAppleButton(.signIn) { request in
                            request.requestedScopes = [.email]
                        } onCompletion: { result in
                            switch result {
                            case .success(let authorization):
                                Task {
                                    await authManager.signInWithApple(authorization: authorization)
                                    // After auth, the ContentView will detect the pending slug
                                    // and navigate to subscribe
                                }
                            case .failure(let error):
                                print("Sign in failed: \(error)")
                            }
                        }
                        .signInWithAppleButtonStyle(.white)
                        .frame(height: 54)
                        .cornerRadius(12)
                        .padding(.horizontal, 40)
                    }
                    
                    if authManager.isLoading {
                        ProgressView()
                            .tint(.primaryAccent)
                    }
                    
                    if let error = authManager.error {
                        Text(error)
                            .foregroundColor(.losses)
                            .font(.caption)
                    }
                }
                .padding(.bottom, 50)
            }
        }
        .onAppear {
            Task { await loadPortfolio() }
        }
    }
    
    private func loadPortfolio() async {
        isLoading = true
        loadError = nil
        
        do {
            portfolio = try await APIService.shared.getPortfolio(slug: slug)
        } catch {
            loadError = "This portfolio couldn't be loaded right now."
        }
        
        isLoading = false
    }
}

struct ReferralPreviewView_Previews: PreviewProvider {
    static var previews: some View {
        ReferralPreviewView(slug: "test", onSkip: {})
            .environmentObject(AuthenticationManager())
    }
}
