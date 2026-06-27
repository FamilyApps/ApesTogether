package com.apestogether.app.ui.share

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import kotlin.math.abs

/**
 * Data needed to render a portfolio performance share card. Mirrors the inputs
 * of iOS `PortfolioShareCardView`.
 */
data class ShareCardData(
    val username: String,
    val portfolioReturn: Double,
    val sp500Return: Double,
    val chartValues: List<Double>,
    val holdingsCount: Int,
    val subscriberCount: Int,
    val period: String,
    val slug: String,
)

/**
 * Renders a branded portfolio-performance card to a PNG and launches the system
 * share sheet (image + a follow link). Compose-free, native-Canvas renderer —
 * deterministic, fully off-screen, and works on all supported API levels. This
 * is the Android equivalent of iOS `ShareCardGenerator.generatePortfolioCard`
 * (which uses SwiftUI `ImageRenderer`).
 */
object ShareCard {

    // Brand palette — matches the iOS card hex values exactly.
    private const val BG_MAIN = 0xFF141A17.toInt()
    private const val BG_HEADER = 0xFF0D1210.toInt()
    private const val BG_FOOTER = 0xFF0A0F0D.toInt()
    private const val ACCENT = 0xFF00D9A5.toInt()
    private const val MUTED = 0xFF9CA3AF.toInt()
    private const val GREEN = 0xFF22C55E.toInt()
    private const val RED = 0xFFEF4444.toInt()
    private const val BORDER = 0xFF1F2A24.toInt()
    private const val WHITE = 0xFFFFFFFF.toInt()

    private const val W = 1140              // 380pt @3x
    private const val HEADER_H = 168
    private const val FOOTER_H = 156
    private const val PAD = 60               // 20pt @3x
    private const val RADIUS = 48f           // 16pt @3x

