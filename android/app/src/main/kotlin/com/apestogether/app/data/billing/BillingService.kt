package com.apestogether.app.data.billing

import android.app.Activity
import android.content.Context
import android.util.Log
import com.android.billingclient.api.AcknowledgePurchaseParams
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams
import com.android.billingclient.api.acknowledgePurchase
import com.android.billingclient.api.queryProductDetails
import com.android.billingclient.api.queryPurchasesAsync
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/**
 * Google Play Billing wrapper. Owns a single [BillingClient] for the app
 * lifecycle and exposes a coroutine-friendly API for:
 *
 *  - Querying the two subscription products ([MONTHLY_PRODUCT_ID] +
 *    [ANNUAL_PRODUCT_ID]).
 *  - Launching the billing flow from an Activity for a chosen plan.
 *  - Awaiting the purchase result (returned from [PurchasesUpdatedListener]).
 *  - Acknowledging purchases (Play refunds them automatically within 3
 *    days if you don't acknowledge).
 *
 * Product IDs must match exactly between Play Console and iOS's
 * StoreKit configuration (`com.apestogether.subscription.{monthly,annual}`).
 *
 * Connection lifecycle: the client connects lazily on first use and
 * automatically reconnects on disconnection. Callers can observe
 * [connectionState] for UI feedback ("Billing not available" vs "Ready").
 */
