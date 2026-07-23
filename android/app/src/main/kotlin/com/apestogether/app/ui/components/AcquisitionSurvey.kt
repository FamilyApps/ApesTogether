package com.apestogether.app.ui.components

import android.util.Log
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.AcquisitionSourceRequest
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.onboarding.OnboardingPreferences
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Display label → backend source key. Order = display order. */
private val SURVEY_OPTIONS = listOf(
    "X / Twitter" to "x",
    "TikTok" to "tiktok",
    "Instagram" to "instagram",
    "Reddit" to "reddit",
    "Friend" to "friend",
    "Search" to "search",
    "Press / article" to "press",
    "Other" to "other",
)

/**
 * One-shot "How did you hear about us?" attribution survey (marketing gap #7).
 *
 * Self-contained host: drop into any authed surface. Shows a one-tap chip
 * dialog once per install (DataStore-gated), ~1.5 s after first composition
 * so it never races the initial screen load. Mirrors iOS
 * [AcquisitionSurveyView]. The backend keeps only the FIRST answer, so a
 * reinstall re-ask can't corrupt attribution data.
 */
@Composable
fun AcquisitionSurveyHost() {
    val viewModel: AcquisitionSurveyViewModel = hiltViewModel()
    val done by viewModel.surveyDone.collectAsState()
    var visible by remember { mutableStateOf(false) }

    LaunchedEffect(done) {
        if (done == false) {
            delay(1500)
            visible = true
        }
    }

    if (done == false && visible) {
        Dialog(onDismissRequest = { viewModel.dismiss() }) {
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = CardBackground,
                border = BorderStroke(1.dp, CardBorder),
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        "How did you hear about us?",
                        color = TextPrimary,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "One tap — it helps us know where to show up.",
                        color = TextSecondary,
                        fontSize = 13.sp,
                        modifier = Modifier.padding(top = 4.dp, bottom = 14.dp),
                    )
                    SURVEY_OPTIONS.chunked(2).forEach { rowOptions ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 8.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            rowOptions.forEach { (label, key) ->
                                Surface(
                                    onClick = { viewModel.answer(key) },
                                    shape = RoundedCornerShape(10.dp),
                                    color = CardBackground,
                                    border = BorderStroke(1.dp, CardBorder),
                                    modifier = Modifier.weight(1f),
                                ) {
                                    Text(
                                        label,
                                        color = TextPrimary,
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Medium,
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(vertical = 12.dp),
                                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                    )
                                }
                            }
                        }
                    }
                    TextButton(
                        onClick = { viewModel.dismiss() },
                        modifier = Modifier.align(Alignment.CenterHorizontally),
                    ) {
                        Text("Skip", color = TextMuted, fontSize = 13.sp)
                    }
                }
            }
        }
    }
}

@HiltViewModel
class AcquisitionSurveyViewModel @Inject constructor(
    private val apiService: ApiService,
    private val onboardingPreferences: OnboardingPreferences,
) : ViewModel() {

    /** null = DataStore hasn't emitted yet; never show until it says false. */
    val surveyDone: StateFlow<Boolean?> = onboardingPreferences.acquisitionSurveyDone
        .stateIn<Boolean?>(viewModelScope, SharingStarted.Eagerly, null)

    fun answer(source: String) {
        viewModelScope.launch {
            // Mark done first — losing one answer to a network blip beats
            // nagging the user twice.
            onboardingPreferences.markAcquisitionSurveyDone()
            try {
                apiService.setAcquisitionSource(AcquisitionSourceRequest(source))
            } catch (e: Exception) {
                Log.w("AcquisitionSurvey", "Failed to submit source '$source'", e)
            }
        }
    }

    fun dismiss() {
        viewModelScope.launch { onboardingPreferences.markAcquisitionSurveyDone() }
    }
}
