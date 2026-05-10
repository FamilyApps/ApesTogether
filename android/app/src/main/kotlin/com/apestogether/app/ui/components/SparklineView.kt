package com.apestogether.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Gains
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.TextMuted

/**
 * Tiny sparkline chart for leaderboard rows. 1:1 port of iOS
 * [SparklineView] in `PerformanceChartView.swift`.
 *
 * - Portfolio line: 1.5dp solid, [Gains] when [isPositive], [Losses] otherwise.
 * - S&P 500 line: 1dp dashed, [TextMuted] @ 40% opacity.
 * - Empty fallback: a [CardBorder]-tinted rectangle when fewer than 2 valid
 *   portfolio points exist.
 *
 * Both data series may contain null values (matching the API's
 * `[Double?]` shape — backend uses null for missing intra-period samples).
 * Nulls are skipped, but absolute index positions are preserved on the X-axis
 * so the two series stay in temporal sync.
 */
@Composable
fun SparklineView(
    dataPoints: List<Double?>,
    sp500Points: List<Double?> = emptyList(),
    isPositive: Boolean,
    modifier: Modifier = Modifier,
) {
    val portfolioValid = dataPoints.mapIndexedNotNull { i, v -> v?.let { i to it } }
    val sp500Valid = sp500Points.mapIndexedNotNull { i, v -> v?.let { i to it } }

    if (portfolioValid.size < 2) {
        // Fallback: empty placeholder rectangle, same as iOS.
        Canvas(modifier = modifier
            .clip(RoundedCornerShape(2.dp))
            .background(CardBorder.copy(alpha = 0.3f))
        ) {}
        return
    }

    // Compute Y-range across BOTH series so they share a coordinate space —
    // matches Swift Charts default behavior with two LineMark series.
    val combinedValues = portfolioValid.map { it.second } +
        if (sp500Valid.size >= 2) sp500Valid.map { it.second } else emptyList()
    val yMin = combinedValues.min()
    val yMax = combinedValues.max()
    val ySpan = (yMax - yMin).takeIf { it > 0.0 } ?: 1.0

    // X-range covers the full original index space (including nulls), again
    // matching iOS where `id: \.index` keeps nulls' positions reserved.
    val xMaxIndex = (dataPoints.size - 1).coerceAtLeast(1)

    val portfolioColor = if (isPositive) Gains else Losses
    val sp500Color = TextMuted.copy(alpha = 0.4f)

    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height

        fun mapX(idx: Int): Float = (idx.toFloat() / xMaxIndex.toFloat()) * w
        fun mapY(value: Double): Float =
            (h - ((value - yMin) / ySpan).toFloat() * h).coerceIn(0f, h)

        // ── S&P 500 dashed line (drawn first, behind the portfolio line) ──
        if (sp500Valid.size >= 2) {
            val sp500Path = Path().apply {
                sp500Valid.forEachIndexed { i, (idx, v) ->
                    val x = mapX(idx)
                    val y = mapY(v)
                    if (i == 0) moveTo(x, y) else lineTo(x, y)
                }
            }
            drawPath(
                path = sp500Path,
                color = sp500Color,
                style = Stroke(
                    width = 1.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(
                        floatArrayOf(3.dp.toPx(), 2.dp.toPx())
                    ),
                ),
            )
        }

        // ── Portfolio solid line ──
        val portfolioPath = Path().apply {
            portfolioValid.forEachIndexed { i, (idx, v) ->
                val x = mapX(idx)
                val y = mapY(v)
                if (i == 0) moveTo(x, y) else lineTo(x, y)
            }
        }
        drawPath(
            path = portfolioPath,
            color = portfolioColor,
            style = Stroke(width = 1.5.dp.toPx()),
        )
    }
}

