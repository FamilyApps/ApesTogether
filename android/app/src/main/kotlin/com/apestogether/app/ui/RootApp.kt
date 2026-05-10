package com.apestogether.app.ui

import com.apestogether.app.data.auth.AuthRepository
import com.apestogether.app.ui.navigation.RootNavGraph
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.compose.rememberNavController
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Top-level composable hosted by [com.apestogether.app.MainActivity]. Owns the
 * NavController and observes auth state to choose between the login flow and
 * the main tab UI.
 *
 * Counterpart to the iOS [ContentView] root switch.
 */
@Composable
fun RootApp(initialDeepLinkUri: Uri? = null) {
    val rootViewModel: RootViewModel = hiltViewModel()
    val isAuthed by rootViewModel.isAuthenticated.collectAsState(initial = false)
    val navController = rememberNavController()

    // On cold start (or whenever auth flips to true) hydrate the cached User
    // object from the backend. Without this, [AuthRepository.currentUser]
    // remains null after relaunch (we only have a token, not a user payload),
    // which causes MyPortfolioScreen to render its empty state even when the
    // signed-in user has a portfolio_slug. iOS does the equivalent in
    // `AuthenticationManager.refreshUserData()` on `ContentView.onAppear`.
    LaunchedEffect(isAuthed) {
        if (isAuthed) {
            rootViewModel.hydrateUser()
        }
    }

    RootNavGraph(
        navController = navController,
        startAuthenticated = isAuthed,
        initialDeepLinkUri = initialDeepLinkUri,
    )
}

@HiltViewModel
class RootViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {
    val isAuthenticated = authRepository.isAuthenticated

    /** Refreshes [AuthRepository.currentUser] from the backend; safe to call
     *  multiple times (network failures fall back to the existing value). */
    fun hydrateUser() {
        viewModelScope.launch {
            authRepository.refreshUserData()
        }
    }
}
