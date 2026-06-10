package com.apestogether.app.ui.screens.onboarding

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.HeroBackgroundEnd
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary

/**
 * Post-subscribe nudge — direct port of iOS [EarnNudgeView]. Shown
 * immediately after a successful Play Billing subscription completes;
 * congratulates the user and points them at the "Add Your Stocks" flow so
 * they can become a creator and start earning.
 *
 * Branches on [userHasStocks]:
 *  - Pure subscribers (no own holdings) get the "earn money" pitch:
 *      - "Add Your Stocks" → [onAddStocks] — navigates to [AddStocksScreen].
 *      - "Not now"         → [onSkip] — dismisses to the main tabs.
 *  - Users who are already creators (have their own stocks) skip the pitch
 *    entirely and instead get:
 *      - "View {trader}'s Portfolio" → [onViewPortfolio] — opens the
 *        portfolio they just subscribed to.
 *      - "Done"                      → [onSkip] — dismisses to the main tabs.
 */
@Composable
fun EarnNudgeScreen(
    subscribedToUsername: String,
    onAddStocks: () -> Unit,
    onSkip: () -> Unit,
    userHasStocks: Boolean = false,
    onViewPortfolio: () -> Unit = {},
) {
    var checkmarkVisible by remember { mutableStateOf(false) }

    // Spring-pop the checkmark on first render — same vibe as the iOS view
    // which animates `scaleEffect` + `opacity` on `onAppear`.
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(150)
        checkmarkVisible = true
    }
    val scale by animateFloatAsState(
        targetValue = if (checkmarkVisible) 1f else 0.5f,
        animationSpec = spring(
            dampingRatio = Spring.DampingRatioMediumBouncy,
            stiffness = Spring.StiffnessMedium,
        ),
        label = "earn_nudge_check_scale",
    )
    val opacity by animateFloatAsState(
        targetValue = if (checkmarkVisible) 1f else 0f,
        animationSpec = tween(durationMillis = 400),
        label = "earn_nudge_check_alpha",
    )

    val heroGradient = Brush.verticalGradient(
        colors = listOf(AppBackground, HeroBackgroundEnd),
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(heroGradient),
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.weight(1f))

            // Animated success checkmark
            Box(
                modifier = Modifier
                    .size(100.dp)
                    .clip(CircleShape)
                    .background(PrimaryAccent.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Default.CheckCircle,
                    contentDescription = null,
                    tint = PrimaryAccent,
                    modifier = Modifier
                        .size(56.dp)
                        .scale(scale)
                        .alpha(opacity),
                )
            }

            Spacer(Modifier.height(24.dp))

            Text(
                text = "You're in!",
                color = TextPrimary,
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
            )

            Spacer(Modifier.height(12.dp))

            Text(
                text = "You'll get notified as soon as\n${subscribedToUsername.ifBlank { "this trader" }} makes a trade.",
                color = TextSecondary,
                fontSize = 16.sp,
                textAlign = TextAlign.Center,
                lineHeight = 22.sp,
            )

            Spacer(Modifier.weight(1f))

            if (userHasStocks) {
                // Already a creator → skip the earn pitch; offer to jump
                // straight into the portfolio they just subscribed to.
                Button(
                    onClick = onViewPortfolio,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 40.dp)
                        .height(54.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                ) {
                    Text(
                        text = subscribedToUsername.takeIf { it.isNotBlank() }
                            ?.let { "View $it's Portfolio" }
                            ?: "View Portfolio",
                        color = AppBackground,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }

                TextButton(
                    onClick = onSkip,
                    modifier = Modifier.padding(top = 12.dp, bottom = 50.dp),
                ) {
                    Text(
                        "Done",
                        color = TextSecondary,
                        fontSize = 14.sp,
                    )
                }
            } else {
                // Pure subscriber → pitch becoming a creator.
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 20.dp)
                        .clip(RoundedCornerShape(16.dp))
                        .background(CardBackground)
                        .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Icon(
                        imageVector = Icons.Default.AttachMoney,
                        contentDescription = null,
                        tint = PrimaryAccent,
                        modifier = Modifier.size(28.dp),
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(
                            "Want to earn money too?",
                            color = TextPrimary,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            "Add your stocks and get paid when others follow your trades.",
                            color = TextSecondary,
                            fontSize = 12.sp,
                            lineHeight = 16.sp,
                        )
                    }
                }

                Spacer(Modifier.height(24.dp))

                Button(
                    onClick = onAddStocks,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 40.dp)
                        .height(54.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
                ) {
                    Text(
                        "Add Your Stocks",
                        color = AppBackground,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }

                TextButton(
                    onClick = onSkip,
                    modifier = Modifier.padding(top = 12.dp, bottom = 50.dp),
                ) {
                    Text(
                        "Not now",
                        color = TextSecondary,
                        fontSize = 14.sp,
                    )
                }
            }
        }
    }
}
