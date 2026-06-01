package com.apestogether.app.ui.screens.login

import com.apestogether.app.data.auth.AuthRepository
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.HeroBackgroundEnd
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import android.content.Context
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.size
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.sp
import com.apestogether.app.R
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Initial sign-in screen. Equivalent to iOS [LoginView].
 *
 * Uses Google Sign-In via the Credential Manager API (the modern
 * replacement for GoogleSignIn). The acquired ID token is exchanged for an
 * Apes Together API token by [AuthRepository.signInWithGoogle].
 */
@Composable
fun LoginScreen(onSignedIn: () -> Unit) {
    val viewModel: LoginViewModel = hiltViewModel()
    val isLoading by viewModel.isLoading.collectAsState()
    val error by viewModel.error.collectAsState()
    val signedIn by viewModel.signedIn.collectAsState()
    val context = LocalContext.current

    LaunchedEffect(signedIn) {
        if (signedIn) onSignedIn()
    }

    // Hero gradient — same as iOS LinearGradient.heroGradient.
    val heroGradient = Brush.verticalGradient(
        colors = listOf(AppBackground, HeroBackgroundEnd),
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(heroGradient)
            .padding(horizontal = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.weight(1f))

        // App logo — matches iOS Image("AppLogo"): 100dp, rounded, accent glow.
        Image(
            painter = painterResource(R.drawable.app_logo),
            contentDescription = null,
            modifier = Modifier
                .size(100.dp)
                .shadow(
                    elevation = 20.dp,
                    shape = RoundedCornerShape(22.dp),
                    spotColor = PrimaryAccent,
                    ambientColor = PrimaryAccent,
                )
                .clip(RoundedCornerShape(22.dp)),
        )

        Spacer(Modifier.height(20.dp))

        // Two-tone wordmark: "Apes" (white) + " Together" (accent).
        Text(
            text = buildAnnotatedString {
                withStyle(SpanStyle(color = TextPrimary)) { append("Apes") }
                withStyle(SpanStyle(color = PrimaryAccent)) { append(" Together") }
            },
            fontSize = 36.sp,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(8.dp))

        Text(
            text = "Follow top traders.\nGet real-time alerts.",
            color = TextSecondary,
            fontSize = 20.sp,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.weight(1f))

        if (isLoading) {
            CircularProgressIndicator(color = PrimaryAccent)
        } else {
            // Mirrors iOS SignInWithAppleButton(.white): a white pill, height 54,
            // corner 12 — but with the Google "G" mark + "Sign in with Google"
            // since Android uses Google auth instead of Apple.
            Button(
                onClick = { viewModel.signInWithGoogle(context) },
                colors = ButtonDefaults.buttonColors(containerColor = Color.White),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().height(54.dp),
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center,
                ) {
                    Image(
                        painter = painterResource(R.drawable.ic_google_g),
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                    )
                    Spacer(Modifier.width(12.dp))
                    Text(
                        "Sign in with Google",
                        color = Color(0xFF1F1F1F),
                        fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }

        if (!error.isNullOrBlank()) {
            Spacer(Modifier.height(16.dp))
            Text(
                text = error.orEmpty(),
                color = MaterialTheme.colorScheme.error,
                fontSize = 13.sp,
                textAlign = TextAlign.Center,
            )
        }

        Spacer(Modifier.height(60.dp))

        // Terms — mirrors iOS bottom disclaimer.
        Text(
            text = "By signing in, you agree to our Terms of Service and Privacy Policy",
            color = TextMuted,
            fontSize = 12.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(bottom = 20.dp),
        )
    }
}

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {
    val isLoading: StateFlow<Boolean> = authRepository.isLoading
    val error: StateFlow<String?> = authRepository.error

    private val _signedIn = MutableStateFlow(false)
    val signedIn: StateFlow<Boolean> = _signedIn.asStateFlow()

    fun signInWithGoogle(context: Context) {
        viewModelScope.launch {
            val result = authRepository.signInWithGoogle(context)
            if (result.isSuccess) _signedIn.value = true
        }
    }
}
