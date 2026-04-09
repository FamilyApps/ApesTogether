import SwiftUI

// MARK: - Tax Status Response Model

struct TaxStatusResponse: Codable {
    let taxInfoOnFile: Bool
    let status: String
    let message: String
    
    enum CodingKeys: String, CodingKey {
        case taxInfoOnFile = "tax_info_on_file"
        case status
        case message
    }
}

// MARK: - Tax Info Status View

struct TaxInfoView: View {
    @Environment(\.dismiss) var dismiss
    @StateObject private var viewModel = TaxInfoViewModel()
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                if viewModel.isLoading {
                    ProgressView()
                        .tint(.primaryAccent)
                } else {
                    ScrollView {
                        VStack(spacing: 24) {
                            // Status icon and message
                            VStack(spacing: 16) {
                                Image(systemName: viewModel.taxInfoOnFile ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                                    .font(.system(size: 48))
                                    .foregroundColor(viewModel.taxInfoOnFile ? .green : .orange)
                                
                                Text(viewModel.taxInfoOnFile ? "Tax Info Complete" : "Tax Info Required")
                                    .font(.title2.bold())
                                    .foregroundColor(.textPrimary)
                                
                                Text(viewModel.message)
                                    .font(.subheadline)
                                    .foregroundColor(.textSecondary)
                                    .multilineTextAlignment(.center)
                                    .padding(.horizontal)
                            }
                            .padding(.top, 32)
                            
                            // Explanation card
                            VStack(alignment: .leading, spacing: 12) {
                                Text("How It Works")
                                    .font(.headline)
                                    .foregroundColor(.textPrimary)
                                
                                VStack(alignment: .leading, spacing: 10) {
                                    infoRow(icon: "1.circle.fill", text: "When you earn your first payout, we'll add you to our payment system (Xero)")
                                    infoRow(icon: "2.circle.fill", text: "Xero will email you to collect your W-9 tax information (legal name, TIN, address)")
                                    infoRow(icon: "3.circle.fill", text: "Once complete, payouts are processed on the 15th of each month")
                                }
                            }
                            .padding()
                            .background(Color.cardBackground)
                            .cornerRadius(12)
                            .padding(.horizontal)
                            
                            // Info note
                            VStack(spacing: 8) {
                                Text("Your tax information is collected and stored securely by Xero, our accounting partner. Apes Together never stores your SSN/EIN.")
                                    .font(.caption)
                                    .foregroundColor(.textSecondary)
                                    .multilineTextAlignment(.center)
                                    .padding(.horizontal)
                            }
                            .padding(.bottom, 32)
                        }
                    }
                }
            }
            .navigationTitle("Tax Info")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Done") { dismiss() }
                        .foregroundColor(.primaryAccent)
                }
            }
        }
        .task { await viewModel.loadStatus() }
    }
    
    private func infoRow(icon: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .foregroundColor(.primaryAccent)
                .font(.subheadline)
                .frame(width: 24)
            Text(text)
                .font(.subheadline)
                .foregroundColor(.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - View Model

@MainActor
class TaxInfoViewModel: ObservableObject {
    @Published var isLoading = true
    @Published var taxInfoOnFile = false
    @Published var message = ""
    
    func loadStatus() async {
        isLoading = true
        defer { isLoading = false }
        
        do {
            let status: TaxStatusResponse = try await APIService.shared.getTaxStatus()
            taxInfoOnFile = status.taxInfoOnFile
            message = status.message
        } catch {
            taxInfoOnFile = false
            message = "Unable to check tax info status. Please try again later."
        }
    }
}

// MARK: - Preview

#Preview {
    TaxInfoView()
        .environmentObject(AuthenticationManager())
}
