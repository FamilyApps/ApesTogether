import SwiftUI
import Combine
import StoreKit

@MainActor
class SubscriptionManager: ObservableObject {
    @Published var products: [Product] = []
    @Published var purchasedSubscriptions: [Product] = []
    @Published var isProcessing = false
    @Published var error: String?
    
    private let productIds = ["com.apestogether.subscription.monthly"]
    private var updateTask: Task<Void, Never>?
    
    init() {
        updateTask = Task {
            await listenForTransactions()
        }
        
        Task {
            await loadProducts()
        }
    }
    
    deinit {
        updateTask?.cancel()
    }
    
    func loadProducts() async {
        do {
            products = try await Product.products(for: productIds)
            print("[SubscriptionManager] Loaded \(products.count) products: \(products.map { $0.id })")
            if products.isEmpty {
                print("[SubscriptionManager] WARNING: No products found for IDs: \(productIds)")
            }
        } catch {
            print("[SubscriptionManager] Failed to load products: \(error)")
            self.error = "Could not load subscription products"
        }
    }
    
    func subscribe(to userId: Int) async {
        // Retry loading products if empty
        if products.isEmpty {
            await loadProducts()
        }
        
        guard let product = products.first else {
            error = "Subscription not available yet. Please try again later."
            print("[SubscriptionManager] subscribe() failed: no products loaded for IDs: \(productIds)")
            return
        }
        
        print("[SubscriptionManager] Starting purchase of \(product.id) for user \(userId)")
        
        isProcessing = true
        error = nil
        
        do {
            let result = try await product.purchase()
            
            switch result {
            case .success(let verification):
                // Extract JWS from the VerificationResult before unwrapping
                let jwsRepresentation = verification.jwsRepresentation
                let transaction = try checkVerified(verification)
                
                // Validate with backend
                await validateWithBackend(jwsRepresentation: jwsRepresentation, transaction: transaction, userId: userId)
                
                await transaction.finish()
                
            case .pending:
                error = "Purchase pending approval"
                
            case .userCancelled:
                break
                
            @unknown default:
                error = "Unknown purchase result"
            }
        } catch {
            self.error = error.localizedDescription
        }
        
        isProcessing = false
    }
    
    private func validateWithBackend(jwsRepresentation: String, transaction: StoreKit.Transaction, userId: Int) async {
        // Use StoreKit 2's signed JWS representation (works in sandbox + production)
        do {
            let response = try await APIService.shared.validatePurchase(
                platform: "apple",
                receiptData: jwsRepresentation,
                purchaseToken: String(transaction.originalID),
                subscribedToId: userId
            )
            
            if !response.success {
                error = response.error ?? "Purchase validation failed"
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    private func listenForTransactions() async {
        for await result in StoreKit.Transaction.updates {
            do {
                let transaction = try checkVerified(result)
                await transaction.finish()
            } catch {
                print("Transaction verification failed: \(error)")
            }
        }
    }
    
    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified:
            throw StoreError.failedVerification
        case .verified(let safe):
            return safe
        }
    }
    
    func restorePurchases() async {
        isProcessing = true
        
        do {
            try await AppStore.sync()
        } catch {
            self.error = error.localizedDescription
        }
        
        isProcessing = false
    }
}

enum StoreError: LocalizedError {
    case failedVerification
    
    var errorDescription: String? {
        switch self {
        case .failedVerification:
            return "Purchase verification failed"
        }
    }
}
