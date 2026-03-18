import SwiftUI
import Charts

// MARK: - Share Card (rendered to image for social sharing)

struct PortfolioShareCardView: View {
    let username: String
    let portfolioReturn: Double
    let sp500Return: Double
    let chartData: [ChartPoint]
    let holdingsCount: Int
    let subscriberCount: Int
    let period: String
    let slug: String
    
    private var isBeatingMarket: Bool {
        portfolioReturn > sp500Return
    }
    
    private var returnFormatted: String {
        let sign = portfolioReturn >= 0 ? "+" : ""
        return "\(sign)\(String(format: "%.1f", portfolioReturn))%"
    }
    
    private var sp500Formatted: String {
        let sign = sp500Return >= 0 ? "+" : ""
        return "\(sign)\(String(format: "%.1f", sp500Return))%"
    }
    
    private var periodLabel: String {
        switch period {
        case "1D": return "Today"
        case "5D": return "5 Days"
        case "7D": return "7 Days"
        case "1M": return "1 Month"
        case "3M": return "3 Months"
        case "YTD": return "Year to Date"
        case "1Y": return "1 Year"
        default: return period
        }
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Header bar
            HStack {
                HStack(spacing: 8) {
                    // Logo placeholder - circle with gorilla emoji
                    ZStack {
                        Circle()
                            .fill(Color(hex: "00D9A5").opacity(0.2))
                            .frame(width: 28, height: 28)
                        Text("\u{1F98D}")
                            .font(.system(size: 14))
                    }
                    Text("Apes Together")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(.white)
                }
                Spacer()
                Text("apestogether.ai")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Color(hex: "9CA3AF"))
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(Color(hex: "0D1210"))
            
            // Main content
            VStack(spacing: 16) {
                // User info
                HStack(spacing: 12) {
                    ZStack {
                        Circle()
                            .fill(Color(hex: "00D9A5").opacity(0.15))
                            .frame(width: 48, height: 48)
                        Text(String(username.prefix(1)).uppercased())
                            .font(.system(size: 20, weight: .bold))
                            .foregroundColor(Color(hex: "00D9A5"))
                    }
                    
                    VStack(alignment: .leading, spacing: 2) {
                        Text(username)
                            .font(.system(size: 18, weight: .bold))
                            .foregroundColor(.white)
                        
                        HStack(spacing: 12) {
                            HStack(spacing: 3) {
                                Image(systemName: "chart.bar.fill")
                                    .font(.system(size: 9))
                                Text("\(holdingsCount) stocks")
                                    .font(.system(size: 11))
                            }
                            if subscriberCount > 0 {
                                HStack(spacing: 3) {
                                    Image(systemName: "person.2.fill")
                                        .font(.system(size: 9))
                                    Text("\(subscriberCount) subscribers")
                                        .font(.system(size: 11))
                                }
                            }
                        }
                        .foregroundColor(Color(hex: "9CA3AF"))
                    }
                    
                    Spacer()
                }
                
                // Return display
                VStack(spacing: 6) {
                    Text(returnFormatted)
                        .font(.system(size: 42, weight: .bold, design: .rounded))
                        .foregroundColor(portfolioReturn >= 0 ? Color(hex: "22C55E") : Color(hex: "EF4444"))
                    
                    HStack(spacing: 6) {
                        Text(periodLabel)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Color(hex: "9CA3AF"))
                        
                        if isBeatingMarket {
                            Text("Beating S&P 500 (\(sp500Formatted))")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(Color(hex: "00D9A5"))
                        } else {
                            Text("S&P 500: \(sp500Formatted)")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "9CA3AF"))
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
                
                // Mini chart
                if !chartData.isEmpty {
                    ShareCardChartView(
                        chartData: chartData,
                        portfolioReturn: portfolioReturn
                    )
                    .frame(height: 80)
                    .padding(.horizontal, 4)
                }
            }
            .padding(20)
            .background(Color(hex: "141A17"))
            
            // Footer CTA
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Follow my trades")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white)
                    Text("Get real-time alerts when I buy or sell")
                        .font(.system(size: 10))
                        .foregroundColor(Color(hex: "9CA3AF"))
                }
                
                Spacer()
                
                Text("apestogether.ai/p/\(slug)")
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundColor(Color(hex: "00D9A5"))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(Color(hex: "00D9A5").opacity(0.1))
                    )
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(Color(hex: "0A0F0D"))
        }
        .frame(width: 380)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color(hex: "1F2A24"), lineWidth: 1)
        )
    }
}

// MARK: - Mini Chart for Share Card

struct ShareCardChartView: View {
    let chartData: [ChartPoint]
    let portfolioReturn: Double
    
    private var lineColor: Color {
        portfolioReturn >= 0 ? Color(hex: "22C55E") : Color(hex: "EF4444")
    }
    
