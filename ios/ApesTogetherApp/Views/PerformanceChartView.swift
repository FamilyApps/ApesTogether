import SwiftUI
import Charts

struct PerformanceChartView: View {
    let chartData: [ChartPoint]
    let portfolioReturn: Double
    let sp500Return: Double
    let selectedPeriod: String
    let onPeriodChange: (String) -> Void
    var portfolioLabel: String = "Your Portfolio"
    
    private let periods = ["1D", "1W", "1M", "3M", "YTD", "1Y"]
    
    private var xAxisLabelCount: Int {
        switch selectedPeriod {
        case "1D": return 4
        case "1W": return 5
        case "1M": return 4
        case "3M": return 5
        case "YTD": return 5
        case "1Y": return 5
        default: return 4
        }
    }
    
    private var portfolioColor: Color {
        portfolioReturn >= 0 ? .gains : .losses
    }
    
    private var xAxisTickValues: [Int] {
        let count = chartData.count
        guard count > 1 else { return count == 1 ? [0] : [] }
        let desiredLabels = xAxisLabelCount
        let step = max(1, count / desiredLabels)
        var ticks: [Int] = []
        var i = 0
        while i < count {
            ticks.append(i)
            i += step
        }
        // Always include the last point
        if let last = ticks.last, last != count - 1 {
            ticks.append(count - 1)
        }
        return ticks
    }
    
    private func formatYAxisLabel(_ val: Double) -> String {
        if abs(val) >= 100 {
            return String(format: "%.0f%%", val)
        } else if abs(val) >= 10 {
            return String(format: "%.0f%%", val)
        } else {
            return String(format: "%.1f%%", val)
        }
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Return summary header
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(portfolioLabel)
                        .font(.caption)
                        .foregroundColor(.textMuted)
                    Text(String(format: "%+.2f%%", portfolioReturn))
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                        .foregroundColor(portfolioColor)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 4) {
                    Text("S&P 500")
                        .font(.caption)
                        .foregroundColor(.textMuted)
                    Text(String(format: "%+.2f%%", sp500Return))
                        .font(.system(size: 18, weight: .semibold, design: .rounded))
                        .foregroundColor(sp500Return >= 0 ? .gains.opacity(0.6) : .losses.opacity(0.6))
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 16)
            .padding(.bottom, 8)
            
