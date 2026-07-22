import SwiftUI
import Combine
import StoreKit
import UIKit

@MainActor
class SubscriptionManager: ObservableObject {
    @Published var products: [Product] = []
    @Published var purchasedSubscriptions: [Product] = []
    @Published var isProcessing = false
    @Published var error: String?
    @Published var selectedPlan: PlanType = .annual
    /// Whether THIS Apple ID can still redeem the 7-day free trial. Drives
    /// the Subscribe CTA copy via [subscribeCtaText]. Defaults to true (the
    /// common case: a brand-new user) and is corrected by [loadProducts].
    ///
    /// Why checking the Slot-A pair is sufficient: the intro offer exists
    /// ONLY on the Slot-A subscription group (one lifetime trial — see
    /// docs/PER_CREATOR_SUBSCRIPTION_SLOTS.md), and Apple tracks intro-offer
    /// eligibility per group. A user's first-ever sub lands in Slot A (trial
    /// applies iff still eligible); every later sub either reuses Slot A
    /// (eligibility already burned) or lands in B+ which carry no intro offer.
    @Published private(set) var trialEligible = true
    
    enum PlanType: String, CaseIterable {
        case monthly, annual
    }
    
    static let monthlyProductId = "com.apestogether.subscription.monthly"
    static let annualProductId  = "com.apestogether.subscription.annual"
    
    private let productIds = [monthlyProductId, annualProductId]
    
    var monthlyProduct: Product? { products.first { $0.id == Self.monthlyProductId } }
    var annualProduct: Product?  { products.first { $0.id == Self.annualProductId } }
    var selectedProduct: Product? {
        selectedPlan == .annual ? annualProduct : monthlyProduct
    }
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
            await refreshTrialEligibility()
        } catch {
            print("[SubscriptionManager] Failed to load products: \(error)")
            self.error = "Could not load subscription products"
        }
    }
    
    /// See [trialEligible]. Leaves the optimistic default untouched when the
    /// products didn't load (we'd have no store answer to overrule it with).
    private func refreshTrialEligibility() async {
        guard let sub = (annualProduct ?? monthlyProduct)?.subscription else { return }
        if sub.introductoryOffer == nil {
            // No intro offer configured on Slot A at all — never promise one.
            trialEligible = false
        } else {
            trialEligible = await sub.isEligibleForIntroOffer
        }
        print("[SubscriptionManager] trialEligible=\(trialEligible)")
    }
    
    /// Subscribe-button label. Trial copy ONLY while the store confirms this
    /// account can still redeem the 7-day intro offer — slots B+ and
    /// trial-used accounts bill immediately, so the button must say so.
    func subscribeCtaText(monthlyPrice: Double = 9) -> String {
        let price = selectedPlan == .annual
            ? "$69/yr"
            : "$\(String(format: "%.0f", monthlyPrice))/mo"
        return trialEligible
            ? "Try Free for 7 Days, then \(price)"
            : "Subscribe for \(price)"
    }
    
    /// Subscribe to [userId]. On a successful (backend-validated) purchase,
    /// posts `.didSubscribe` with the trader's [username] + [slug] so
    /// ContentView can present the post-subscribe EarnNudge (mirrors the
    /// Android OnboardingManager.notifyDidSubscribe flow).
    ///
    /// Per-creator slots: the backend assigns this creator a generic store
    /// "slot" product (Subscription A/B/…) so the user can hold independently
    /// cancelable subs to many creators. We resolve the slot's product IDs
    /// first, then purchase that specific product. See
    /// docs/PER_CREATOR_SUBSCRIPTION_SLOTS.md.
    func subscribe(to userId: Int, username: String? = nil, slug: String? = nil) async {
        isProcessing = true
        error = nil
        defer { isProcessing = false }

        // 1) Ask the backend which slot product to buy for THIS creator.
        let resolution: SubscriptionSlotResponse
        do {
            resolution = try await APIService.shared.getSubscriptionSlot(subscribedToId: userId)
        } catch {
            self.error = error.localizedDescription
            return
        }
        if let err = resolution.error {
            switch err {
            case "max_reached":
                let maxSlots = resolution.maxSlots ?? 20
                self.error = "You've reached the maximum of \(maxSlots) subscriptions. Cancel one to subscribe to another."
            case "already_subscribed":
                self.error = "You're already subscribed to this trader."
            default:
                self.error = "Couldn't start the subscription. Please try again."
            }
            return
        }
        guard let productId = (selectedPlan == .annual ? resolution.annualProductId : resolution.monthlyProductId) else {
            self.error = "Subscription not available yet. Please try again later."
            return
        }

        // 2) Load that slot's product from the App Store.
        let product: Product
        do {
            let fetched = try await Product.products(for: [productId])
            guard let p = fetched.first else {
                self.error = "Subscription product not available. The product may not be published yet."
                print("[SubscriptionManager] subscribe() failed: no App Store product for \(productId)")
                return
            }
            product = p
        } catch {
            self.error = error.localizedDescription
            return
        }

        print("[SubscriptionManager] Starting purchase of \(product.id) (slot \(resolution.slotLabel ?? "?"), \(selectedPlan.rawValue)) for user \(userId)")

        // 3) Purchase + validate.
        do {
            let result = try await product.purchase()

            switch result {
            case .success(let verification):
                // Extract JWS from the VerificationResult before unwrapping
                let jwsRepresentation = verification.jwsRepresentation
                let transaction = try checkVerified(verification)

                // Validate with backend (it derives the slot from the receipt's
                // authoritative product_id and binds the token → creator).
                await validateWithBackend(jwsRepresentation: jwsRepresentation, transaction: transaction, userId: userId)

                await transaction.finish()

                // Only fire the post-subscribe nudge if the backend accepted
                // the purchase (validateWithBackend sets `error` on failure).
                if error == nil {
                    var info: [String: Any] = [:]
                    if let username = username { info["username"] = username }
                    if let slug = slug { info["slug"] = slug }
                    NotificationCenter.default.post(
                        name: .didSubscribe,
                        object: nil,
                        userInfo: info
                    )
                }

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

    /// Opens the system "Manage Subscriptions" sheet so the user can actually
    /// stop billing. Apps cannot cancel auto-renewable subscriptions
    /// programmatically — only the user can, via the App Store.
    func openManageSubscriptions() async {
        guard let scene = UIApplication.shared.connectedScenes
            .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene else { return }
        do {
            try await AppStore.showManageSubscriptions(in: scene)
        } catch {
            self.error = error.localizedDescription
        }
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
