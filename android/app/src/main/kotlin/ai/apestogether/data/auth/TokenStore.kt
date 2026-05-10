package ai.apestogether.data.auth

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Encrypted-at-rest storage for the API auth token. Counterpart to iOS
 * [KeychainService]. Two layers:
 *  1. AndroidX Security `EncryptedSharedPreferences` for actual secret storage
 *     (AES-256-GCM, key in Android Keystore, hardware-backed where available).
 *  2. A DataStore Flow exposing the `isAuthenticated` boolean so Compose UI
 *     can react to login/logout without polling.
 *
 * The double-storage layout exists because EncryptedSharedPreferences is
 * synchronous (good for Retrofit interceptor) while DataStore is reactive
 * (good for Compose). They're kept in sync on every write.
 */
@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val Context.tokenDataStore by preferencesDataStore(name = "token_meta")

    private val authedKey = stringPreferencesKey("authed")

    private val encrypted by lazy {
        EncryptedSharedPreferences.create(
            context,
            "secure_prefs",
            MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build(),
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    /** Returns the stored token, or null if signed out. */
    suspend fun getToken(): String? = encrypted.getString(KEY_TOKEN, null)

    /** Persist a fresh token after a successful sign-in. */
    suspend fun setToken(token: String) {
        encrypted.edit().putString(KEY_TOKEN, token).apply()
        context.tokenDataStore.edit { it[authedKey] = "1" }
    }

    /** Clear all secret state. Called on sign-out and on 401 responses. */
    suspend fun clear() {
        encrypted.edit().remove(KEY_TOKEN).apply()
        context.tokenDataStore.edit { it.remove(authedKey) }
    }

    /** Reactive auth-state Flow for Compose. */
    val isAuthenticated: Flow<Boolean> =
        context.tokenDataStore.data.map { it[authedKey] == "1" }

    suspend fun isAuthenticatedNow(): Boolean = isAuthenticated.first()

    private companion object {
        const val KEY_TOKEN = "auth_token"
    }
}
