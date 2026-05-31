package com.apestogether.app.ui.screens.onboarding

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import com.apestogether.app.R
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.HeroBackgroundEnd
import com.apestogether.app.ui.theme.PrimaryAccent
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import com.apestogether.app.ui.theme.TextSecondary
import kotlinx.coroutines.launch

/**
 * First-launch carousel. Direct port of iOS [WelcomeCarouselView].
 *
 * Two pages:
 *  1. "Know when the best traders buy and sell" (bell icon, accent on the
 *     phrase "buy and sell").
 *  2. "Get paid to share your trades" (dollar icon, accent on "your trades").
 *
 * Skip / Next / Get Started CTAs all funnel through [onComplete] which
 * persists `hasCompletedOnboarding = true` and exits the carousel.
 */
@Composable
fun WelcomeCarouselScreen(onComplete: () -> Unit) {
    val pagerState = rememberPagerState(pageCount = { 2 })
    val scope = rememberCoroutineScope()

    // Background gradient — same as iOS LinearGradient.heroGradient.
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
        ) {
            // Skip button
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp, vertical = 16.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(onClick = onComplete) {
                    Text(
                        "Skip",
                        color = TextSecondary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }

            // Pager
            HorizontalPager(
                state = pagerState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentPadding = PaddingValues(horizontal = 0.dp),
            ) { page ->
                when (page) {
                    0 -> CarouselPage(
                        icon = Icons.Default.Notifications,
                        headline = "Know when the best\ntraders buy and sell",
                        accentWord = "buy and sell",
                        subtext = "Get real-time alerts the moment\ntop investors make a move",
                        imageRes = R.drawable.carousel1,
                    )
                    1 -> CarouselPage(
                        icon = Icons.Default.AttachMoney,
                        headline = "Get paid to share\nyour trades",
                        accentWord = "your trades",
                        subtext = "Build a following and earn\nfrom every subscriber",
                        imageRes = R.drawable.carousel2,
                    )
                }
            }

            // Page indicator dots
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 32.dp),
                horizontalArrangement = Arrangement.Center,
            ) {
                repeat(2) { index ->
                    Box(
                        modifier = Modifier
                            .padding(horizontal = 4.dp)
                            .size(8.dp)
                            .clip(CircleShape)
                            .background(
                                if (pagerState.currentPage == index) PrimaryAccent
                                else TextMuted
                            ),
                    )
                }
            }

            // Primary CTA
            Button(
                onClick = {
                    if (pagerState.currentPage < 1) {
                        scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) }
                    } else {
                        onComplete()
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 40.dp)
                    .padding(bottom = 50.dp)
                    .height(54.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryAccent),
            ) {
                Text(
                    text = if (pagerState.currentPage < 1) "Next" else "Get Started",
                    color = AppBackground,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun CarouselPage(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    headline: String,
    accentWord: String,
    subtext: String,
    imageRes: Int? = null,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        // Illustration (matches iOS Carousel1/Carousel2 assets); falls back
        // to an icon-in-a-circle when no image is supplied.
        if (imageRes != null) {
            Image(
                painter = painterResource(imageRes),
                contentDescription = null,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .height(200.dp)
                    .clip(RoundedCornerShape(16.dp)),
            )
        } else {
            Box(
                modifier = Modifier
                    .size(120.dp)
                    .clip(CircleShape)
                    .background(PrimaryAccent.copy(alpha = 0.12f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = PrimaryAccent,
                    modifier = Modifier.size(50.dp),
                )
            }
        }

        Spacer(Modifier.height(32.dp))

        // Headline with optional accent word
        val headlineText = buildAnnotatedString {
            val idx = headline.indexOf(accentWord)
            if (idx >= 0) {
                withStyle(SpanStyle(color = TextPrimary)) {
                    append(headline.substring(0, idx))
                }
                withStyle(SpanStyle(color = PrimaryAccent)) {
                    append(accentWord)
                }
                withStyle(SpanStyle(color = TextPrimary)) {
                    append(headline.substring(idx + accentWord.length))
                }
            } else {
                withStyle(SpanStyle(color = TextPrimary)) {
                    append(headline)
                }
            }
        }
        Text(
            text = headlineText,
            fontSize = 28.sp,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center,
            lineHeight = 34.sp,
        )

        Spacer(Modifier.height(16.dp))

        Text(
            text = subtext,
            color = TextSecondary,
            fontSize = 16.sp,
            textAlign = TextAlign.Center,
            lineHeight = 22.sp,
        )
    }
}
