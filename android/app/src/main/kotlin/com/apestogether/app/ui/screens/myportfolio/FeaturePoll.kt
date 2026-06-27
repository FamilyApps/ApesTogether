package com.apestogether.app.ui.screens.myportfolio

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apestogether.app.data.api.ApiService
import com.apestogether.app.data.models.PollData
import com.apestogether.app.data.models.PollVoteRequest
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Inline "Quick Poll" card shown below the Share button on the My Portfolio
 * tab. Direct Compose port of iOS `FeaturePollView`: loads the active poll,
 * lets the user vote once (optimistic update + reload), and renders result
 * bars after voting. Renders nothing when there's no active poll.
 */
@Composable
fun FeaturePoll(modifier: Modifier = Modifier) {
    val viewModel: FeaturePollViewModel = hiltViewModel()
    val state by viewModel.uiState.collectAsState()
    LaunchedEffect(Unit) { viewModel.loadPoll() }

    val poll = state.poll ?: return

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp)
            .padding(bottom = 8.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(CardBackground)
            .border(1.dp, PrimaryAccent.copy(alpha = 0.15f), RoundedCornerShape(12.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // Header
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                Icons.Default.BarChart,
                contentDescription = null,
                tint = PrimaryAccent,
                modifier = Modifier.size(14.dp),
            )
            Spacer(Modifier.width(6.dp))
            Text("Quick Poll", color = TextSecondary, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            if (poll.totalVotes > 0) {
                Text(
                    "${poll.totalVotes} vote" + if (poll.totalVotes == 1) "" else "s",
                    color = TextSecondary.copy(alpha = 0.7f),
                    fontSize = 11.sp,
                )
            }
        }

        // Question
        Text(poll.question, color = TextPrimary, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)

        // Options
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            poll.options.forEach { option ->
                val votes = poll.results.firstOrNull { it.option == option }?.votes ?: 0
                PollOptionRow(
                    option = option,
                    votes = votes,
                    totalVotes = poll.totalVotes,
                    isSelected = state.selectedOption == option,
                    hasVoted = state.hasVoted,
                    onTap = { viewModel.vote(poll.id, option) },
                )
            }
        }

        if (state.hasVoted) {
            Text(
                "Thanks for voting!",
                color = PrimaryAccent.copy(alpha = 0.8f),
                fontSize = 11.sp,
            )
        }
    }
}

@Composable
private fun PollOptionRow(
    option: String,
    votes: Int,
    totalVotes: Int,
    isSelected: Boolean,
    hasVoted: Boolean,
    onTap: () -> Unit,
) {
    val percentage = if (totalVotes > 0) votes.toFloat() / totalVotes.toFloat() else 0f
    val borderColor = if (isSelected) PrimaryAccent.copy(alpha = 0.4f) else TextSecondary.copy(alpha = 0.2f)
    val barColor = if (isSelected) PrimaryAccent.copy(alpha = 0.15f) else TextSecondary.copy(alpha = 0.08f)

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 40.dp)
            .clip(RoundedCornerShape(8.dp))
            .then(
                if (hasVoted) {
                    Modifier.drawBehind {
                        drawRoundRect(
                            color = barColor,
                            size = Size(size.width * percentage, size.height),
                            cornerRadius = CornerRadius(8.dp.toPx()),
                        )
                    }
                } else {
                    Modifier
                }
            )
            .border(1.dp, borderColor, RoundedCornerShape(8.dp))
            .clickable(enabled = !hasVoted) { onTap() }
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            option,
            color = if (isSelected) PrimaryAccent else TextPrimary,
            fontSize = 14.sp,
            fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal,
            maxLines = 2,
            modifier = Modifier.weight(1f),
        )
        if (hasVoted) {
            Spacer(Modifier.width(8.dp))
            Text(
                "${(percentage * 100).toInt()}%",
                color = if (isSelected) PrimaryAccent else TextSecondary,
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@HiltViewModel
class FeaturePollViewModel @Inject constructor(
    private val apiService: ApiService,
) : ViewModel() {

    data class UiState(
        val poll: PollData? = null,
        val selectedOption: String? = null,
        val hasVoted: Boolean = false,
    )

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    fun loadPoll() {
        viewModelScope.launch {
            runCatching { apiService.getActivePoll() }
                .onSuccess { response ->
                    val poll = response.poll
                    val voted = poll?.userVoted
                    _uiState.value = UiState(
                        poll = poll,
                        selectedOption = voted,
                        hasVoted = voted != null,
                    )
                }
        }
    }

    fun vote(pollId: Int, option: String) {
        val current = _uiState.value
        if (current.hasVoted) return
        // Optimistic update, then confirm + reload counts. Revert on failure.
        _uiState.value = current.copy(selectedOption = option, hasVoted = true)
        viewModelScope.launch {
            runCatching {
                apiService.voteOnPoll(PollVoteRequest(pollId = pollId, selectedOption = option))
            }
                .onSuccess { loadPoll() }
                .onFailure { _uiState.value = current.copy(selectedOption = null, hasVoted = false) }
        }
    }
}
