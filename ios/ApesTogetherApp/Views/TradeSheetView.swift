import SwiftUI
import StoreKit

struct TradeSheetView: View {
    let ticker: String
    let tradeType: TradeType
    let currentQuantity: Double
    // General-buy mode (portfolio Buy button): ticker starts empty and is
    // typed by the user, with a debounced price re-fetch on every change.
    // Holding-row buy/sell paths pass a fixed ticker and leave this false.
    var allowTickerEntry: Bool = false
    let onComplete: () -> Void
    
    @Environment(\.dismiss) private var dismiss
    @State private var quantity: String = ""
    @State private var tickerInput: String = ""
    @State private var price: Double = 0
    @State private var isLoadingPrice = true
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var showSuccess = false
    @State private var isPending = false
    @State private var priceFetchTask: Task<Void, Never>?
    @FocusState private var tickerFocused: Bool
    
    private var effectiveTicker: String {
        allowTickerEntry
            ? tickerInput.trimmingCharacters(in: .whitespaces).uppercased()
            : ticker
    }
    
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
            case .buy: return "plus"
            case .sell: return "minus"
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
                        
                        Text(effectiveTicker.isEmpty ? tradeType.title : "\(tradeType.title) \(effectiveTicker)")
                            .font(.title2.bold())
                            .foregroundColor(.textPrimary)
                        
