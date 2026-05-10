package com.apestogether.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccessTime
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.apestogether.app.data.models.ChartPoint
import com.apestogether.app.ui.theme.AppBackground
import com.apestogether.app.ui.theme.CardBackground
import com.apestogether.app.ui.theme.CardBorder
import com.apestogether.app.ui.theme.Gains
import com.apestogether.app.ui.theme.Losses
import com.apestogether.app.ui.theme.TextMuted
import com.apestogether.app.ui.theme.TextPrimary
import kotlin.math.absoluteValue
import kotlin.math.ceil

/**
 * Performance chart card. Direct port of iOS [PerformanceChartView] in
 * `ios/.../PerformanceChartView.swift`.
 *
 * Components (top → bottom, matching iOS exactly):
 *  1. Summary header — alpha vs S&P 500 in big gain/loss-colored type, with
 *     compact portfolio + S&P side-by-side returns to the right.
 *  2. Chart canvas (200dp tall): portfolio line (solid 2.5dp), S&P 500
 *     line (dashed 1.5dp), zero rule line. Axes are unobtrusive: only
 *     "boundary" date labels (from non-empty `point.date` values) appear
 *     on the X-axis; the Y-axis shows 4 evenly-spaced percentage ticks
 *     on the right.
 *  3. Legend (Portfolio dot + S&P dashed segment).
 *  4. Period selector (1D / 1W / 1M / 3M / YTD / 1Y) — tinted with the
 *     portfolio color, like iOS.
 *  5. Optional eligibility banner if [leaderboardEligible] is false.
 *
 * The whole card uses [CardBackground] + [CardBorder] just like iOS.
 */
@Composable
fun PerformanceChartCard(
    chartData: List<ChartPoint>,
    portfolioReturn: Double,
    sp500Return: Double,
    selectedPeriod: String,
    onPeriodChange: (String) -> Unit,
    portfolioLabel: String = "Your Portfolio",
    leaderboardEligible: Boolean = true,
    daysActive: Int = 0,
    daysRequired: Int = 0,
    eligibleDate: String? = null,
    modifier: Modifier = Modifier,
) {
    val portfolioColor = if (portfolioReturn >= 0) Gains else Losses

    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(CardBackground)
            .border(0.5.dp, CardBorder, RoundedCornerShape(16.dp))
    ) {
        ChartSummaryHeader(
            portfolioReturn = portfolioReturn,
            sp500Return = sp500Return,
            portfolioLabel = portfolioLabel,
            portfolioColor = portfolioColor,
        )

        if (chartData.isEmpty()) {
            ChartEmptyState()
        } else {
            ChartCanvas(
                chartData = chartData,
                portfolioColor = portfolioColor,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp)
                    .padding(horizontal = 8.dp),
            )
        }

        ChartLegend(portfolioColor = portfolioColor)

        PeriodSelector(
            selected = selectedPeriod,
            onChange = onPeriodChange,
            tint = portfolioColor,
            paddingBottom = if (leaderboardEligible) 16.dp else 8.dp,
        )

        if (!leaderboardEligible) {
            EligibilityBanner(
                daysActive = daysActive,
                daysRequired = daysRequired,
                eligibleDate = eligibleDate,
            )
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Header
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun ChartSummaryHeader(
    portfolioReturn: Double,
    sp500Return: Double,
    portfolioLabel: String,
    portfolioColor: Color,
) {
    val alpha = portfolioReturn - sp500Return

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 0.dp)
            .padding(top = 16.dp, bottom = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                text = if (alpha >= 0) "Beating S&P by" else "Trailing S&P by",
                color = TextMuted,
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
            )
            Text(
                text = formatPercent(alpha, decimals = 2),
                color = if (alpha >= 0) Gains else Losses,
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
            )
        }

        Column(
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            CompactReturnRow(
                label = portfolioLabel,
                value = portfolioReturn,
                valueColor = portfolioColor,
            )
            CompactReturnRow(
                label = "S&P 500",
                value = sp500Return,
                valueColor = (if (sp500Return >= 0) Gains else Losses).copy(alpha = 0.7f),
            )
        }
    }
}

