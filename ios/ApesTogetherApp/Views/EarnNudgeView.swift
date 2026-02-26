import SwiftUI

struct EarnNudgeView: View {
    let subscribedToUsername: String
    let onAddStocks: () -> Void
    let onSkip: () -> Void
    
    @State private var showConfetti = false
    
    var body: some View {
        ZStack {
            LinearGradient.heroGradient
                .ignoresSafeArea()
            
            VStack(spacing: 32) {
                Spacer()
                
                // Success checkmark
                ZStack {
                    Circle()
                        .fill(Color.primaryAccent.opacity(0.15))
                        .frame(width: 100, height: 100)
                    
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 56))
                        .foregroundColor(.primaryAccent)
                        .scaleEffect(showConfetti ? 1.0 : 0.5)
                        .opacity(showConfetti ? 1.0 : 0)
                        .animation(.spring(response: 0.5, dampingFraction: 0.6), value: showConfetti)
                }
                
                VStack(spacing: 12) {
                    Text("You're in!")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(.textPrimary)
                    
                    Text("You'll get notified the moment\n\(subscribedToUsername) makes a trade.")
                        .font(.body)
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }
                
                Spacer()
                
                // Earn money nudge card
                VStack(spacing: 16) {
                    HStack(spacing: 12) {
                        Image(systemName: "dollarsign.circle.fill")
                            .font(.system(size: 28))
                            .foregroundColor(.primaryAccent)
                        
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Want to earn money too?")
                                .font(.headline)
                                .foregroundColor(.textPrimary)
                            
                            Text("Add your stocks and get paid when others follow your trades.")
                                .font(.caption)
                                .foregroundColor(.textSecondary)
                        }
                    }
                }
                .cardStyle()
                .padding(.horizontal, 20)
                
                // Buttons
                VStack(spacing: 12) {
                    Button {
                        onAddStocks()
                    } label: {
                        Text("Add Your Stocks")
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    
                    Button {
                        onSkip()
                    } label: {
                        Text("Not now")
                            .font(.subheadline)
                            .foregroundColor(.textSecondary)
                    }
                }
                .padding(.horizontal, 40)
                .padding(.bottom, 50)
            }
        }
        .onAppear {
            withAnimation(.easeOut(duration: 0.5).delay(0.2)) {
                showConfetti = true
            }
        }
    }
}

struct EarnNudgeView_Previews: PreviewProvider {
    static var previews: some View {
        EarnNudgeView(
            subscribedToUsername: "clever-fox",
            onAddStocks: {},
            onSkip: {}
        )
    }
}