                        if tradeType == .sell {
                            Text("\(Int(currentQuantity)) shares available")
                                .font(.caption)
                                .foregroundColor(.textMuted)
                        }
                    }
                    .padding(.top, 24)
                    
                    // Input fields
                    VStack(spacing: 16) {
                        // Ticker — general-buy mode only.
                        if allowTickerEntry {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("Ticker")
                                    .font(.caption.weight(.semibold))
                                    .foregroundColor(.textMuted)
                                
                                TextField("", text: $tickerInput, prompt: Text("AAPL").foregroundColor(.textSecondary))
                                    .textInputAutocapitalization(.characters)
                                    .autocorrectionDisabled()
                                    .focused($tickerFocused)
                                    .font(.system(size: 24, weight: .bold, design: .rounded))
                                    .foregroundColor(.textPrimary)
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 14)
                                    .background(Color.inputBackground)
                                    .cornerRadius(12)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12)
                                            .stroke(Color.inputBorder, lineWidth: 1)
                                    )
                                    .onChange(of: tickerInput) { _, newValue in
                                        let cleaned = String(
                                            newValue.uppercased()
                                                .filter { $0.isLetter || $0.isNumber || $0 == "." }
                                                .prefix(10)
                                        )
                                        if cleaned != newValue { tickerInput = cleaned }
                                        errorMessage = nil
                                        schedulePriceFetch()
                                    }
                            }
                        }
                        
                        // Market price (auto-fetched, read-only). Plain
                        // label/value row — deliberately NOT field-styled so it
                        // doesn't look editable (Robinhood/Webull/Public
                        // convention; mirrors Android TradeSheet Option A).
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text("Market Price")
                                    .font(.subheadline)
                                    .foregroundColor(.textSecondary)
                                Spacer()
                                if isLoadingPrice {
                                    ProgressView()
                                        .tint(.primaryAccent)
                                        .scaleEffect(0.8)
                                    Text("Fetching\u{2026}")
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(.textMuted)
                                } else if price > 0 {
                                    Text("$\(grouped(price))")
                                        .font(.system(size: 18, weight: .bold, design: .rounded))
                                        .foregroundColor(.primaryAccent)
                                } else if effectiveTicker.isEmpty {
                                    Text("\u{2014}")
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(.textMuted)
                                } else {
                                    Text("Price unavailable")
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(.losses)
                                }
                            }
                            Text("Live price \u{2014} trades always execute at the current market price.")
                                .font(.system(size: 11))
                                .foregroundColor(.textMuted)
                        }
                        .padding(.horizontal, 4)
                        
                        // Quantity
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Quantity")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.textMuted)
                            
                            TextField("0", text: $quantity)
                                .keyboardType(.decimalPad)
                                .font(.system(size: 24, weight: .bold, design: .rounded))
                                .foregroundColor(.textPrimary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 14)
                                .background(Color.inputBackground)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.inputBorder, lineWidth: 1)
                                )
                        }
                        
                        // Estimated total
                        if let qty = Double(quantity), qty > 0, price > 0 {
                            HStack {
                                Text("Estimated total")
                                    .font(.subheadline)
                                    .foregroundColor(.textSecondary)
                                Spacer()
                                Text("$\(grouped(qty * price))")
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
                            Text(showSuccess ? (isPending ? "Queued for open" : "Done!") : (effectiveTicker.isEmpty ? tradeType.title : "\(tradeType.title) \(effectiveTicker)"))
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
                    .disabled(isSubmitting || showSuccess || effectiveTicker.isEmpty)
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
                if allowTickerEntry {
                    isLoadingPrice = false
                    // Delay so the sheet finishes presenting before requesting
                    // focus — otherwise the keyboard often fails to appear.
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
                        tickerFocused = true
                    }
                } else {
                    fetchPrice()
                }
            }
        }
    }
    
    private func openEmailTrade() {
        let qty = quantity.isEmpty ? "___" : quantity
        let symbol = effectiveTicker.isEmpty ? "____" : effectiveTicker
        let subject = "\(tradeType.title.uppercased()) \(qty) \(symbol)"
        let body = """
        \(tradeType.title.uppercased()) \(qty) \(symbol)
        
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
            await fetchPriceAsync(effectiveTicker)
        }
    }
    
    /// Debounced re-fetch as the user types a ticker (general-buy mode).
    private func schedulePriceFetch() {
        priceFetchTask?.cancel()
        let symbol = effectiveTicker
        guard !symbol.isEmpty else {
            price = 0
            isLoadingPrice = false
            return
        }
        isLoadingPrice = true
        priceFetchTask = Task {
            try? await Task.sleep(nanoseconds: 500_000_000)
            guard !Task.isCancelled else { return }
            await fetchPriceAsync(symbol)
        }
    }
    
    private func fetchPriceAsync(_ symbol: String) async {
        do {
            let response = try await APIService.shared.getStockPrice(ticker: symbol)
            // The user may have kept typing while the request was in flight —
            // only apply the result if it still matches the current ticker.
            guard symbol == effectiveTicker else { return }
            price = response.price
        } catch {
            guard symbol == effectiveTicker else { return }
            price = 0
        }
        isLoadingPrice = false
    }
    
    private func grouped(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.minimumFractionDigits = 2
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: value)) ?? String(format: "%.2f", value)
    }
    
    private func submitTrade() {
        guard !effectiveTicker.isEmpty else {
            errorMessage = "Enter a ticker"
            return
        }
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
                    ticker: effectiveTicker,
                    quantity: qty,
                    price: price,
                    type: tradeType.rawValue
                )
                
                if response.success {
                    isPending = (response.pending == true)
                    showSuccess = true
                    if !isPending {
                        Self.promptReviewIfEligible()
                    }
                    try? await Task.sleep(nanoseconds: isPending ? 1_200_000_000 : 800_000_000)
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
    
    // MARK: - App Store Review Prompt
    
    private static let tradeCountKey = "successfulTradeCount"
    
    private static func promptReviewIfEligible() {
        let count = UserDefaults.standard.integer(forKey: tradeCountKey) + 1
        UserDefaults.standard.set(count, forKey: tradeCountKey)
        
        // Prompt after 3rd successful trade (user is engaged, feeling accomplished)
        if count == 3 {
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                if let scene = UIApplication.shared.connectedScenes
                    .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene {
                    SKStoreReviewController.requestReview(in: scene)
                }
            }
        }
    }
}