            // Chart
            if chartData.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.system(size: 36))
                        .foregroundColor(.textMuted)
                    Text("Chart data will appear once\nyour portfolio has history")
                        .font(.caption)
                        .foregroundColor(.textMuted)
                        .multilineTextAlignment(.center)
                }
                .frame(height: 200)
                .frame(maxWidth: .infinity)
            } else {
                Chart {
                    // Portfolio line — use index for X to avoid overlapping string labels
                    ForEach(Array(chartData.filter { $0.portfolio != nil }.enumerated()), id: \.offset) { idx, point in
                        LineMark(
                            x: .value("Index", point.index ?? idx),
                            y: .value("Return", point.portfolio ?? 0),
                            series: .value("Series", "Portfolio")
                        )
                        .foregroundStyle(portfolioColor)
                        .lineStyle(StrokeStyle(lineWidth: 2.5))
                        .interpolationMethod(.linear)
                    }
                    
                    // S&P 500 line
                    ForEach(Array(chartData.filter { $0.sp500 != nil }.enumerated()), id: \.offset) { idx, point in
                        LineMark(
                            x: .value("Index", point.index ?? idx),
                            y: .value("Return", point.sp500 ?? 0),
                            series: .value("Series", "S&P 500")
                        )
                        .foregroundStyle(Color.textMuted.opacity(0.5))
                        .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [5, 3]))
                        .interpolationMethod(.linear)
                    }
                    
                    // Zero line
                    RuleMark(y: .value("Zero", 0))
                        .foregroundStyle(Color.textMuted.opacity(0.2))
                        .lineStyle(StrokeStyle(lineWidth: 0.5))
                }
                .chartXAxis {
                    AxisMarks(values: xAxisTickValues) { value in
                        if let idx = value.as(Int.self), idx < chartData.count {
                            AxisValueLabel {
                                Text(chartData[idx].date)
                                    .font(.system(size: 9))
                                    .foregroundColor(.textMuted)
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) { value in
                        AxisGridLine(stroke: StrokeStyle(lineWidth: 0.3))
                            .foregroundStyle(Color.cardBorder.opacity(0.5))
                        AxisValueLabel {
                            if let val = value.as(Double.self) {
                                Text(formatYAxisLabel(val))
                                    .font(.system(size: 9))
                                    .foregroundColor(.textMuted)
                            }
                        }
                    }
                }
                .chartLegend(.hidden)
                .frame(height: 200)
                .padding(.horizontal, 8)
            }
            
            // Legend
            HStack(spacing: 16) {
                HStack(spacing: 4) {
                    Circle().fill(portfolioColor).frame(width: 6, height: 6)
                    Text("Portfolio").font(.system(size: 10)).foregroundColor(.textMuted)
                }
                HStack(spacing: 4) {
                    RoundedRectangle(cornerRadius: 1)
                        .stroke(Color.textMuted.opacity(0.5), style: StrokeStyle(lineWidth: 1.5, dash: [3, 2]))
                        .frame(width: 14, height: 1)
                    Text("S&P 500").font(.system(size: 10)).foregroundColor(.textMuted)
                }
            }
            .padding(.top, 8)
            
            // Period selector
            HStack(spacing: 0) {
                ForEach(periods, id: \.self) { period in
                    Button {
                        onPeriodChange(period)
                    } label: {
                        Text(period)
                            .font(.system(size: 12, weight: .bold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .background(
                                selectedPeriod == period
                                    ? portfolioColor.opacity(0.15)
                                    : Color.clear
                            )
                            .foregroundColor(
                                selectedPeriod == period
                                    ? portfolioColor
                                    : .textMuted
                            )
                            .cornerRadius(6)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 12)
            .padding(.bottom, 16)
        }
        .background(Color.cardBackground)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.cardBorder, lineWidth: 0.5)
        )
    }
}

// MARK: - Sparkline (for Leaderboard rows)

struct SparklineView: View {
    let dataPoints: [Double?]
    var sp500Points: [Double?] = []
    let isPositive: Bool
    
    private var validPortfolioPoints: [(index: Int, value: Double)] {
        dataPoints.enumerated().compactMap { index, value in
            value.map { (index: index, value: $0) }
        }
    }
    
    private var validSP500Points: [(index: Int, value: Double)] {
        sp500Points.enumerated().compactMap { index, value in
            value.map { (index: index, value: $0) }
        }
    }
    
    var body: some View {
        if validPortfolioPoints.count >= 2 {
            Chart {
                ForEach(validPortfolioPoints, id: \.index) { point in
                    LineMark(
                        x: .value("Index", point.index),
                        y: .value("Value", point.value),
                        series: .value("S", "Portfolio")
                    )
                    .foregroundStyle(isPositive ? Color.gains : Color.losses)
                    .lineStyle(StrokeStyle(lineWidth: 1.5))
                    .interpolationMethod(.linear)
                }
                if validSP500Points.count >= 2 {
                    ForEach(validSP500Points, id: \.index) { point in
                        LineMark(
                            x: .value("Index", point.index),
                            y: .value("Value", point.value),
                            series: .value("S", "SP500")
                        )
                        .foregroundStyle(Color.textMuted.opacity(0.4))
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 2]))
                        .interpolationMethod(.linear)
                    }
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis(.hidden)
            .chartLegend(.hidden)
        } else {
            Rectangle()
                .fill(Color.cardBorder.opacity(0.3))
        }
    }
}
