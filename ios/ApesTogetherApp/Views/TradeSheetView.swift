import SwiftUI

struct TradeSheetView: View {
    let ticker: String
    let tradeType: TradeType
    let currentQuantity: Double
    let onComplete: () -> Void
    
    @Environment(\.dismiss) private var dismiss
    @State private var quantity: String = ""
    @State private var price: String = ""
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
                        
                        // Price
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Price per share")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.textMuted)
                            
                            HStack {
                                Text("$")
                                    .font(.system(size: 24, weight: .bold, design: .rounded))
                                    .foregroundColor(.textMuted)
                                TextField("0.00", text: $price)
                                    .keyboardType(.decimalPad)
                                    .font(.system(size: 24, weight: .bold, design: .rounded))
                                    .foregroundColor(.textPrimary)
                            }
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
                        if let qty = Double(quantity), let prc = Double(price), qty > 0, prc > 0 {
                            HStack {
                                Text("Estimated total")
                                    .font(.subheadline)
                                    .foregroundColor(.textSecondary)
                                Spacer()
                                Text("$\(String(format: "%.2f", qty * prc))")
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
        }
    }
    
    private func submitTrade() {
        guard let qty = Double(quantity), qty > 0 else {
            errorMessage = "Enter a valid quantity"
            return
        }
        guard let prc = Double(price), prc > 0 else {
            errorMessage = "Enter a valid price"
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
                    price: prc,
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
