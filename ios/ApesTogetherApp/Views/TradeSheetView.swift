import SwiftUI

struct TradeSheetView: View {
    let ticker: String
    let tradeType: TradeType
    let currentQuantity: Double
    let onComplete: () -> Void
    
    @Environment(\.dismiss) private var dismiss
    @State private var quantity: String = ""
    @State private var price: Double = 0
    @State private var isLoadingPrice = true
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var showSuccess = false
    
    enum TradeType: String {
        case buy = "buy"
        case sell = "sell"
        
        var color: Color {
            switch self {
            case .buy: return .gains
            case .sell: return .losses
            }
        }
        
        var title: String {
            switch self {
            case .buy: return "Buy"
            case .sell: return "Sell"
            }
        }
        
        var icon: String {
            switch self {
            case .buy: return "arrow.down.left"
            case .sell: return "arrow.up.right"
            }
        }
    }
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                VStack(spacing: 24) {
                    // Header
                    VStack(spacing: 8) {
                        ZStack {
                            Circle()
                                .fill(tradeType.color.opacity(0.15))
                                .frame(width: 56, height: 56)
                            Image(systemName: tradeType.icon)
                                .font(.system(size: 22, weight: .bold))
                                .foregroundColor(tradeType.color)
                        }
                        
                        Text("\(tradeType.title) \(ticker)")
                            .font(.title2.bold())
                            .foregroundColor(.textPrimary)
                        
                        if tradeType == .sell {
                            Text("\(Int(currentQuantity)) shares available")
                                .font(.caption)
                                .foregroundColor(.textMuted)
                        }
                    }
                    .padding(.top, 8)
                    
                    // Input fields
                    VStack(spacing: 16) {
                        // Current price (auto-fetched)
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Market Price")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.textMuted)
                            
                            HStack {
                                if isLoadingPrice {
                                    ProgressView()
                                        .tint(.primaryAccent)
                                        .scaleEffect(0.8)
                                    Text("Fetching price...")
                                        .font(.system(size: 16, weight: .medium))
                                        .foregroundColor(.textMuted)
                                } else if price > 0 {
                                    Text("$\(String(format: "%.2f", price))")
                                        .font(.system(size: 24, weight: .bold, design: .rounded))
                                        .foregroundColor(.primaryAccent)
                                } else {
                                    Text("Price unavailable")
                                        .font(.system(size: 16, weight: .medium))
                                        .foregroundColor(.losses)
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 14)
                            .background(Color.cardBackground)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(price > 0 ? Color.primaryAccent.opacity(0.3) : Color.cardBorder, lineWidth: 1)
                            )
                        }
                        
                        // Quantity
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Shares")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.textMuted)
                            
                            TextField("0", text: $quantity)
                                .keyboardType(.decimalPad)
                                .font(.system(size: 24, weight: .bold, design: .rounded))
                                .foregroundColor(.textPrimary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 14)
                                .background(Color.cardBackground)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.cardBorder, lineWidth: 1)
                                )
                        }
                        
                        // Estimated total
                        if let qty = Double(quantity), qty > 0, price > 0 {
                            HStack {
                                Text("Estimated total")
                                    .font(.subheadline)
                                    .foregroundColor(.textSecondary)
                                Spacer()
                                Text("$\(String(format: "%.2f", qty * price))")
                                    .font(.subheadline.bold())
                                    .foregroundColor(.textPrimary)
                            }
                            .padding(.horizontal, 4)
                        }
                    }
                    .padding(.horizontal, 20)
                    
                    if let error = errorMessage {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.losses)
                            .padding(.horizontal, 20)
                    }
                    
                    Spacer()
                    
                    // Quick quantity buttons (for sell)
                    if tradeType == .sell && currentQuantity > 0 {
                        HStack(spacing: 10) {
                            ForEach(["25%", "50%", "75%", "All"], id: \.self) { label in
                                Button {
                                    let pct: Double
                                    switch label {
                                    case "25%": pct = 0.25
                                    case "50%": pct = 0.50
                                    case "75%": pct = 0.75
                                    default: pct = 1.0
                                    }
                                    let qty = floor(currentQuantity * pct)
                                    quantity = qty == floor(qty) ? "\(Int(qty))" : "\(qty)"
                                } label: {
                                    Text(label)
                                        .font(.caption.weight(.semibold))
                                        .foregroundColor(.textSecondary)
                                        .padding(.horizontal, 14)
                                        .padding(.vertical, 8)
                                        .background(Color.cardBackground)
                                        .cornerRadius(8)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 8)
                                                .stroke(Color.cardBorder, lineWidth: 0.5)
                                        )
                                }
                            }
                        }
                        .padding(.horizontal, 20)
                    }
                    
                    // Submit button
                    Button {
                        submitTrade()
                    } label: {
                        HStack(spacing: 8) {
                            if isSubmitting {
                                ProgressView()
                                    .tint(.white)
                                    .scaleEffect(0.8)
                            }
                            Text(showSuccess ? "Done!" : "\(tradeType.title) \(ticker)")
                                .fontWeight(.bold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(
                            showSuccess ? Color.gains : tradeType.color
                        )
                        .foregroundColor(.white)
                        .cornerRadius(14)
                    }
                    .disabled(isSubmitting || showSuccess)
                    .padding(.horizontal, 20)
                    
                    // Email trading CTA — opens Mail.app with pre-filled trade
                    Button {
                        openEmailTrade()
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "envelope.fill")
                                .font(.system(size: 11))
                            Text("Submit trades via email")
                                .font(.caption)
                                .underline()
                        }
                        .foregroundColor(.primaryAccent)
                    }
                    .padding(.bottom, 16)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textMuted)
                            .font(.title3)
                    }
                }
            }
            .onAppear {
                fetchPrice()
            }
        }
    }
    
    private func openEmailTrade() {
        let qty = quantity.isEmpty ? "___" : quantity
        let subject = "\(tradeType.title.uppercased()) \(qty) \(ticker)"
        let body = """
        \(tradeType.title.uppercased()) \(qty) \(ticker)
        
        Tip: Put one trade per line to submit multiple trades at once.
        Example:
        BUY 10 AAPL
        SELL 5 TSLA
        BUY 20 MSFT
        """
        
        let to = "trade@trade.apestogether.ai"
        var components = URLComponents()
        components.scheme = "mailto"
        components.path = to
        components.queryItems = [
            URLQueryItem(name: "subject", value: subject),
            URLQueryItem(name: "body", value: body),
        ]
        
        if let url = components.url {
            UIApplication.shared.open(url)
        }
    }
    
    private func fetchPrice() {
        isLoadingPrice = true
        Task {
            do {
                let response = try await APIService.shared.getStockPrice(ticker: ticker)
                price = response.price
            } catch {
                price = 0
            }
            isLoadingPrice = false
        }
    }
    
    private func submitTrade() {
        guard let qty = Double(quantity), qty > 0 else {
            errorMessage = "Enter a valid quantity"
            return
        }
        guard price > 0 else {
            errorMessage = "Price not available. Please try again."
            return
        }
        
        if tradeType == .sell && qty > currentQuantity {
            errorMessage = "You only have \(Int(currentQuantity)) shares"
            return
        }
        
        errorMessage = nil
        isSubmitting = true
        
        Task {
            do {
                let response = try await APIService.shared.executeTrade(
                    ticker: ticker,
                    quantity: qty,
                    price: price,
                    type: tradeType.rawValue
                )
                
                if response.success {
                    showSuccess = true
                    try? await Task.sleep(nanoseconds: 800_000_000)
                    dismiss()
                    onComplete()
                } else {
                    errorMessage = response.error ?? "Trade failed"
                }
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
