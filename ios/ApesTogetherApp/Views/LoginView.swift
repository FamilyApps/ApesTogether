import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    
    var body: some View {
        ZStack {
            // Background gradient
            LinearGradient.heroGradient
                .ignoresSafeArea()
            
            // Decorative gradient accent
            VStack {
                Spacer()
                LinearGradient(
                    colors: [Color.primaryAccent.opacity(0.0), Color.primaryAccent.opacity(0.08)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 300)
            }
            .ignoresSafeArea()
            
            VStack(spacing: 40) {
                Spacer()
                
                // Logo and title
                VStack(spacing: 20) {
                    // App icon
                    Image("AppIcon-1024")
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 100, height: 100)
                        .cornerRadius(22)
                        .shadow(color: Color.primaryAccent.opacity(0.3), radius: 20, x: 0, y: 10)
                    
                    VStack(spacing: 8) {
                        Text("Apes")
                            .foregroundColor(.textPrimary) +
                        Text(" Together")
                            .foregroundColor(.primaryAccent)
                    }
                    .font(.system(size: 36, weight: .bold))
                    
                    Text("Follow top traders.\nGet real-time alerts.")
                        .font(.title3)
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                }
                
                Spacer()
                
                // Sign in with Apple button
                SignInWithAppleButton(.signIn) { request in
                    request.requestedScopes = [.email]
                } onCompletion: { result in
                    switch result {
                    case .success(let authorization):
                        Task {
                            await authManager.signInWithApple(authorization: authorization)
                        }
                    case .failure(let error):
                        print("Sign in with Apple failed: \(error)")
                    }
                }
                .signInWithAppleButtonStyle(.white)
                .frame(height: 54)
                .cornerRadius(12)
                .padding(.horizontal, 40)
                
                if authManager.isLoading {
                    ProgressView()
                        .tint(.primaryAccent)
                }
                
                if let error = authManager.error {
                    Text(error)
                        .foregroundColor(.losses)
                        .font(.caption)
                        .padding(.horizontal)
                }
                
                Spacer()
                    .frame(height: 60)
                
                // Terms
                Text("By signing in, you agree to our Terms of Service and Privacy Policy")
                    .font(.caption)
                    .foregroundColor(.textMuted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
                    .padding(.bottom, 20)
            }
        }
    }
}

struct LoginView_Previews: PreviewProvider {
    static var previews: some View {
        LoginView()
            .environmentObject(AuthenticationManager())
    }
}
