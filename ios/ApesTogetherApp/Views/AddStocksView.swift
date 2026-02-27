import SwiftUI

struct StockEntry: Identifiable {
    let id = UUID()
    var ticker: String = ""
    var quantity: String = ""
}

struct AddStocksView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @Environment(\.dismiss) var dismiss
    
    let onComplete: () -> Void
    let showSkip: Bool
    let headline: String
    let subheadline: String
    
    @State private var entries: [StockEntry] = [StockEntry()]
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var successCount = 0
    @State private var showSuccess = false
    
    init(
        headline: String = "Add Your Stocks",
        subheadline: String = "Share your trades and earn from every subscriber",
        showSkip: Bool = true,
        onComplete: @escaping () -> Void
    ) {
        self.headline = headline
        self.subheadline = subheadline
        self.showSkip = showSkip
        self.onComplete = onComplete
    }
    
    var body: some View {
        ZStack {
            Color.appBackground.ignoresSafeArea()
            
            VStack(spacing: 0) {
                // Header
                VStack(spacing: 8) {
                    Text(headline)
                        .font(.title2.bold())
                        .foregroundColor(.textPrimary)
                    
                    Text(subheadline)
                        .font(.subheadline)
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.top, 24)
                .padding(.horizontal, 24)
                
                // Stock entries
                ScrollView {
                    VStack(spacing: 12) {
                        ForEach($entries) { $entry in
                            StockEntryRow(entry: $entry, onDelete: entries.count > 1 ? {
                                withAnimation {
                                    entries.removeAll { $0.id == entry.id }
                                }
                            } : nil)
                        }
                        
                        // Add more button
                        Button {
                            withAnimation {
                                entries.append(StockEntry())
                            }
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "plus.circle.fill")
                                    .font(.title3)
                                Text("Add another stock")
                                    .font(.subheadline.weight(.medium))
                            }
                            .foregroundColor(.primaryAccent)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.primaryAccent.opacity(0.3), style: StrokeStyle(lineWidth: 1, dash: [6]))
                            )
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 24)
                    .padding(.bottom, 16)
                }
                
                if let error = errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.losses)
                        .padding(.horizontal, 20)
                        .padding(.bottom, 8)
                }
                
                // Bottom buttons
                VStack(spacing: 12) {
                    Button {
                        Task {
                            await submitStocks()
                        }
                    } label: {
                        if isSubmitting {
                            ProgressView()
                                .tint(.appBackground)
                        } else {
                            Text("Save Stocks")
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle(isDisabled: !hasValidEntries || isSubmitting))
                    .disabled(!hasValidEntries || isSubmitting)
                    
                    if showSkip {
                        Button {
                            onComplete()
                        } label: {
                            Text("I'll do this later")
                                .font(.subheadline)
                                .foregroundColor(.textSecondary)
                        }
                    }
                }
                .padding(.horizontal, 40)
                .padding(.bottom, 40)
            }
        }
        .alert("Stocks Added!", isPresented: $showSuccess) {
            Button("Continue") {
                onComplete()
            }
        } message: {
            Text("\(successCount) stock\(successCount == 1 ? "" : "s") added to your portfolio.")
        }
    }
    
    private var hasValidEntries: Bool {
        entries.contains { !$0.ticker.trimmingCharacters(in: .whitespaces).isEmpty && !$0.quantity.trimmingCharacters(in: .whitespaces).isEmpty }
    }
    
    private func submitStocks() async {
        isSubmitting = true
        errorMessage = nil
        
        let validEntries = entries.filter {
            !$0.ticker.trimmingCharacters(in: .whitespaces).isEmpty &&
            !$0.quantity.trimmingCharacters(in: .whitespaces).isEmpty
        }
        
        guard !validEntries.isEmpty else {
            errorMessage = "Please enter at least one stock"
            isSubmitting = false
            return
        }
        
        let stocks = validEntries.compactMap { entry -> [String: Any]? in
            guard let qty = Double(entry.quantity.trimmingCharacters(in: .whitespaces)), qty > 0 else {
                return nil
            }
            return [
                "ticker": entry.ticker.trimmingCharacters(in: .whitespaces).uppercased(),
                "quantity": qty
            ]
        }
        
        guard !stocks.isEmpty else {
            errorMessage = "Please enter valid quantities"
            isSubmitting = false
            return
        }
        
        do {
            let response = try await APIService.shared.addStocks(stocks: stocks)
            successCount = response.addedCount
            showSuccess = true
        } catch {
            errorMessage = error.localizedDescription
        }
        
        isSubmitting = false
    }
}

struct StockEntryRow: View {
    @Binding var entry: StockEntry
    var onDelete: (() -> Void)?
    
    var body: some View {
        HStack(spacing: 10) {
            // Ticker field
            TextField("AAPL", text: $entry.ticker)
                .textCase(.uppercase)
                .font(.headline)
                .foregroundColor(.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 14)
                .background(Color.cardBackground)
                .cornerRadius(10)
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.cardBorder, lineWidth: 1)
                )
                .frame(maxWidth: .infinity)
            
            // Quantity field
            TextField("Shares", text: $entry.quantity)
                .keyboardType(.decimalPad)
                .font(.headline)
                .foregroundColor(.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 14)
                .background(Color.cardBackground)
                .cornerRadius(10)
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.cardBorder, lineWidth: 1)
                )
                .frame(width: 100)
            
            // Delete button
            if let onDelete = onDelete {
                Button(action: onDelete) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title3)
                        .foregroundColor(.textMuted)
                }
            }
        }
    }
}

struct AddStocksView_Previews: PreviewProvider {
    static var previews: some View {
        AddStocksView(onComplete: {})
            .environmentObject(AuthenticationManager())
    }
}
