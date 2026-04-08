import SwiftUI

// MARK: - W-9 Status Response Model

struct W9StatusResponse: Codable {
    let hasW9: Bool
    let status: String
    let submittedAt: String?
    let reviewedAt: String?
    let rejectionReason: String?
    let tinDisplay: String?
    let legalName: String?
    let message: String?
}

struct W9SubmitResponse: Codable {
    let success: Bool?
    let w9Id: Int?
    let status: String?
    let message: String?
    let error: String?
    let details: [String]?
}

// MARK: - W-9 Form View

struct W9FormView: View {
    @Environment(\.dismiss) var dismiss
    @StateObject private var viewModel = W9FormViewModel()
    
    var body: some View {
        NavigationView {
            ZStack {
                Color.appBackground.ignoresSafeArea()
                
                if viewModel.isLoading {
                    ProgressView()
                        .tint(.primaryAccent)
                } else if viewModel.hasActiveW9 {
                    w9StatusView
                } else {
                    w9FormContent
                }
            }
            .navigationTitle("W-9 Tax Form")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(.primaryAccent)
                }
            }
            .alert("Error", isPresented: $viewModel.showError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(viewModel.errorMessage)
            }
            .alert("W-9 Submitted", isPresented: $viewModel.showSuccess) {
                Button("Done") { dismiss() }
            } message: {
                Text("Your W-9 has been submitted successfully and is under review.")
            }
        }
        .task { await viewModel.loadStatus() }
    }
    
    // MARK: - Status View (existing W-9)
    
    private var w9StatusView: some View {
        ScrollView {
            VStack(spacing: 24) {
                VStack(spacing: 16) {
                    Image(systemName: statusIcon)
                        .font(.system(size: 48))
                        .foregroundColor(statusColor)
                    
                    Text(statusTitle)
                        .font(.title2.bold())
                        .foregroundColor(.textPrimary)
                    
                    Text(viewModel.statusMessage)
                        .font(.subheadline)
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.top, 32)
                
                VStack(spacing: 0) {
                    SettingsRow(label: "Name", value: viewModel.statusLegalName)
                    AccentDivider()
                    SettingsRow(label: "TIN", value: viewModel.statusTinDisplay)
                    AccentDivider()
                    SettingsRow(label: "Status", value: viewModel.statusText.capitalized)
                    if let date = viewModel.statusSubmittedAt {
                        AccentDivider()
                        SettingsRow(label: "Submitted", value: date)
                    }
                }
                .cardStyle(padding: 0)
                
                if viewModel.statusText == "rejected" {
                    Button {
                        viewModel.hasActiveW9 = false
                    } label: {
                        Text("Resubmit W-9")
                            .font(.headline)
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(Color.primaryAccent)
                            .cornerRadius(12)
                    }
                    .padding(.horizontal)
                }
            }
            .padding()
        }
    }
    
    private var statusIcon: String {
        switch viewModel.statusText {
        case "verified": return "checkmark.seal.fill"
        case "rejected": return "xmark.octagon.fill"
        default: return "clock.fill"
        }
    }
    
    private var statusColor: Color {
        switch viewModel.statusText {
        case "verified": return .green
        case "rejected": return .red
        default: return .orange
        }
    }
    
    private var statusTitle: String {
        switch viewModel.statusText {
        case "verified": return "W-9 Verified"
        case "rejected": return "W-9 Rejected"
        case "submitted": return "Under Review"
        default: return "W-9 Status"
        }
    }
    
    // MARK: - Form Content
    
    private var w9FormContent: some View {
        ScrollView {
            VStack(spacing: 24) {
                // Header
                VStack(spacing: 8) {
                    Text("IRS Form W-9")
                        .font(.title2.bold())
                        .foregroundColor(.textPrimary)
                    Text("Request for Taxpayer Identification Number and Certification")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.top, 8)
                
                // Legal Name Section
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Legal Name")
                    VStack(spacing: 12) {
                        FormField(title: "First Name", text: $viewModel.firstName, placeholder: "As shown on tax return")
                        FormField(title: "Last Name", text: $viewModel.lastName, placeholder: "As shown on tax return")
                        FormField(title: "Business Name", text: $viewModel.businessName, placeholder: "Optional — DBA or entity name")
                    }
                    .cardStyle(padding: 0)
                }
                
                // Tax Classification
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Federal Tax Classification")
                    VStack(spacing: 0) {
                        ForEach(TaxClassification.allCases) { classification in
                            Button {
                                viewModel.taxClassification = classification
                            } label: {
                                HStack {
                                    Image(systemName: viewModel.taxClassification == classification ? "checkmark.circle.fill" : "circle")
                                        .foregroundColor(viewModel.taxClassification == classification ? .primaryAccent : .textSecondary)
                                    Text(classification.displayName)
                                        .foregroundColor(.textPrimary)
                                        .font(.subheadline)
                                    Spacer()
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                            }
                            if classification != TaxClassification.allCases.last {
                                AccentDivider()
                            }
                        }
                    }
                    .cardStyle(padding: 0)
                }
                
                // Address
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Address")
                    VStack(spacing: 12) {
                        FormField(title: "Street Address", text: $viewModel.address1, placeholder: "123 Main St")
                        FormField(title: "Apt/Suite", text: $viewModel.address2, placeholder: "Optional")
                        FormField(title: "City", text: $viewModel.city, placeholder: "City")
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("State")
                                    .font(.caption)
                                    .foregroundColor(.textSecondary)
                                    .padding(.horizontal, 16)
                                Picker("State", selection: $viewModel.state) {
                                    Text("Select").tag("")
                                    ForEach(USState.allCases) { state in
                                        Text(state.rawValue).tag(state.rawValue)
                                    }
                                }
                                .pickerStyle(.menu)
                                .tint(.primaryAccent)
                                .padding(.horizontal, 12)
                                .padding(.bottom, 8)
                            }
                            .frame(maxWidth: .infinity)
                            FormField(title: "ZIP Code", text: $viewModel.zipCode, placeholder: "12345")
                                .keyboardType(.numberPad)
                        }
                    }
                    .cardStyle(padding: 0)
                }
                
                // TIN
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Taxpayer ID Number")
                    VStack(spacing: 12) {
                        Picker("TIN Type", selection: $viewModel.tinType) {
                            Text("SSN").tag("ssn")
                            Text("EIN").tag("ein")
                        }
                        .pickerStyle(.segmented)
                        .padding(.horizontal, 16)
                        .padding(.top, 12)
                        
                        FormField(
                            title: viewModel.tinType == "ssn" ? "Social Security Number" : "Employer Identification Number",
                            text: $viewModel.tin,
                            placeholder: viewModel.tinType == "ssn" ? "XXX-XX-XXXX" : "XX-XXXXXXX",
                            isSecure: true
                        )
                        .keyboardType(.numberPad)
                    }
                    .cardStyle(padding: 0)
                    
                    Text("Your TIN is encrypted at rest and never stored in plain text.")
                        .font(.caption2)
                        .foregroundColor(.textSecondary)
                        .padding(.horizontal, 4)
                }
                
                // E-Signature
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Electronic Signature")
                    VStack(spacing: 12) {
                        Text("Under penalties of perjury, I certify that the number shown on this form is my correct taxpayer identification number and that I am a U.S. citizen or U.S. resident alien.")
                            .font(.caption)
                            .foregroundColor(.textSecondary)
                            .padding(.horizontal, 16)
                            .padding(.top, 12)
                        
                        FormField(title: "Type Your Full Legal Name", text: $viewModel.signatureName, placeholder: "John A. Doe")
                        
                        Toggle(isOn: $viewModel.certify) {
                            Text("I certify that the information above is true and correct")
                                .font(.caption)
                                .foregroundColor(.textPrimary)
                        }
                        .toggleStyle(SwitchToggleStyle(tint: Color.primaryAccent))
                        .padding(.horizontal, 16)
                        .padding(.bottom, 12)
                    }
                    .cardStyle(padding: 0)
                }
                
                // Submit Button
                Button {
                    Task { await viewModel.submit() }
                } label: {
                    if viewModel.isSubmitting {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding()
                    } else {
                        Text("Submit W-9")
                            .font(.headline)
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity)
                            .padding()
                    }
                }
                .background(viewModel.isFormValid ? Color.primaryAccent : Color.gray.opacity(0.3))
                .cornerRadius(12)
                .disabled(!viewModel.isFormValid || viewModel.isSubmitting)
                .padding(.bottom, 32)
            }
            .padding()
        }
    }
}