@Singleton
class BillingService @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    enum class ConnectionState { Disconnected, Connecting, Ready, Unavailable }

    /**
     * Result of a purchase flow. Exactly one of these will be emitted by
     * [purchase] per flow invocation.
     */
    sealed interface PurchaseResult {
        /** User completed payment. Pass [token] to the backend for server-side validation. */
        data class Success(val purchase: Purchase) : PurchaseResult

        /** User dismissed the Google sheet without paying. Not an error. */
        data object UserCanceled : PurchaseResult

        /** Anything else: network failure, item already owned, Play not configured, etc. */
        data class Error(val message: String, val code: Int? = null) : PurchaseResult
    }

    private val _connectionState = MutableStateFlow(ConnectionState.Disconnected)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    private val _productDetails = MutableStateFlow<Map<String, ProductDetails>>(emptyMap())
    /** Keyed by product ID — empty until [queryProducts] succeeds. */
    val productDetails: StateFlow<Map<String, ProductDetails>> = _productDetails.asStateFlow()

    /**
     * One-shot deferred for the in-flight purchase, completed by the
     * [PurchasesUpdatedListener] callback. We park the suspend coroutine
     * on this and let Play call us back asynchronously.
     */
    private var pendingPurchase: CompletableDeferred<PurchaseResult>? = null

    private val purchasesUpdatedListener = PurchasesUpdatedListener { billingResult, purchases ->
        val deferred = pendingPurchase
        pendingPurchase = null

        when (billingResult.responseCode) {
            BillingClient.BillingResponseCode.OK -> {
                val purchase = purchases?.firstOrNull()
                if (purchase != null) {
                    deferred?.complete(PurchaseResult.Success(purchase))
                } else {
                    deferred?.complete(
                        PurchaseResult.Error("Play returned OK but no purchase object")
                    )
                }
            }
            BillingClient.BillingResponseCode.USER_CANCELED -> {
                deferred?.complete(PurchaseResult.UserCanceled)
            }
            BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED -> {
                deferred?.complete(
                    PurchaseResult.Error(
                        "You already subscribed to this trader. " +
                            "Manage existing subscriptions in the Subscriptions tab.",
                        billingResult.responseCode,
                    )
                )
            }
            else -> {
                deferred?.complete(
                    PurchaseResult.Error(
                        billingResult.debugMessage.ifEmpty { "Billing failed: ${billingResult.responseCode}" },
                        billingResult.responseCode,
                    )
                )
            }
        }
    }

    private val billingClient: BillingClient = BillingClient.newBuilder(context)
        .setListener(purchasesUpdatedListener)
        .enablePendingPurchases(
            com.android.billingclient.api.PendingPurchasesParams.newBuilder()
                .enableOneTimeProducts()
                .build()
        )
        .build()

    // ─────────────────────────────────────────────────────────────────────
    // Connection
    // ─────────────────────────────────────────────────────────────────────

    /**
     * Ensure the [BillingClient] is connected, reconnecting if necessary.
     * Suspends until the connection succeeds or definitively fails.
     */
    suspend fun ensureConnected(): BillingResult = suspendCoroutine { cont ->
        if (billingClient.isReady) {
            _connectionState.value = ConnectionState.Ready
            cont.resume(BillingResult.newBuilder().setResponseCode(BillingClient.BillingResponseCode.OK).build())
            return@suspendCoroutine
        }

        _connectionState.value = ConnectionState.Connecting
        billingClient.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(billingResult: BillingResult) {
                _connectionState.value = when (billingResult.responseCode) {
                    BillingClient.BillingResponseCode.OK -> ConnectionState.Ready
                    BillingClient.BillingResponseCode.BILLING_UNAVAILABLE -> ConnectionState.Unavailable
                    else -> ConnectionState.Disconnected
                }
                cont.resume(billingResult)
            }

            override fun onBillingServiceDisconnected() {
                _connectionState.value = ConnectionState.Disconnected
                // Will reconnect on next ensureConnected() call.
            }
        })
    }

    // ─────────────────────────────────────────────────────────────────────
    // Product query
    // ─────────────────────────────────────────────────────────────────────

    /**
     * Query Play for the latest pricing + offer details of our two
     * subscription SKUs. Cache the results in [productDetails].
     *
     * Will fail with a non-OK response if you haven't yet published the
     * subscription products in Play Console — in that case the caller
     * should fall back to "Billing not available" UI.
     */
    suspend fun queryProducts(): BillingResult {
        val ensure = ensureConnected()
        if (ensure.responseCode != BillingClient.BillingResponseCode.OK) return ensure

        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(
                listOf(MONTHLY_PRODUCT_ID, ANNUAL_PRODUCT_ID).map { id ->
                    QueryProductDetailsParams.Product.newBuilder()
                        .setProductId(id)
                        .setProductType(BillingClient.ProductType.SUBS)
                        .build()
                }
            )
            .build()

        val result = billingClient.queryProductDetails(params)
        if (result.billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
            val byId = result.productDetailsList.orEmpty().associateBy { it.productId }
            // Merge (don't clobber) so any per-creator "slot" products fetched on
            // demand via [queryProduct] survive a refresh of the default pair.
            _productDetails.value = _productDetails.value + byId
            Log.d(TAG, "Loaded ${byId.size} subscription products: ${byId.keys}")
        } else {
            Log.w(
                TAG,
                "queryProductDetails failed: code=${result.billingResult.responseCode} msg=${result.billingResult.debugMessage}",
            )
        }
        return result.billingResult
    }

    /**
     * Query Play for a single subscription product's details and cache it. Used
     * for the per-creator "slot" products (Subscription B..T) that aren't part of
     * the default monthly/annual pair loaded by [queryProducts]. Returns null if
     * Play is unavailable or the product isn't published.
     */
    suspend fun queryProduct(productId: String): ProductDetails? {
        val ensure = ensureConnected()
        if (ensure.responseCode != BillingClient.BillingResponseCode.OK) return null

        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(
                listOf(
                    QueryProductDetailsParams.Product.newBuilder()
                        .setProductId(productId)
                        .setProductType(BillingClient.ProductType.SUBS)
                        .build()
                )
            )
            .build()

        val result = billingClient.queryProductDetails(params)
        if (result.billingResult.responseCode != BillingClient.BillingResponseCode.OK) {
            Log.w(
                TAG,
                "queryProduct($productId) failed: code=${result.billingResult.responseCode} msg=${result.billingResult.debugMessage}",
            )
            return null
        }
        val pd = result.productDetailsList.orEmpty().firstOrNull { it.productId == productId }
        if (pd != null) {
            _productDetails.value = _productDetails.value + (productId to pd)
        }
        return pd
    }

    // ─────────────────────────────────────────────────────────────────────
    // Purchase flow
    // ─────────────────────────────────────────────────────────────────────

    /**
     * Launch the Play Billing sheet for [productId] from [activity], then
     * suspend until the user completes / cancels / errors out.
     *
     * Picks the first offer in the subscription's `subscriptionOfferDetails`
     * (this is where the 7-day free trial offer lives — Play Console
     * orders offers so that promotional offers come first).
     */
    suspend fun purchase(activity: Activity, productId: String): PurchaseResult {
        // Slot products (Subscription B..T) aren't in the default pair, so fetch
        // the specific product on demand if it isn't cached yet.
        val product = _productDetails.value[productId] ?: queryProduct(productId)
        if (product == null) {
            return PurchaseResult.Error(
                "Subscription product not available. The product may not be published in Play Console yet."
            )
        }

        val offerToken = product.subscriptionOfferDetails?.firstOrNull()?.offerToken
            ?: return PurchaseResult.Error("No subscription offer available for $productId")

        val params = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(
                listOf(
                    BillingFlowParams.ProductDetailsParams.newBuilder()
                        .setProductDetails(product)
                        .setOfferToken(offerToken)
                        .build()
                )
            )
            .build()

        val deferred = CompletableDeferred<PurchaseResult>()
        pendingPurchase = deferred

        val launchResult = billingClient.launchBillingFlow(activity, params)
        if (launchResult.responseCode != BillingClient.BillingResponseCode.OK) {
            pendingPurchase = null
            return PurchaseResult.Error(
                launchResult.debugMessage.ifEmpty { "Failed to launch billing flow" },
                launchResult.responseCode,
            )
        }

        return deferred.await()
    }

    /**
     * Acknowledge a successful purchase. Required within 3 days of
     * purchase or Play will automatically refund. Backends typically
     * acknowledge server-side (via the Play Developer API) when they
     * record the purchase, but acknowledging client-side is safer + idempotent.
     */
    suspend fun acknowledge(purchase: Purchase): BillingResult {
        if (purchase.isAcknowledged) {
            return BillingResult.newBuilder().setResponseCode(BillingClient.BillingResponseCode.OK).build()
        }
        val params = AcknowledgePurchaseParams.newBuilder()
            .setPurchaseToken(purchase.purchaseToken)
            .build()
        return billingClient.acknowledgePurchase(params)
    }

    /**
     * Get any existing active subscriptions the user already owns. Used
     * to (a) restore purchases after sign-in on a new device, and (b)
     * detect ITEM_ALREADY_OWNED situations gracefully.
     */
    suspend fun queryActivePurchases(): List<Purchase> {
        val ensure = ensureConnected()
        if (ensure.responseCode != BillingClient.BillingResponseCode.OK) return emptyList()
        val params = QueryPurchasesParams.newBuilder()
            .setProductType(BillingClient.ProductType.SUBS)
            .build()
        val result = billingClient.queryPurchasesAsync(params)
        return if (result.billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
            result.purchasesList
        } else emptyList()
    }

    // ─────────────────────────────────────────────────────────────────────
    // Pricing helpers (mirror iOS Configuration.storekit)
    // ─────────────────────────────────────────────────────────────────────

    /**
     * Formatted price for the monthly plan, taken from the
     * [ProductDetails] if available (e.g. "$9.00") with a hardcoded
     * fallback matching iOS.
     */
    fun monthlyPrice(): String =
        _productDetails.value[MONTHLY_PRODUCT_ID]
            ?.subscriptionOfferDetails
            ?.firstOrNull()
            ?.pricingPhases
            ?.pricingPhaseList
            ?.lastOrNull { it.priceAmountMicros > 0 }   // skip the free trial phase
            ?.formattedPrice
            ?: "$9.00"

    fun annualPrice(): String =
        _productDetails.value[ANNUAL_PRODUCT_ID]
            ?.subscriptionOfferDetails
            ?.firstOrNull()
            ?.pricingPhases
            ?.pricingPhaseList
            ?.lastOrNull { it.priceAmountMicros > 0 }
            ?.formattedPrice
            ?: "$69.00"

    companion object {
        private const val TAG = "BillingService"

        /** Must match Play Console + iOS StoreKit product IDs exactly. */
        const val MONTHLY_PRODUCT_ID = "com.apestogether.subscription.monthly"
        const val ANNUAL_PRODUCT_ID = "com.apestogether.subscription.annual"
    }
}

/** Selected plan in the Subscribe UI (the toggle above the CTA button). */
enum class SubscriptionPlan(val productId: String) {
    Monthly(BillingService.MONTHLY_PRODUCT_ID),
    Annual(BillingService.ANNUAL_PRODUCT_ID),
}
