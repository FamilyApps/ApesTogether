import SwiftUI
import Charts

struct PerformanceChartView: View {
    let chartData: [ChartPoint]
    let portfolioReturn: Double
    let sp500Return: Double
    let selectedPeriod: String
    let onPeriodChange: (String) -> Void
    
    private let periods = ["1D", "5D", "7D", "1M", "3M", "YTD", "1Y"]
    
    private var xAxisLabelCount: Int {
        switch selectedPeriod {
        case "1D": return 4
        case "5D": return 5
        case "7D": return 4
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
                    Text("Your Portfolio")
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
                    ForEach(chartData) { point in
                        if let portfolio = point.portfolio {
                            LineMark(
                                x: .value("Date", point.date),
                                y: .value("Return", portfolio)
                            )
                            .foregroundStyle(portfolioColor)
                            .lineStyle(StrokeStyle(lineWidth: 2.5))
                            .interpolationMethod(.catmullRom)
                            .symbol(.circle)
                            .symbolSize(0)
                        }
                    }
                    
                    ForEach(chartData) { point in
                        if let sp500 = point.sp500 {
                            LineMark(
                                x: .value("Date", point.date),
                                y: .value("Return", sp500)
                            )
                            .foregroundStyle(Color.textMuted.opacity(0.5))
                            .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [5, 3]))
                            .interpolationMethod(.catmullRom)
                            .symbol(.circle)
                            .symbolSize(0)
                        }
                    }
                    
                    // Zero line
                    RuleMark(y: .value("Zero", 0))
                        .foregroundStyle(Color.textMuted.opacity(0.2))
                        .lineStyle(StrokeStyle(lineWidth: 0.5))
                }
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: xAxisLabelCount)) { value in
                        AxisValueLabel()
                            .foregroundStyle(Color.textMuted)
                            .font(.system(size: 9))
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
    let dataPoints: [Double]
    let isPositive: Bool
    
    var body: some View {
        if dataPoints.count >= 2 {
            Chart {
                ForEach(Array(dataPoints.enumerated()), id: \.offset) { index, value in
                    LineMark(
                        x: .value("Index", index),
                        y: .value("Value", value)
                    )
                    .foregroundStyle(isPositive ? Color.gains : Color.losses)
                    .interpolationMethod(.catmullRom)
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
