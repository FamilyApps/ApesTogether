package ai.apestogether.ui

import ai.apestogether.data.auth.AuthRepository
import ai.apestogether.ui.navigation.RootNavGraph
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.navigation.compose.rememberNavController
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

/**
 * Top-level composable hosted by [ai.apestogether.MainActivity]. Owns the
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

    RootNavGraph(
        navController = navController,
        startAuthenticated = isAuthed,
        initialDeepLinkUri = initialDeepLinkUri,
    )
}

@HiltViewModel
class RootViewModel @Inject constructor(
    authRepository: AuthRepository,
) : ViewModel() {
    val isAuthenticated = authRepository.isAuthenticated
}
