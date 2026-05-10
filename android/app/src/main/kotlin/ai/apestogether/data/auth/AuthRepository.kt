package ai.apestogether.data.auth

import ai.apestogether.BuildConfig
import ai.apestogether.data.api.ApiService
import ai.apestogether.data.api.DeviceRegistrationRequest
import ai.apestogether.data.models.AuthRequest
import ai.apestogether.data.models.AuthResponse
import ai.apestogether.data.models.User
import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.firebase.messaging.FirebaseMessaging
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.tasks.await
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Owns the full authentication lifecycle. Counterpart to iOS
 * [AuthenticationManager.swift].
 *
 * Responsibilities:
 *  - Drives Google Sign-In via the Credential Manager API (the modern
 *    replacement for the deprecated GoogleSignIn library).
 *  - Exchanges the Google id_token for an Apes Together API token via
 *    POST /auth/token (provider="google").
 *  - Persists the token in [TokenStore] (encrypted).
 *  - Re-registers the device's FCM token after sign-in so push notifications
 *    can route to the freshly-authenticated user.
 *  - Exposes `currentUser`, `isAuthenticated`, `isLoading`, and `error`
 *    StateFlows for Compose to observe.
 */
@Singleton
class AuthRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val tokenStore: TokenStore,
    private val apiService: ApiService,
) {
    private val _currentUser = MutableStateFlow<User?>(null)
    val currentUser: StateFlow<User?> = _currentUser.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    val isAuthenticated = tokenStore.isAuthenticated

    /**
     * Drive the Google Sign-In flow using Credential Manager.
     *
     * Pre-req: [BuildConfig.GOOGLE_WEB_CLIENT_ID] must be populated via
     * `secrets.properties` (see android/README.md for setup).
     */
    suspend fun signInWithGoogle(activityContext: Context): Result<User> {
        val webClientId = BuildConfig.GOOGLE_WEB_CLIENT_ID
        if (webClientId.isBlank()) {
            return Result.failure(IllegalStateException(
                "GOOGLE_WEB_CLIENT_ID is not configured. See android/README.md."
            ))
        }

        _isLoading.value = true
        _error.value = null

        return try {
            val credentialManager = CredentialManager.create(activityContext)
            val googleIdOption = GetGoogleIdOption.Builder()
                .setFilterByAuthorizedAccounts(false)  // allow first-time sign-in
                .setServerClientId(webClientId)
                .setAutoSelectEnabled(true)
                .build()

            val request = GetCredentialRequest.Builder()
                .addCredentialOption(googleIdOption)
                .build()

            val credentialResponse = credentialManager.getCredential(activityContext, request)
            val googleCred = GoogleIdTokenCredential.createFrom(credentialResponse.credential.data)

            val authResponse: AuthResponse = apiService.authenticate(
                AuthRequest(
                    provider = "google",
                    idToken = googleCred.idToken,
                    email = googleCred.id,  // Google's `id` field is the email for ID tokens
                ),
            )

            tokenStore.setToken(authResponse.token)
            _currentUser.value = authResponse.user

            // Re-register FCM token now that we have an auth header.
            registerFcmToken()

            Result.success(authResponse.user)
        } catch (e: GetCredentialException) {
            _error.value = "Sign-in cancelled or unavailable"
            Result.failure(e)
        } catch (e: Exception) {
            _error.value = e.message ?: "Sign-in failed"
            Result.failure(e)
        } finally {
            _isLoading.value = false
        }
    }

    suspend fun refreshUserData(): Result<User> {
        if (!tokenStore.isAuthenticatedNow()) {
            return Result.failure(IllegalStateException("Not authenticated"))
        }
        return try {
            val user = apiService.getCurrentUser()
            _currentUser.value = user
            Result.success(user)
        } catch (e: retrofit2.HttpException) {
            if (e.code() == 401) {
                signOut()
            }
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun signOut() {
        tokenStore.clear()
        _currentUser.value = null
    }

    /**
     * Push the current FCM token to the backend so the freshly logged-in user
     * is the recipient of push notifications. Mirrors iOS
     * `messaging(_:didReceiveRegistrationToken:)`.
     */
    private suspend fun registerFcmToken() {
        runCatching {
            val token = FirebaseMessaging.getInstance().token.await()
            apiService.registerDevice(
                DeviceRegistrationRequest(
                    token = token,
                    platform = "android",
                    deviceId = android.os.Build.MODEL,
                    appVersion = packageVersionName(),
                    osVersion = "Android ${android.os.Build.VERSION.RELEASE}",
                ),
            )
        }
    }

    private fun packageVersionName(): String = try {
        @Suppress("DEPRECATION")
        context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "1.0"
    } catch (_: Exception) {
        "1.0"
    }
}
