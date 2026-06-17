import SwiftUI

// MARK: - W-9 Models

struct W9StatusResponse: Codable {
    let status: String          // not_submitted | submitted | on_file | failed
    let `required`: Bool        // payout-eligible and not yet on file
    let onFile: Bool
    let tinLast4: String?
    let legalName: String?
    let heldPayoutCount: Int
    let heldPayoutTotal: Double
}

struct W9SubmitResponse: Codable {
    let status: String
    let onFile: Bool
    let tinLast4: String?
    let releasedPayouts: Int?
    let message: String?
}

// MARK: - Tax Info / W-9 Screen

struct TaxInfoView: View {
    @Environment(\.dismiss) var dismiss
    @StateObject private var viewModel = W9ViewModel()

    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                if viewModel.isLoading {
                    ProgressView().tint(.primaryAccent)
                } else if viewModel.onFile {
                    onFileView
                } else if viewModel.required {
                    formView
                } else {
                    notNeededView
                }
            }
            .navigationTitle("Tax Info (W-9)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Close") { dismiss() }.foregroundColor(.primaryAccent)
                }
            }
        }
        .task { await viewModel.loadStatus() }
    }

    // On-file confirmation
    private var onFileView: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 48)).foregroundColor(.green)
                Text("W-9 on File").font(.title2.bold()).foregroundColor(.textPrimary)
                if let last4 = viewModel.tinLast4 {
                    Text("TIN ending in •••\(last4)")
                        .font(.subheadline).foregroundColor(.textSecondary)
                }
                Text("Your payouts are cleared for payment. We never store your full SSN/EIN — it's held only by our accounting partner (Xero) for 1099 reporting.")
                    .font(.caption).foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center).padding(.horizontal)
            }
            .padding(.top, 40)
        }
    }

    // Shown to users who don't yet have a subscriber — we don't collect W-9s
    // from everyone, only from creators who are actually due a payout.
    private var notNeededView: some View {
        ScrollView {
            VStack(spacing: 16) {
                Image(systemName: "doc.text.magnifyingglass")
                    .font(.system(size: 44)).foregroundColor(.textSecondary)
                Text("No tax info needed yet").font(.title3.bold()).foregroundColor(.textPrimary)
                Text("We only collect a W-9 once you have your first paying subscriber and are due a payout. We'll prompt you here when that happens.")
                    .font(.callout).foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center).padding(.horizontal)
            }
            .padding(.top, 48)
        }
    }

    // The actual W-9 form
    private var formView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if viewModel.heldPayoutTotal > 0 {
                    bannerView
                }
                Text("We need your W-9 before we can pay you — the IRS requires it for creator payouts. Your full TIN is sent securely to our accounting partner (Xero) and is never stored on ApesTogether's servers.")
                    .font(.footnote).foregroundColor(.textSecondary)

                group("Legal name (as on your tax return)") {
                    field("Full legal name", text: $viewModel.legalName)
                }
                group("Business name (optional)") {
                    field("DBA / entity name", text: $viewModel.businessName)
                }
                group("Federal tax classification") {
                    Picker("Classification", selection: $viewModel.taxClassification) {
                        ForEach(W9ViewModel.classifications, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .pickerStyle(.menu).tint(.primaryAccent)
                }
                group("Taxpayer ID number") {
                    Picker("TIN type", selection: $viewModel.tinType) {
                        Text("SSN").tag("ssn"); Text("EIN").tag("ein")
                    }.pickerStyle(.segmented)
                    field(viewModel.tinType == "ssn" ? "SSN (9 digits)" : "EIN (9 digits)",
                          text: $viewModel.tin, keyboard: .numberPad)
                }
                group("Mailing address") {
                    field("Street address", text: $viewModel.addressLine1)
                    field("Apt / suite (optional)", text: $viewModel.addressLine2)
                    field("City", text: $viewModel.city)
                    HStack {
                        field("State", text: $viewModel.state)
                        field("ZIP", text: $viewModel.postalCode, keyboard: .numbersAndPunctuation)
                    }
                }

                Toggle(isOn: $viewModel.certified) {
                    Text("Under penalties of perjury, I certify the information above is correct and that I am a U.S. person.")
                        .font(.caption).foregroundColor(.textSecondary)
                }.toggleStyle(SwitchToggleStyle(tint: .primaryAccent))

                if let err = viewModel.error {
                    Text(err).font(.caption).foregroundColor(.red)
                }

                Button {
                    Task { await viewModel.submit() }
                } label: {
                    HStack {
                        if viewModel.isSubmitting { ProgressView().tint(.appBackground) }
                        Text(viewModel.isSubmitting ? "Submitting…" : "Submit W-9")
                            .font(.headline).foregroundColor(.appBackground)
                    }
                    .frame(maxWidth: .infinity).padding()
                    .background(viewModel.canSubmit ? Color.primaryAccent : Color.gray)
                    .cornerRadius(12)
                }
                .disabled(!viewModel.canSubmit || viewModel.isSubmitting)
            }
            .padding()
        }
    }

    private var bannerView: some View {
        HStack(spacing: 10) {
            Image(systemName: "clock.badge.exclamationmark").foregroundColor(.orange)
            Text("\(viewModel.heldPayoutTotal, specifier: "$%.2f") in payouts is on hold until your W-9 is received.")
                .font(.caption).foregroundColor(.textPrimary)
        }
        .padding().frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.15)).cornerRadius(10)
    }

    private func group<Content: View>(_ title: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.caption.weight(.semibold)).foregroundColor(.textSecondary)
            content()
        }
    }

    private func field(_ placeholder: String, text: Binding<String>, keyboard: UIKeyboardType = .default) -> some View {
        TextField(placeholder, text: text)
            .keyboardType(keyboard)
            .autocorrectionDisabled()
            .padding(12)
            .background(Color.cardBackground)
            .cornerRadius(10)
            .foregroundColor(.textPrimary)
    }
}