// MARK: - Form Field

private struct FormField: View {
    let title: String
    @Binding var text: String
    var placeholder: String = ""
    var isSecure: Bool = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundColor(.textSecondary)
            if isSecure {
                SecureField(placeholder, text: $text)
                    .font(.body)
                    .foregroundColor(.textPrimary)
            } else {
                TextField(placeholder, text: $text)
                    .font(.body)
                    .foregroundColor(.textPrimary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }
}

// MARK: - View Model

@MainActor
class W9FormViewModel: ObservableObject {
    // Status
    @Published var isLoading = true
    @Published var hasActiveW9 = false
    @Published var statusText = ""
    @Published var statusMessage = ""
    @Published var statusLegalName = ""
    @Published var statusTinDisplay = ""
    @Published var statusSubmittedAt: String? = nil
    
    // Form fields
    @Published var firstName = ""
    @Published var lastName = ""
    @Published var businessName = ""
    @Published var taxClassification: TaxClassification = .individual
    @Published var address1 = ""
    @Published var address2 = ""
    @Published var city = ""
    @Published var state = ""
    @Published var zipCode = ""
    @Published var tinType = "ssn"
    @Published var tin = ""
    @Published var signatureName = ""
    @Published var certify = false
    
    // UI state
    @Published var isSubmitting = false
    @Published var showError = false
    @Published var showSuccess = false
    @Published var errorMessage = ""
    