@Composable
private fun CompactReturnRow(label: String, value: Double, valueColor: Color) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(label, color = TextMuted, fontSize = 10.sp, fontWeight = FontWeight.Medium)
        Text(
            text = formatPercent(value, decimals = 1),
            color = valueColor,
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Empty
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun ChartEmptyState() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(200.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(
                imageVector = Icons.Default.ShowChart,
                contentDescription = null,
                tint = TextMuted,
                modifier = Modifier.size(36.dp),
            )
            Text(
                text = "Chart data will appear once\nyour portfolio has history",
                color = TextMuted,
                fontSize = 12.sp,
            )
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Canvas (the actual chart)
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun ChartCanvas(
    chartData: List<ChartPoint>,
    portfolioColor: Color,
    modifier: Modifier = Modifier,
) {
    val portfolioPoints = chartData.mapIndexedNotNull { i, p ->
        p.portfolio?.let { i to it }
    }
    val sp500Points = chartData.mapIndexedNotNull { i, p ->
        p.sp500?.let { i to it }
    }

    val xAxisTicks: List<Int> = run {
        val labeled = chartData.indices.filter { chartData[it].date.isNotEmpty() }
        if (labeled.isNotEmpty()) labeled else evenlySpacedIndices(chartData.size, desired = 5)
    }

    val combinedValues = portfolioPoints.map { it.second } + sp500Points.map { it.second } + 0.0
    val rawMin = combinedValues.min()
    val rawMax = combinedValues.max()
    // Pad the Y range a bit so lines don't touch the edges.
    val pad = ((rawMax - rawMin) * 0.1).coerceAtLeast(0.5)
    val yMin = rawMin - pad
    val yMax = rawMax + pad
    val ySpan = (yMax - yMin).takeIf { it > 0.0 } ?: 1.0

    // 4 ticks evenly spaced
    val yTicks: List<Double> = niceTicks(yMin, yMax, count = 4)

    val xMaxIndex = (chartData.size - 1).coerceAtLeast(1)
    val mutedColor = TextMuted

    val density = LocalDensity.current
    val xLabelPx = with(density) { 9.sp.toPx() }
    val yLabelPx = with(density) { 9.sp.toPx() }

    Canvas(modifier = modifier) {
        val rightPad = 36f * density.density       // room for right-aligned Y labels
        val bottomPad = 20f * density.density      // room for bottom X labels
        val leftPad = 4f * density.density
        val topPad = 4f * density.density

        val plotW = (size.width - leftPad - rightPad).coerceAtLeast(1f)
        val plotH = (size.height - topPad - bottomPad).coerceAtLeast(1f)

        fun mapX(idx: Int): Float = leftPad + (idx.toFloat() / xMaxIndex.toFloat()) * plotW
        fun mapY(value: Double): Float =
            topPad + (((yMax - value) / ySpan).toFloat()) * plotH

        // ── Y gridlines + labels ──
        for (tick in yTicks) {
            val y = mapY(tick)
            drawLine(
                color = CardBorder.copy(alpha = 0.5f),
                start = Offset(leftPad, y),
                end = Offset(leftPad + plotW, y),
                strokeWidth = 0.3f * density.density,
            )
            drawContext.canvas.nativeCanvas.apply {
                val paint = android.graphics.Paint().apply {
                    color = mutedColor.toArgb()
                    textSize = yLabelPx
                    textAlign = android.graphics.Paint.Align.LEFT
                    isAntiAlias = true
                }
                drawText(
                    formatYLabel(tick),
                    leftPad + plotW + 4f * density.density,
                    y + yLabelPx / 2f,
                    paint,
                )
            }
        }

        // ── Zero line (heavier than gridlines) ──
        if (yMin <= 0.0 && yMax >= 0.0) {
            val zeroY = mapY(0.0)
            drawLine(
                color = TextMuted.copy(alpha = 0.2f),
                start = Offset(leftPad, zeroY),
                end = Offset(leftPad + plotW, zeroY),
                strokeWidth = 0.5f * density.density,
            )
        }

        // ── S&P 500 dashed line ──
        if (sp500Points.size >= 2) {
            val path = Path().apply {
                sp500Points.forEachIndexed { i, (idx, v) ->
                    val x = mapX(idx)
                    val y = mapY(v)
                    if (i == 0) moveTo(x, y) else lineTo(x, y)
                }
            }
            drawPath(
                path = path,
                color = TextMuted.copy(alpha = 0.5f),
                style = Stroke(
                    width = 1.5f * density.density,
                    pathEffect = PathEffect.dashPathEffect(
                        floatArrayOf(5f * density.density, 3f * density.density)
                    ),
                ),
            )
        }

        // ── Portfolio solid line ──
        if (portfolioPoints.size >= 2) {
            val path = Path().apply {
                portfolioPoints.forEachIndexed { i, (idx, v) ->
                    val x = mapX(idx)
                    val y = mapY(v)
                    if (i == 0) moveTo(x, y) else lineTo(x, y)
                }
            }
            drawPath(
                path = path,
                color = portfolioColor,
                style = Stroke(width = 2.5f * density.density),
            )
        }

        // ── X-axis labels ──
        drawContext.canvas.nativeCanvas.apply {
            val paint = android.graphics.Paint().apply {
                color = mutedColor.toArgb()
                textSize = xLabelPx
                textAlign = android.graphics.Paint.Align.CENTER
                isAntiAlias = true
            }
            for (idx in xAxisTicks) {
                if (idx >= chartData.size) continue
                val label = chartData[idx].date
                if (label.isEmpty()) continue
                val x = mapX(idx)
                val y = topPad + plotH + xLabelPx + 2f * density.density
                drawText(label, x, y, paint)
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Legend
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun ChartLegend(portfolioColor: Color) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp),
        horizontalArrangement = Arrangement.Center,
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            modifier = Modifier.padding(end = 16.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .clip(CircleShape)
                    .background(portfolioColor)
            )
            Text("Portfolio", color = TextMuted, fontSize = 10.sp)
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Canvas(
                modifier = Modifier
                    .width(14.dp)
                    .height(2.dp)
            ) {
                drawLine(
                    color = TextMuted.copy(alpha = 0.5f),
                    start = Offset(0f, size.height / 2f),
                    end = Offset(size.width, size.height / 2f),
                    strokeWidth = 1.5f,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(3f, 2f)),
                )
            }
            Text("S&P 500", color = TextMuted, fontSize = 10.sp)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Period selector
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun PeriodSelector(
    selected: String,
    onChange: (String) -> Unit,
    tint: Color,
    paddingBottom: androidx.compose.ui.unit.Dp,
) {
    val periods = listOf("1D", "1W", "1M", "3M", "YTD", "1Y")
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 0.dp)
            .padding(top = 12.dp, bottom = paddingBottom),
        horizontalArrangement = Arrangement.spacedBy(0.dp),
    ) {
        periods.forEach { p ->
            val isActive = p == selected
            Box(
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(6.dp))
                    .background(if (isActive) tint.copy(alpha = 0.15f) else Color.Transparent)
                    .clickable { onChange(p) }
                    .padding(vertical = 8.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = p,
                    color = if (isActive) tint else TextMuted,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Eligibility banner
// ─────────────────────────────────────────────────────────────────────────

@Composable
private fun EligibilityBanner(
    daysActive: Int,
    daysRequired: Int,
    eligibleDate: String?,
) {
    val orange = Color(0xFFFFA500)
    val text = remember(daysActive, daysRequired, eligibleDate) {
        eligibilityBannerText(daysActive, daysRequired, eligibleDate)
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp)
            .padding(bottom = 12.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(orange.copy(alpha = 0.08f))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Icon(
            imageVector = Icons.Default.AccessTime,
            contentDescription = null,
            tint = orange,
            modifier = Modifier.size(11.dp),
        )
        Text(
            text = text,
            color = orange,
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

private fun eligibilityBannerText(
    daysActive: Int,
    daysRequired: Int,
    eligibleDate: String?,
): String {
    val monthsNeeded = ceil(daysRequired / 30.0).toInt().coerceAtLeast(1)
    val monthsHave = (daysActive / 30).coerceAtLeast(0)
    val monthsRemaining = monthsNeeded - monthsHave

    if (!eligibleDate.isNullOrEmpty()) {
        // Backend gives an ISO date like "2026-08-15" — show it directly.
        return "Ineligible for leaderboard until $eligibleDate"
    }
    if (monthsRemaining > 0) {
        val unit = if (monthsRemaining == 1) "month" else "months"
        return "Ineligible for leaderboard — $monthsRemaining more $unit of data needed"
    }
    return "Ineligible for leaderboard for this period"
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

private fun evenlySpacedIndices(count: Int, desired: Int): List<Int> {
    if (count <= 1) return if (count == 1) listOf(0) else emptyList()
    val step = (count / desired).coerceAtLeast(1)
    val ticks = mutableListOf<Int>()
    var i = 0
    while (i < count) {
        ticks.add(i)
        i += step
    }
    if (ticks.lastOrNull() != count - 1) ticks.add(count - 1)
    return ticks
}

private fun niceTicks(min: Double, max: Double, count: Int): List<Double> {
    if (max <= min) return listOf(min)
    val step = (max - min) / (count - 1)
    return (0 until count).map { min + step * it }
}

private fun formatYLabel(value: Double): String {
    val abs = value.absoluteValue
    return if (abs >= 10) "%.0f%%".format(value)
    else "%.1f%%".format(value)
}

private fun formatPercent(value: Double, decimals: Int): String {
    val sign = if (value >= 0) "+" else "−"
    val abs = value.absoluteValue
    return "$sign${"%.${decimals}f".format(abs)}%"
}

