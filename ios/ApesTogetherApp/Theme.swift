import SwiftUI

// MARK: - Color Palette
extension Color {
    // Backgrounds
    static let appBackground = Color(hex: "0A0F0D")
    static let cardBackground = Color(hex: "141A17")
    static let cardBorder = Color(hex: "1F2A24")
    
    // Accent colors
    static let primaryAccent = Color(hex: "00D9A5")
    static let secondaryAccent = Color(hex: "34D399")
    
    // Semantic colors
    static let gains = Color(hex: "22C55E")
    static let losses = Color(hex: "EF4444")
    
    // Text colors
    static let textPrimary = Color.white
    static let textSecondary = Color(hex: "9CA3AF")
    static let textMuted = Color(hex: "6B7280")
    
    // Initialize from hex string
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - Gradients
extension LinearGradient {
    static let heroGradient = LinearGradient(
        colors: [Color.appBackground, Color(hex: "0D1A14")],
        startPoint: .top,
        endPoint: .bottom
    )
    
    static let cardGradient = LinearGradient(
        colors: [Color.cardBackground, Color(hex: "0F1512")],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
    
    static let accentGradient = LinearGradient(
        colors: [Color.primaryAccent, Color.secondaryAccent],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
}

// MARK: - Button Styles
struct PrimaryButtonStyle: ButtonStyle {
    var isDisabled: Bool = false
    
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundColor(.appBackground)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isDisabled ? Color.textMuted : Color.primaryAccent)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .opacity(configuration.isPressed ? 0.9 : 1.0)
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundColor(.primaryAccent)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.primaryAccent, lineWidth: 2)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .opacity(configuration.isPressed ? 0.9 : 1.0)
    }
}

struct PillButtonStyle: ButtonStyle {
    var isSelected: Bool = false
    
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(
                Capsule()
                    .fill(isSelected ? Color.primaryAccent : Color.cardBackground)
            )
            .overlay(
                Capsule()
                    .stroke(isSelected ? Color.clear : Color.cardBorder, lineWidth: 1)
            )
            .foregroundColor(isSelected ? .appBackground : .textSecondary)
            .scaleEffect(configuration.isPressed ? 0.95 : 1.0)
    }
}

// MARK: - Card Modifier
struct CardStyle: ViewModifier {
    var padding: CGFloat = 16
    
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color.cardBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.cardBorder, lineWidth: 1)
            )
    }
}

extension View {
    func cardStyle(padding: CGFloat = 16) -> some View {
        modifier(CardStyle(padding: padding))
    }
}

// MARK: - Status Badge
struct StatusBadge: View {
    let text: String
    let color: Color
    
    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundColor(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(color.opacity(0.15))
            )
    }
}

// MARK: - Empty State View
struct EmptyStateView: View {
    let icon: String
    let title: String
    let message: String
    var action: (() -> Void)? = nil
    var actionLabel: String? = nil
    
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: icon)
                .font(.system(size: 50))
                .foregroundColor(.primaryAccent.opacity(0.6))
            
            Text(title)
                .font(.title2.bold())
                .foregroundColor(.textPrimary)
            
            Text(message)
                .foregroundColor(.textSecondary)
                .multilineTextAlignment(.center)
            
            if let action = action, let label = actionLabel {
                Button(action: action) {
                    Text(label)
                }
                .buttonStyle(PrimaryButtonStyle())
                .padding(.horizontal, 40)
                .padding(.top, 8)
            }
        }
        .padding()
    }
}

// MARK: - Section Header
struct SectionHeader: View {
    let title: String
    var accentWord: String? = nil
    
    var body: some View {
        HStack {
            if let accent = accentWord {
                Text(title.replacingOccurrences(of: accent, with: ""))
                    .foregroundColor(.textPrimary) +
                Text(accent)
                    .foregroundColor(.primaryAccent)
            } else {
                Text(title)
                    .foregroundColor(.textPrimary)
            }
            Spacer()
        }
        .font(.headline)
    }
}

// MARK: - Divider Style
struct AccentDivider: View {
    var body: some View {
        Rectangle()
            .fill(Color.cardBorder)
            .frame(height: 1)
    }
}