    var isFormValid: Bool {
        !firstName.trimmingCharacters(in: .whitespaces).isEmpty &&
        !lastName.trimmingCharacters(in: .whitespaces).isEmpty &&
        !address1.trimmingCharacters(in: .whitespaces).isEmpty &&
        !city.trimmingCharacters(in: .whitespaces).isEmpty &&
        !state.isEmpty &&
        zipCode.count >= 5 &&
        tin.filter(\.isNumber).count == 9 &&
        !signatureName.trimmingCharacters(in: .whitespaces).isEmpty &&
        certify
    }
    
    func loadStatus() async {
        isLoading = true
        defer { isLoading = false }
        
        do {
            let status: W9StatusResponse = try await APIService.shared.getW9Status()
            if status.hasW9 {
                hasActiveW9 = true
                statusText = status.status
                statusMessage = status.message ?? ""
                statusLegalName = status.legalName ?? ""
                statusTinDisplay = status.tinDisplay ?? ""
                statusSubmittedAt = formatDate(status.submittedAt)
            }
        } catch {
            // No W-9 on file — show form
            hasActiveW9 = false
        }
    }
    
    func submit() async {
        guard isFormValid else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        
        do {
            let response: W9SubmitResponse = try await APIService.shared.submitW9(
                firstName: firstName.trimmingCharacters(in: .whitespaces),
                lastName: lastName.trimmingCharacters(in: .whitespaces),
                businessName: businessName.trimmingCharacters(in: .whitespaces),
                taxClassification: taxClassification.rawValue,
                address1: address1.trimmingCharacters(in: .whitespaces),
                address2: address2.trimmingCharacters(in: .whitespaces),
                city: city.trimmingCharacters(in: .whitespaces),
                state: state,
                zipCode: zipCode.trimmingCharacters(in: .whitespaces),
                tinType: tinType,
                tin: tin.filter(\.isNumber),
                signatureName: signatureName.trimmingCharacters(in: .whitespaces)
            )
            
            if response.success == true {
                showSuccess = true
            } else {
                let details = response.details?.joined(separator: "\n") ?? response.error ?? "Submission failed"
                errorMessage = details
                showError = true
            }
        } catch {
            errorMessage = error.localizedDescription
            showError = true
        }
    }
    
    private func formatDate(_ iso: String?) -> String? {
        guard let iso = iso else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: iso) {
            let display = DateFormatter()
            display.dateStyle = .medium
            display.timeStyle = .none
            return display.string(from: date)
        }
        // Try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: iso) {
            let display = DateFormatter()
            display.dateStyle = .medium
            display.timeStyle = .none
            return display.string(from: date)
        }
        return String(iso.prefix(10))
    }
}

// MARK: - Tax Classification Enum

enum TaxClassification: String, CaseIterable, Identifiable {
    case individual
    case soleProprietor = "sole_proprietor"
    case llcSingle = "llc_single"
    case llcPartnership = "llc_partnership"
    case cCorp = "c_corp"
    case sCorp = "s_corp"
    case partnership
    case trustEstate = "trust_estate"
    
    var id: String { rawValue }
    
    var displayName: String {
        switch self {
        case .individual: return "Individual"
        case .soleProprietor: return "Sole Proprietor"
        case .llcSingle: return "LLC (Single Member)"
        case .llcPartnership: return "LLC (Partnership)"
        case .cCorp: return "C Corporation"
        case .sCorp: return "S Corporation"
        case .partnership: return "Partnership"
        case .trustEstate: return "Trust / Estate"
        }
    }
}

// MARK: - US States Enum

enum USState: String, CaseIterable, Identifiable {
    case AL, AK, AZ, AR, CA, CO, CT, DE, FL, GA
    case HI, ID, IL, IN, IA, KS, KY, LA, ME, MD
    case MA, MI, MN, MS, MO, MT, NE, NV, NH, NJ
    case NM, NY, NC, ND, OH, OK, OR, PA, RI, SC
    case SD, TN, TX, UT, VT, VA, WA, WV, WI, WY
    case DC
    
    var id: String { rawValue }
}

// MARK: - Preview

#Preview {
    W9FormView()
        .environmentObject(AuthenticationManager())
}
