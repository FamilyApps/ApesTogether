import SwiftUI

/// One-shot "How did you hear about us?" attribution survey (marketing gap #7).
///
/// Presented as a dimmed overlay card over `MainTabView` ~1.5 s after the
/// first authenticated launch. One tap per install (UserDefaults-gated);
/// mirrors Android's `AcquisitionSurveyHost`. The backend keeps only the
/// FIRST answer (first-write-wins), so a reinstall re-ask can't corrupt
/// attribution data.
struct AcquisitionSurveyView: View {
    @Binding var isPresented: Bool

    /// Display label → backend source key. Order = display order.
    private static let options: [(String, String)] = [
        ("X / Twitter", "x"),
        ("TikTok", "tiktok"),
        ("Instagram", "instagram"),
        ("Reddit", "reddit"),
        ("Friend", "friend"),
        ("Search", "search"),
        ("Press / article", "press"),
        ("Other", "other"),
    ]

    static let doneKey = "acquisitionSurveyDone"

    var body: some View {
        ZStack {
            Color.black.opacity(0.55)
                .ignoresSafeArea()
                .onTapGesture { dismiss() }

            VStack(alignment: .leading, spacing: 0) {
                Text("How did you hear about us?")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(.textPrimary)

                Text("One tap — it helps us know where to show up.")
                    .font(.system(size: 13))
                    .foregroundColor(.textSecondary)
                    .padding(.top, 4)
                    .padding(.bottom, 14)

                let rows = Self.options.chunked(into: 2)
                ForEach(0..<rows.count, id: \.self) { rowIndex in
                    HStack(spacing: 8) {
                        ForEach(rows[rowIndex], id: \.1) { option in
                            Button(action: { answer(option.1) }) {
                                Text(option.0)
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundColor(.textPrimary)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 12)
                                    .background(
                                        RoundedRectangle(cornerRadius: 10)
                                            .stroke(Color.textSecondary.opacity(0.25), lineWidth: 1)
                                    )
                            }
                        }
                    }
                    .padding(.bottom, 8)
                }

                Button(action: { dismiss() }) {
                    Text("Skip")
                        .font(.system(size: 13))
                        .foregroundColor(.textSecondary.opacity(0.7))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
            }
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color.cardBackground)
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(Color.primaryAccent.opacity(0.15), lineWidth: 1)
                    )
            )
            .padding(.horizontal, 28)
        }
    }

    private func answer(_ source: String) {
        // Mark done first — losing one answer to a network blip beats
        // nagging the user twice.
        UserDefaults.standard.set(true, forKey: Self.doneKey)
        isPresented = false
        Task {
            do {
                try await APIService.shared.setAcquisitionSource(source)
            } catch {
                print("AcquisitionSurvey: failed to submit '\(source)': \(error)")
            }
        }
    }

    private func dismiss() {
        UserDefaults.standard.set(true, forKey: Self.doneKey)
        isPresented = false
    }
}

private extension Array {
    func chunked(into size: Int) -> [[Element]] {
        stride(from: 0, to: count, by: size).map {
            Array(self[$0..<Swift.min($0 + size, count)])
        }
    }
}
