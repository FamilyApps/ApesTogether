//
//  CompactPlanToggle.swift
//  ApesTogether
//
//  A compact, two-segment toggle between Monthly ($9/mo) and Annual ($69/yr)
//  subscription plans. Designed for tight spaces (leaderboard expanded rows,
//  portfolio detail header) where the full-size overlay plan selector is too big.
//
//  Usage:
//    CompactPlanToggle(subscriptionManager: subscriptionManager)
//
//  The toggle binds to `subscriptionManager.selectedPlan`, which is then read
//  by the subscribe button and purchase flow.
//

import SwiftUI

struct CompactPlanToggle: View {
    @ObservedObject var subscriptionManager: SubscriptionManager

    var body: some View {
        HStack(spacing: 4) {
            segment(
                plan: .annual,
                title: "Annual",
                price: "$69/yr",
                badge: "Save 36%"
            )
            segment(
                plan: .monthly,
                title: "Monthly",
                price: "$9/mo",
                badge: nil
            )
        }
        .padding(3)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color.white.opacity(0.06))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Color.white.opacity(0.04), lineWidth: 1)
        )
    }

    private func segment(
        plan: SubscriptionManager.PlanType,
        title: String,
        price: String,
        badge: String?
    ) -> some View {
        let isSelected = subscriptionManager.selectedPlan == plan
        return Button {
            withAnimation(.easeInOut(duration: 0.18)) {
                subscriptionManager.selectedPlan = plan
            }
        } label: {
            HStack(spacing: 6) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(title)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(isSelected ? .textSecondary : .textMuted)
                    Text(price)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(isSelected ? .textPrimary : .textSecondary)
                }
                if let badge = badge {
                    Text(badge)
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(isSelected ? .appBackground : .primaryAccent)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(
                            Capsule()
                                .fill(isSelected ? Color.primaryAccent : Color.primaryAccent.opacity(0.18))
                        )
                        .fixedSize()
                }
            }
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(isSelected ? Color.primaryAccent.opacity(0.12) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(isSelected ? Color.primaryAccent.opacity(0.55) : Color.clear, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
