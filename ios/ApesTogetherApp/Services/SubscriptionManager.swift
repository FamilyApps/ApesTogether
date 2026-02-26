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
        } catch {
            print("Failed to load products: \(error)")
        }
    }
    
    func subscribe(to userId: Int) async {
        guard let product = products.first else {
            error = "Subscription product not available"
            return
        }
        
        isProcessing = true
        error = nil
        
        do {
            let result = try await product.purchase()
            
            switch result {
            case .success(let verification):
                let transaction = try checkVerified(verification)
                
                // Validate with backend
                await validateWithBackend(transaction: transaction, userId: userId)
                
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
    
    private func validateWithBackend(transaction: StoreKit.Transaction, userId: Int) async {
        // Get the receipt data
        guard let appStoreReceiptURL = Bundle.main.appStoreReceiptURL,
              FileManager.default.fileExists(atPath: appStoreReceiptURL.path),
              let receiptData = try? Data(contentsOf: appStoreReceiptURL) else {
            error = "Could not retrieve receipt"
            return
        }
        
        let receiptString = receiptData.base64EncodedString()
        
        do {
            let response = try await APIService.shared.validatePurchase(
                platform: "apple",
                receiptData: receiptString,
                purchaseToken: nil,
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