// MARK: - View Model

@MainActor
class W9ViewModel: ObservableObject {
    static let classifications: [(String, String)] = [
        ("individual_sole_prop", "Individual / sole proprietor / single-member LLC"),
        ("c_corp", "C corporation"),
        ("s_corp", "S corporation"),
        ("partnership", "Partnership"),
        ("trust", "Trust / estate"),
        ("llc_c", "LLC (taxed as C corp)"),
        ("llc_s", "LLC (taxed as S corp)"),
        ("llc_p", "LLC (taxed as partnership)"),
    ]

    @Published var isLoading = true
    @Published var isSubmitting = false
    @Published var onFile = false
    @Published var required = false
    @Published var tinLast4: String?
    @Published var heldPayoutTotal: Double = 0
    @Published var error: String?

    // Form fields
    @Published var legalName = ""
    @Published var businessName = ""
    @Published var taxClassification = "individual_sole_prop"
    @Published var tinType = "ssn"
    @Published var tin = ""
    @Published var addressLine1 = ""
    @Published var addressLine2 = ""
    @Published var city = ""
    @Published var state = ""
    @Published var postalCode = ""
    @Published var certified = false

    var canSubmit: Bool {
        let digits = tin.filter(\.isNumber)
        return !legalName.isEmpty && digits.count == 9 && certified
            && !addressLine1.isEmpty && !city.isEmpty && !state.isEmpty && !postalCode.isEmpty
    }

    func loadStatus() async {
        isLoading = true; defer { isLoading = false }
        do {
            let s = try await APIService.shared.getW9Status()
            onFile = s.onFile
            required = s.required
            tinLast4 = s.tinLast4
            heldPayoutTotal = s.heldPayoutTotal
            if let name = s.legalName { legalName = name }
        } catch {
            self.error = "Couldn't load your tax status. Please try again."
        }
    }

    func submit() async {
        guard canSubmit else { return }
        isSubmitting = true; error = nil; defer { isSubmitting = false }
        let body: [String: Any] = [
            "legal_name": legalName,
            "business_name": businessName,
            "tax_classification": taxClassification,
            "tin_type": tinType,
            "tin": tin.filter(\.isNumber),
            "address_line1": addressLine1,
            "address_line2": addressLine2,
            "city": city,
            "state": state,
            "postal_code": postalCode,
            "country": "US",
            "certified": true,
        ]
        do {
            let resp = try await APIService.shared.submitW9(body)
            if resp.onFile {
                onFile = true
                tinLast4 = resp.tinLast4
            } else {
                error = resp.message ?? "Saved, but syncing is still pending. We'll retry automatically."
                onFile = false
            }
        } catch {
            self.error = "Submission failed. Please check your details and try again."
        }
    }
}

// MARK: - Preview

#Preview {
    TaxInfoView()
        .environmentObject(AuthenticationManager())
}