    var body: some View {
        if #available(iOS 16.0, *) {
            Chart {
                ForEach(Array(chartData.enumerated()), id: \.element.id) { index, point in
                    if let value = point.portfolio {
                        LineMark(
                            x: .value("Time", index),
                            y: .value("Return", value)
                        )
                        .foregroundStyle(lineColor)
                        .lineStyle(StrokeStyle(lineWidth: 2))
                        
                        AreaMark(
                            x: .value("Time", index),
                            y: .value("Return", value)
                        )
                        .foregroundStyle(
                            LinearGradient(
                                colors: [lineColor.opacity(0.3), lineColor.opacity(0.0)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                    }
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis(.hidden)
            .chartLegend(.hidden)
        }
    }
}

// MARK: - Trade Share Card

struct TradeShareCardView: View {
    let username: String
    let ticker: String
    let tradeType: String // "BUY" or "SELL"
    let quantity: Int
    let price: Double
    let slug: String
    
    private var isBuy: Bool { tradeType.uppercased() == "BUY" }
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    ZStack {
                        Circle()
                            .fill(Color(hex: "00D9A5").opacity(0.2))
                            .frame(width: 28, height: 28)
                        Text("\u{1F98D}")
                            .font(.system(size: 14))
                    }
                    Text("Apes Together")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(.white)
                }
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(Color(hex: "0D1210"))
            
            // Trade info
            VStack(spacing: 16) {
                // Trade action
                HStack(spacing: 8) {
                    ZStack {
                        Circle()
                            .fill((isBuy ? Color(hex: "22C55E") : Color(hex: "EF4444")).opacity(0.15))
                            .frame(width: 40, height: 40)
                        Image(systemName: isBuy ? "arrow.down.left" : "arrow.up.right")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(isBuy ? Color(hex: "22C55E") : Color(hex: "EF4444"))
                    }
                    
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(username) just \(isBuy ? "bought" : "sold")")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(Color(hex: "9CA3AF"))
                        
                        HStack(spacing: 6) {
                            Text(ticker)
                                .font(.system(size: 24, weight: .bold))
                                .foregroundColor(.white)
                        }
                    }
                    
                    Spacer()
                }
                
                // Details
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Quantity")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(Color(hex: "6B7280"))
                        Text("\(quantity) shares")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                    }
                    
                    Spacer()
                    
                    VStack(alignment: .trailing, spacing: 4) {
                        Text("Price")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(Color(hex: "6B7280"))
                        Text("$\(String(format: "%.2f", price))")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                    }
                }
                .padding(14)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color(hex: "0A0F0D"))
                )
            }
            .padding(20)
            .background(Color(hex: "141A17"))
            
            // Footer
            HStack {
                Text("Get real-time trade alerts")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Color(hex: "9CA3AF"))
                Spacer()
                Text("apestogether.ai/p/\(slug)")
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundColor(Color(hex: "00D9A5"))
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Color(hex: "0A0F0D"))
        }
        .frame(width: 380)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color(hex: "1F2A24"), lineWidth: 1)
        )
    }
}

// MARK: - Share Card Generator

@MainActor
class ShareCardGenerator {
    
    static let shared = ShareCardGenerator()
    
    /// Generate a portfolio performance share card as UIImage
    @available(iOS 16.0, *)
    func generatePortfolioCard(
        username: String,
        portfolioReturn: Double,
        sp500Return: Double,
        chartData: [ChartPoint],
        holdingsCount: Int,
        subscriberCount: Int,
        period: String,
        slug: String
    ) -> UIImage? {
        let view = PortfolioShareCardView(
            username: username,
            portfolioReturn: portfolioReturn,
            sp500Return: sp500Return,
            chartData: chartData,
            holdingsCount: holdingsCount,
            subscriberCount: subscriberCount,
            period: period,
            slug: slug
        )
        
        let renderer = ImageRenderer(content: view)
        renderer.scale = 3.0 // High resolution
        return renderer.uiImage
    }
    
    /// Generate a trade alert share card as UIImage
    @available(iOS 16.0, *)
    func generateTradeCard(
        username: String,
        ticker: String,
        tradeType: String,
        quantity: Int,
        price: Double,
        slug: String
    ) -> UIImage? {
        let view = TradeShareCardView(
            username: username,
            ticker: ticker,
            tradeType: tradeType,
            quantity: quantity,
            price: price,
            slug: slug
        )
        
        let renderer = ImageRenderer(content: view)
        renderer.scale = 3.0
        return renderer.uiImage
    }
}

// MARK: - Previews

struct PortfolioShareCardView_Previews: PreviewProvider {
    static var previews: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 20) {
                PortfolioShareCardView(
                    username: "clever-fox",
                    portfolioReturn: 18.5,
                    sp500Return: 12.3,
                    chartData: [],
                    holdingsCount: 8,
                    subscriberCount: 14,
                    period: "7D",
                    slug: "abc123"
                )
                
                TradeShareCardView(
                    username: "clever-fox",
                    ticker: "TSLA",
                    tradeType: "BUY",
                    quantity: 10,
                    price: 245.50,
                    slug: "abc123"
                )
            }
            .padding()
        }
    }
}
