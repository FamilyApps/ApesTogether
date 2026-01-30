import SwiftUI
import AuthenticationServices

@MainActor
class AuthenticationManager: ObservableObject {
    @Published var isAuthenticated = false
    @Published var currentUser: User?
    @Published var isLoading = false
    @Published var error: String?
    
    private let keychain = KeychainService.shared
    
    init() {
        checkExistingAuth()
    }
    
    private func checkExistingAuth() {
        if let token = keychain.getToken() {
            self.isAuthenticated = true
            Task {
                await refreshUserData()
            }
        }
    }
    
    func signInWithApple(authorization: ASAuthorization) async {
        guard let appleIDCredential = authorization.credential as? ASAuthorizationAppleIDCredential,
              let identityTokenData = appleIDCredential.identityToken,
              let identityToken = String(data: identityTokenData, encoding: .utf8) else {
            error = "Failed to get Apple ID credentials"
            return
        }
        
        isLoading = true
        error = nil
        
        do {
            let response = try await APIService.shared.authenticate(
                provider: "apple",
                idToken: identityToken,
                email: appleIDCredential.email
            )
            
            keychain.saveToken(response.token)
            currentUser = response.user
            isAuthenticated = true
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
    
    func signOut() {
        keychain.deleteToken()
        currentUser = nil
        isAuthenticated = false
    }
    
    func refreshUserData() async {
        guard isAuthenticated else { return }
        
        do {
            let user = try await APIService.shared.getCurrentUser()
            currentUser = user
        } catch {
            // Token might be expired
            signOut()
        }
    }
    
    func navigateToPortfolio(slug: String) {
        // Handle deep link to portfolio
        NotificationCenter.default.post(
            name: .navigateToPortfolio,
            object: nil,
            userInfo: ["slug": slug]
        )
    }
}

extension Notification.Name {
    static let navigateToPortfolio = Notification.Name("navigateToPortfolio")
}
