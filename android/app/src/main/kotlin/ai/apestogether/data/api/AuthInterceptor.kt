package ai.apestogether.data.api

import ai.apestogether.data.auth.TokenStore
import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Attaches `Authorization: Bearer <token>` to every outbound request when a
 * token exists in [TokenStore]. Public endpoints (e.g. /leaderboard) safely
 * ignore the header server-side.
 *
 * On a 401 response, callers are responsible for triggering re-authentication
 * (matches iOS [APIError.unauthorized] handling in
 * `AuthenticationManager.refreshUserData`).
 */
@Singleton
class AuthInterceptor @Inject constructor(
    private val tokenStore: TokenStore,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        // runBlocking is acceptable here — Retrofit calls happen on the
        // OkHttp dispatcher thread, never the main thread.
        val token = runBlocking { tokenStore.getToken() }
        val request = if (!token.isNullOrBlank()) {
            original.newBuilder()
                .addHeader("Authorization", "Bearer $token")
                .build()
        } else {
            original
        }
        return chain.proceed(request)
    }
}
