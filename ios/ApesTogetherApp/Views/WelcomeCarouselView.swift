import SwiftUI

struct WelcomeCarouselView: View {
    @Binding var isComplete: Bool
    @State private var currentPage = 0
    
    var body: some View {
        ZStack {
            LinearGradient.heroGradient
                .ignoresSafeArea()
            
            VStack(spacing: 0) {
                // Skip button
                HStack {
                    Spacer()
                    Button("Skip") {
                        withAnimation {
                            isComplete = true
                        }
                    }
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(.textSecondary)
                    .padding(.horizontal, 24)
                    .padding(.top, 16)
                }
                
                Spacer()
                
                // Pages
                TabView(selection: $currentPage) {
                    // Screen 1: Trade alerts value prop
                    CarouselPage(
                        icon: "bell.badge.fill",
                        headline: "Know when the best\ntraders buy and sell",
                        subtext: "Get real-time alerts the moment\ntop investors make a move",
                        accentWord: "buy and sell"
                    )
                    .tag(0)
                    
                    // Screen 2: Earn money value prop
                    CarouselPage(
                        icon: "dollarsign.circle.fill",
                        headline: "Get paid to share\nyour trades",
                        subtext: "Build a following and earn\nfrom every subscriber",
                        accentWord: "your trades"
                    )
                    .tag(1)
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                
                Spacer()
                
                // Page indicator dots
                HStack(spacing: 8) {
                    ForEach(0..<2, id: \.self) { index in
                        Circle()
                            .fill(currentPage == index ? Color.primaryAccent : Color.textMuted)
                            .frame(width: 8, height: 8)
                            .animation(.easeInOut(duration: 0.2), value: currentPage)
                    }
                }
                .padding(.bottom, 32)
                
                // CTA Button
                Button {
                    if currentPage < 1 {
                        withAnimation {
                            currentPage += 1
                        }
                    } else {
                        withAnimation {
                            isComplete = true
                        }
                    }
                } label: {
                    Text(currentPage < 1 ? "Next" : "Get Started")
                }
                .buttonStyle(PrimaryButtonStyle())
                .padding(.horizontal, 40)
                .padding(.bottom, 50)
            }
        }
    }
}

struct CarouselPage: View {
    let icon: String
    let headline: String
    let subtext: String
    var accentWord: String? = nil
    
    var body: some View {
        VStack(spacing: 32) {
            // Icon
            ZStack {
                Circle()
                    .fill(Color.primaryAccent.opacity(0.12))
                    .frame(width: 120, height: 120)
                
                Image(systemName: icon)
                    .font(.system(size: 50))
                    .foregroundColor(.primaryAccent)
            }
            
            // Headline with optional accent word
            VStack(spacing: 16) {
                if let accent = accentWord, let range = headline.range(of: accent) {
                    let before = String(headline[headline.startIndex..<range.lowerBound])
                    let after = String(headline[range.upperBound..<headline.endIndex])
                    
                    (Text(before)
                        .foregroundColor(.textPrimary) +
                    Text(accent)
                        .foregroundColor(.primaryAccent) +
                    Text(after)
                        .foregroundColor(.textPrimary))
                        .font(.system(size: 28, weight: .bold))
                        .multilineTextAlignment(.center)
                } else {
                    Text(headline)
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(.textPrimary)
                        .multilineTextAlignment(.center)
                }
                
                Text(subtext)
                    .font(.body)
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(4)
            }
        }
        .padding(.horizontal, 40)
    }
}

struct WelcomeCarouselView_Previews: PreviewProvider {
    static var previews: some View {
        WelcomeCarouselView(isComplete: .constant(false))
    }
}
