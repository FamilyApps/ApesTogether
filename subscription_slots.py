"""
Per-creator subscription "slots".

A bounded pool of generic, identical-price subscription products. Each slot is its
own iOS subscription group (so slots are independently cancelable) and its own
monthly/annual product pair. The store only knows about the slots ("Subscription
A".."Subscription T"); WHICH creator a slot maps to is held per-user on our backend
(see MobileSubscription.slot + subscribed_to_id).

Slot 1 reuses the original product IDs (which already carry the 7-day free trial in
App Store Connect / Play Console). Slots 2..N are trial-free, so the user gets
exactly one free trial in their lifetime — enforced natively by the stores, since
the first subscription always lands in Slot 1 and intro-offer eligibility is
once-per-group/product per account.

Design doc: docs/PER_CREATOR_SUBSCRIPTION_SLOTS.md
"""

import re

# Max concurrent subscriptions a single user may hold. Over-provisioning is cheap
# (each slot is a one-time store product); bump this only by also creating the
# corresponding products in App Store Connect + Play Console.
MAX_SUBSCRIPTION_SLOTS = 20

# Slot 1 == the original products (already have the trial configured).
LEGACY_MONTHLY_PRODUCT_ID = "com.apestogether.subscription.monthly"
LEGACY_ANNUAL_PRODUCT_ID = "com.apestogether.subscription.annual"

_SLOT_RE = re.compile(r"^com\.apestogether\.subscription\.s(\d{2})\.(monthly|annual)$")


def monthly_product_id(slot: int) -> str:
    if slot == 1:
        return LEGACY_MONTHLY_PRODUCT_ID
    return f"com.apestogether.subscription.s{slot:02d}.monthly"


def annual_product_id(slot: int) -> str:
    if slot == 1:
        return LEGACY_ANNUAL_PRODUCT_ID
    return f"com.apestogether.subscription.s{slot:02d}.annual"


def slot_for_product_id(product_id: str):
    """Return the 1-based slot index for a product ID, or None if unrecognized."""
    if not product_id:
        return None
    if product_id in (LEGACY_MONTHLY_PRODUCT_ID, LEGACY_ANNUAL_PRODUCT_ID):
        return 1
    m = _SLOT_RE.match(product_id)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= MAX_SUBSCRIPTION_SLOTS else None


def slot_label(slot: int) -> str:
    """1 -> 'A', 2 -> 'B', ... (matches the store-facing 'Subscription A/B/...')."""
    if slot is None or slot < 1:
        return "?"
    # Beyond 26 slots this would need AA/AB; N=20 keeps us within A..T.
    return chr(ord('A') + (slot - 1))


def all_product_ids() -> list:
    """Every slot product ID (monthly + annual), for client product-detail queries."""
    ids = []
    for s in range(1, MAX_SUBSCRIPTION_SLOTS + 1):
        ids.append(monthly_product_id(s))
        ids.append(annual_product_id(s))
    return ids
