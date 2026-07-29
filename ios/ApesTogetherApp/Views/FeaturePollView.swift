import SwiftUI

struct FeaturePollView: View {
    @StateObject private var viewModel = FeaturePollViewModel()
    
    var body: some View {
        Group {
            if let poll = viewModel.poll {
                VStack(spacing: 12) {
                    HStack {
                        Image(systemName: "chart.bar.fill")
                            .font(.system(size: 14))
                            .foregroundColor(.primaryAccent)
                        Text("Quick Poll")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.textSecondary)
                        Spacer()
                        // Deliberately NO "N votes" counter: only humans vote, so
                        // an exact total would disclose the platform's human-user
                        // count. Percentages only.
                    }
                    
                    Text(poll.question)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    
                    VStack(spacing: 8) {
                        ForEach(poll.options, id: \.self) { option in
                            let result = poll.results.first(where: { $0.option == option })
                            // New server: `percent` present. Old server: derive from votes/total.
                            let percentage: Double = {
                                if let p = result?.percent { return p }
                                let v = result?.votes ?? 0
                                let t = poll.totalVotes ?? 0
                                return t > 0 ? Double(v) / Double(t) * 100 : 0
                            }()
                            PollOptionRow(
                                option: option,
                                percentage: percentage,
                                isSelected: viewModel.selectedOption == option,
                                hasVoted: viewModel.hasVoted,
                                onTap: {
                                    Task { await viewModel.vote(pollId: poll.id, option: option) }
                                }
                            )
                        }
                    }
                    
                    if viewModel.hasVoted {
                        Text("Thanks for voting!")
                            .font(.system(size: 11))
                            .foregroundColor(.primaryAccent.opacity(0.8))
                    }
                }
                .padding(16)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(Color.cardBackground)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.primaryAccent.opacity(0.15), lineWidth: 1)
                        )
                )
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
            }
        }
        .task { await viewModel.loadPoll() }
    }
}

struct PollOptionRow: View {
    let option: String
    let percentage: Double
    let isSelected: Bool
    let hasVoted: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            ZStack(alignment: .leading) {
                // Background bar (shown after voting)
                if hasVoted {
                    GeometryReader { geo in
                        RoundedRectangle(cornerRadius: 8)
                            .fill(isSelected ? Color.primaryAccent.opacity(0.15) : Color.textSecondary.opacity(0.08))
                            .frame(width: geo.size.width * CGFloat(percentage / 100))
                    }
                }
                
                HStack {
                    Text(option)
                        .font(.system(size: 14, weight: isSelected ? .semibold : .regular))
                        .foregroundColor(isSelected ? .primaryAccent : .textPrimary)
                        .lineLimit(2)
                    
                    Spacer()
                    
                    if hasVoted {
                        Text("\(Int(percentage))%")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(isSelected ? .primaryAccent : .textSecondary)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
            }
            .frame(maxWidth: .infinity, minHeight: 40)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? Color.primaryAccent.opacity(0.4) : Color.textSecondary.opacity(0.2), lineWidth: 1)
            )
        }
        .disabled(hasVoted)
    }
}

// MARK: - ViewModel

@MainActor
class FeaturePollViewModel: ObservableObject {
    @Published var poll: PollData?
    @Published var selectedOption: String?
    @Published var hasVoted = false
    
    func loadPoll() async {
        do {
            let response = try await APIService.shared.getActivePoll()
            poll = response.poll
            if let voted = response.poll?.userVoted {
                selectedOption = voted
                hasVoted = true
            }
        } catch {
            print("Failed to load poll: \(error)")
        }
    }
    
    func vote(pollId: Int, option: String) async {
        guard !hasVoted else { return }
        
        // Optimistic update
        selectedOption = option
        hasVoted = true
        
        do {
            let _ = try await APIService.shared.voteOnPoll(pollId: pollId, selectedOption: option)
            // Reload to get updated counts
            await loadPoll()
        } catch {
            // Revert on failure
            selectedOption = nil
            hasVoted = false
            print("Failed to vote: \(error)")
        }
    }
}
