import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color.black, Color(red: 0.1, green: 0.2, blue: 0.1)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
            
            VStack(spacing: 40) {
                Spacer()
                
                // Logo and title
                VStack(spacing: 16) {
                    Text("🦍")
                        .font(.system(size: 80))
                    
                    Text("Apes Together")
                        .font(.system(size: 36, weight: .bold))
                        .foregroundColor(.white)
                    
                    Text("Follow top traders.\nGet real-time alerts.")
                        .font(.title3)
                        .foregroundColor(.gray)
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
                .frame(height: 50)
                .cornerRadius(8)
                .padding(.horizontal, 40)
                
                if authManager.isLoading {
                    ProgressView()
                        .tint(.white)
                }
                
                if let error = authManager.error {
                    Text(error)
                        .foregroundColor(.red)
                        .font(.caption)
                }
                
                Spacer()
                    .frame(height: 60)
                
                // Terms
                Text("By signing in, you agree to our Terms of Service and Privacy Policy")
                    .font(.caption)
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
                    .padding(.bottom, 20)
            }
        }
    }
}

#Preview {
    LoginView()
        .environmentObject(AuthenticationManager())
}