    suspend fun sharePortfolioPerformance(context: Context, data: ShareCardData) {
        val bitmap = withContext(Dispatchers.Default) { render(data) }
        val uri = withContext(Dispatchers.IO) {
            val dir = File(context.cacheDir, "shared_images").apply { mkdirs() }
            val file = File(dir, "portfolio_${data.slug}.png")
            FileOutputStream(file).use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        }
        val shareText = "Check out my portfolio on ApesTogether! \uD83E\uDD8D\uD83D\uDCC8\n" +
            "https://apestogether.ai/p/${data.slug}"
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "image/png"
            putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_TEXT, shareText)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(Intent.createChooser(intent, "Share my performance"))
    }

    private fun render(data: ShareCardData): Bitmap {
        val hasChart = data.chartValues.size >= 2
        val chartBlock = if (hasChart) 288 else 0   // 240 chart + 48 gap
        val mainH = PAD + 144 + 48 + 224 + chartBlock + PAD
        val h = HEADER_H + mainH + FOOTER_H

        val bitmap = Bitmap.createBitmap(W, h, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)

        val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
        val card = RectF(0f, 0f, W.toFloat(), h.toFloat())

        // Clip to the rounded-rect card so the header/footer bands inherit the
        // corner radius, then paint the layered backgrounds.
        canvas.save()
        val clip = Path().apply { addRoundRect(card, RADIUS, RADIUS, Path.Direction.CW) }
        canvas.clipPath(clip)
        fill.color = BG_MAIN
        canvas.drawRect(card, fill)
        fill.color = BG_HEADER
        canvas.drawRect(0f, 0f, W.toFloat(), HEADER_H.toFloat(), fill)
        fill.color = BG_FOOTER
        canvas.drawRect(0f, (h - FOOTER_H).toFloat(), W.toFloat(), h.toFloat(), fill)

        drawHeader(canvas, fill)
        drawContent(canvas, fill, data, hasChart)
        drawFooter(canvas, fill, data, h)
        canvas.restore()

        // Border, inset so the stroke is fully inside the bitmap (not clipped).
        val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 3f
            color = BORDER
        }
        val inset = 4f
        canvas.drawRoundRect(
            RectF(inset, inset, W - inset, h - inset),
            RADIUS, RADIUS, borderPaint,
        )
        return bitmap
    }

    private fun textPaint(color: Int, size: Float, bold: Boolean, mono: Boolean = false) =
        Paint(Paint.ANTI_ALIAS_FLAG).apply {
            this.color = color
            textSize = size
            typeface = when {
                mono -> Typeface.MONOSPACE
                bold -> Typeface.DEFAULT_BOLD
                else -> Typeface.DEFAULT
            }
        }

    private fun drawHeader(canvas: Canvas, fill: Paint) {
        // Logo bubble + emoji
        val cy = HEADER_H / 2f
        fill.color = withAlpha(ACCENT, 0.2f)
        canvas.drawCircle((PAD + 42).toFloat(), cy, 42f, fill)
        val emoji = textPaint(WHITE, 42f, false).apply { textAlign = Paint.Align.CENTER }
        canvas.drawText("\uD83E\uDD8D", (PAD + 42).toFloat(), cy + 15f, emoji)
        // Wordmark
        canvas.drawText("ApesTogether", (PAD + 108).toFloat(), cy + 15f, textPaint(WHITE, 42f, true))
        // Domain (right)
        canvas.drawText(
            "apestogether.ai",
            (W - PAD).toFloat(), cy + 12f,
            textPaint(MUTED, 33f, false).apply { textAlign = Paint.Align.RIGHT },
        )
    }

    private fun drawContent(canvas: Canvas, fill: Paint, data: ShareCardData, hasChart: Boolean) {
        val top = (HEADER_H + PAD).toFloat()

        // Avatar bubble + initial
        val avatarCx = (PAD + 72).toFloat()
        val avatarCy = top + 72
        fill.color = withAlpha(ACCENT, 0.15f)
        canvas.drawCircle(avatarCx, avatarCy, 72f, fill)
        val initial = data.username.take(1).uppercase()
        canvas.drawText(
            initial, avatarCx, avatarCy + 22f,
            textPaint(ACCENT, 60f, true).apply { textAlign = Paint.Align.CENTER },
        )

        // Username + stats
        val textX = (PAD + 168).toFloat()
        canvas.drawText(data.username, textX, top + 56f, textPaint(WHITE, 54f, true))
        val stats = buildString {
            append("${data.holdingsCount} stocks")
            if (data.subscriberCount > 0) append("  ·  ${data.subscriberCount} subscribers")
        }
        canvas.drawText(stats, textX, top + 110f, textPaint(MUTED, 33f, false))

        // Return block (centered)
        val returnTop = top + 144 + 48
        val returnColor = if (data.portfolioReturn >= 0) GREEN else RED
        val returnText = signed(data.portfolioReturn)
        canvas.drawText(
            returnText, W / 2f, returnTop + 120f,
            textPaint(returnColor, 126f, true).apply { textAlign = Paint.Align.CENTER },
        )
        val beating = data.portfolioReturn > data.sp500Return
        val sub = if (beating) {
            "${periodLabel(data.period)}   ·   Beating S&P 500 (${signed(data.sp500Return)})"
        } else {
            "${periodLabel(data.period)}   ·   S&P 500: ${signed(data.sp500Return)}"
        }
        val subColor = if (beating) ACCENT else MUTED
        canvas.drawText(
            sub, W / 2f, returnTop + 180f,
            textPaint(subColor, 36f, false).apply { textAlign = Paint.Align.CENTER },
        )

        // Mini chart
        if (hasChart) {
            val chartTop = returnTop + 224
            drawChart(
                canvas,
                left = PAD.toFloat(),
                top = chartTop.toFloat(),
                right = (W - PAD).toFloat(),
                bottom = (chartTop + 240).toFloat(),
                values = data.chartValues,
                positive = data.portfolioReturn >= 0,
            )
        }
    }

    private fun drawChart(
        canvas: Canvas,
        left: Float, top: Float, right: Float, bottom: Float,
        values: List<Double>, positive: Boolean,
    ) {
        val color = if (positive) GREEN else RED
        val min = values.min()
        val max = values.max()
        val span = (max - min).let { if (abs(it) < 1e-9) 1.0 else it }
        val n = values.size
        val dx = (right - left) / (n - 1)

        fun yFor(v: Double): Float = (bottom - ((v - min) / span).toFloat() * (bottom - top))

        val line = Path()
        values.forEachIndexed { i, v ->
            val x = left + dx * i
            val y = yFor(v)
            if (i == 0) line.moveTo(x, y) else line.lineTo(x, y)
        }

        // Area fill (gradient under the line)
        val area = Path(line).apply {
            lineTo(right, bottom)
            lineTo(left, bottom)
            close()
        }
        val areaPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            shader = LinearGradient(
                0f, top, 0f, bottom,
                withAlpha(color, 0.3f), withAlpha(color, 0f),
                Shader.TileMode.CLAMP,
            )
        }
        canvas.drawPath(area, areaPaint)

        // Line on top
        val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 6f
            strokeCap = Paint.Cap.ROUND
            strokeJoin = Paint.Join.ROUND
            this.color = color
        }
        canvas.drawPath(line, linePaint)
    }

    private fun drawFooter(canvas: Canvas, fill: Paint, data: ShareCardData, h: Int) {
        val top = (h - FOOTER_H).toFloat()
        canvas.drawText("Follow my trades", PAD.toFloat(), top + 60f, textPaint(WHITE, 39f, true))
        canvas.drawText(
            "Get real-time alerts when I buy or sell",
            PAD.toFloat(), top + 108f, textPaint(MUTED, 30f, false),
        )

        // URL pill (right-aligned)
        val url = "apestogether.ai/p/${data.slug}"
        val urlPaint = textPaint(ACCENT, 30f, false, mono = true).apply { textAlign = Paint.Align.RIGHT }
        val textW = urlPaint.measureText(url)
        val pillRight = (W - PAD).toFloat()
        val pillLeft = pillRight - textW - 36f
        val pillCy = top + FOOTER_H / 2f
        fill.color = withAlpha(ACCENT, 0.1f)
        canvas.drawRoundRect(
            RectF(pillLeft, pillCy - 33f, pillRight + 18f, pillCy + 33f),
            12f, 12f, fill,
        )
        canvas.drawText(url, pillRight, pillCy + 11f, urlPaint)
    }

    private fun signed(v: Double): String {
        val sign = if (v >= 0) "+" else ""
        return "$sign${"%.1f".format(v)}%"
    }

    private fun periodLabel(period: String): String = when (period) {
        "1D" -> "Today"
        "1W", "5D" -> "1 Week"
        "1M" -> "1 Month"
        "3M" -> "3 Months"
        "YTD" -> "Year to Date"
        "1Y" -> "1 Year"
        else -> period
    }

    private fun withAlpha(color: Int, alpha: Float): Int {
        val a = (alpha.coerceIn(0f, 1f) * 255).toInt()
        return (a shl 24) or (color and 0x00FFFFFF)
    }
}
