"""
Add per-creator subscription "slot" products (Slots 2..N) to the local
ios/ApesTogetherApp/Configuration.storekit so the monthly/annual toggle + the
multi-subscription flow can be exercised in Xcode's LOCAL StoreKit environment
(sandbox / production use App Store Connect, not this file).

Slot 1 (the existing com.apestogether.subscription.{monthly,annual} group with
its 7-day trial) is left untouched. Slots 2..N are added WITHOUT an intro offer,
so the "one free trial per user, lifetime" rule holds (only Slot 1 has a trial).
See docs/PER_CREATOR_SUBSCRIPTION_SLOTS.md.

Idempotent: re-running won't duplicate slots already present.

Run:  python scripts/gen_storekit_slots.py

Keep MAX_SLOTS in sync with subscription_slots.MAX_SUBSCRIPTION_SLOTS.
"""

import json
import os

MAX_SLOTS = 20
STOREKIT = os.path.join(
    os.path.dirname(__file__), "..", "ios", "ApesTogetherApp", "Configuration.storekit"
)


def letter(slot: int) -> str:
    return chr(ord("A") + slot - 1)


def _subscription(slot: int, annual: bool) -> dict:
    return {
        "adHocOffers": [],
        "codeOffers": [],
        "displayPrice": "69.00" if annual else "9.00",
        "familyShareable": False,
        "groupNumber": 1 if annual else 2,
        # Locally-unique synthetic IDs (only the productID must match the app).
        "internalID": f"{'22' if annual else '23'}0000{slot:02d}",
        "localizations": [
            {
                "description": (
                    "Follow a trader's moves in real-time — best value"
                    if annual
                    else "Follow a trader's moves in real-time"
                ),
                "displayName": "Annual Subscription" if annual else "Monthly Subscription",
                "locale": "en_US",
            }
        ],
        "productID": (
            f"com.apestogether.subscription.s{slot:02d}.{'annual' if annual else 'monthly'}"
        ),
        "recurringSubscriptionPeriod": "P1Y" if annual else "P1M",
        "referenceName": f"Slot {letter(slot)} {'Annual - $69' if annual else 'Monthly - $9'}",
        "subscriptionGroupID": f"210000{slot:02d}",
        "type": "RecurringSubscription",
        # NOTE: deliberately NO "introductoryOffer" — only Slot 1 has the trial.
    }


def _group(slot: int) -> dict:
    return {
        "id": f"210000{slot:02d}",
        "localizations": [],
        "name": f"Trader Subscription {letter(slot)}",
        # Annual first (matches Slot 1's ordering), then monthly.
        "subscriptions": [_subscription(slot, True), _subscription(slot, False)],
    }


def main() -> None:
    with open(STOREKIT, "r", encoding="utf-8") as f:
        data = json.load(f)

    groups = data.setdefault("subscriptionGroups", [])
    existing = {s.get("productID") for g in groups for s in g.get("subscriptions", [])}

    added = 0
    for slot in range(2, MAX_SLOTS + 1):
        if f"com.apestogether.subscription.s{slot:02d}.annual" in existing:
            continue
        groups.append(_group(slot))
        added += 1

    with open(STOREKIT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"Added {added} slot group(s); Configuration.storekit now has {len(groups)} groups.")


if __name__ == "__main__":
    main()
