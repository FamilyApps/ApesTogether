"""
Milestone Email Service
Sends congratulatory emails when influencers hit key milestones:
  - First subscriber
  - First payment (first subscriber's trial converts to paid)
  - Subscriber count milestones (10, 25, 50, 100, 250, 500, 1000)
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SUBSCRIBER_MILESTONES = [1, 10, 25, 50, 100, 250, 500, 1000]


def check_subscription_milestones(influencer_user_id, new_subscriber_id):
    """
    Check if a new subscription triggers a milestone for the influencer.
    Called after a MobileSubscription is created/activated.

    Args:
        influencer_user_id: The portfolio owner who just got a new subscriber
        new_subscriber_id: The user who just subscribed
    """
    from models import db, User, MobileSubscription, AdminSubscription

    influencer = User.query.get(influencer_user_id)
    if not influencer:
        return

    # Count total active subscribers (real + gifted)
    real_count = MobileSubscription.query.filter_by(
        subscribed_to_id=influencer_user_id,
        status='active'
    ).count()

    gifted_count = 0
    try:
        admin_sub = AdminSubscription.query.filter_by(
            portfolio_user_id=influencer_user_id
        ).first()
        if admin_sub:
            gifted_count = admin_sub.bonus_subscriber_count or 0
    except Exception:
        pass

    total_subs = real_count + gifted_count

    # Each milestone fires ONCE EVER per influencer, tracked in
    # User.extra_data['milestones_sent']. The active-sub count alone is not a
    # safe trigger: it re-crosses milestone boundaries whenever a sub expires
    # and a new one arrives (or the same purchase is re-validated / restored),
    # which sent duplicate "first subscriber" emails.
    extra = dict(influencer.extra_data or {})
    sent = set(extra.get('milestones_sent') or [])

    unsent = [m for m in SUBSCRIBER_MILESTONES if total_subs >= m and m not in sent]
    if not unsent:
        return

    # Send only the highest newly-reached milestone (a jump from e.g. 0 -> 12
    # gifted subs shouldn't fire two congratulation emails at once).
    milestone = max(unsent)
    if _send_milestone_email(influencer, milestone, total_subs, real_count, gifted_count):
        # Mark every milestone at or below the current count as consumed, so
        # skipped-over ones can never fire late. Only mark on a successful
        # send — a transient email failure retries at the next sub event.
        extra['milestones_sent'] = sorted(sent | {m for m in SUBSCRIBER_MILESTONES if total_subs >= m})
        influencer.extra_data = extra
        db.session.commit()


def _send_milestone_email(influencer, milestone, total_subs, real_count, gifted_count):
    """Send the appropriate milestone congratulation email.

    Returns True if the email was accepted for delivery ('sent'), else False.
    """
    from services.notification_utils import send_email

    email = influencer.email
    if not email:
        logger.warning(f"No email for influencer {influencer.id}, skipping milestone email")
        return False

    username = influencer.username or 'there'

    slug = influencer.portfolio_slug or ''
    # /p/<slug> — the real public-portfolio web route AND the App Links /
    # Universal Links path (AASA + assetlinks both register /p/*), so the tap
    # opens the app when installed. /portfolio/<slug> was a 404.
    share_url = f"https://apestogether.ai/p/{slug}" if slug else "https://apestogether.ai"
    # Deep link into the app's Share Performance screen
    app_deep_link = f"apestogether://share-performance"

    share_cta = (
        f"\n\n📣 Share your achievement! Open the app and tap Share Performance "
        f"on your portfolio to post your results:\n"
        f"  {app_deep_link}\n\n"
        f"Or share your public portfolio link:\n"
        f"  {share_url}\n"
    )

    if milestone == 1:
        subject = "🎉 You got your first subscriber!"
        body = (
            f"Hey {username},\n\n"
            f"Congratulations — someone just subscribed to follow your trades on ApesTogether!\n\n"
            f"This is a big deal. Every great portfolio starts with subscriber #1.\n\n"
            f"Your subscribers will now see your trades in real time. Keep doing what you're doing, "
            f"and the community will keep growing."
            + share_cta
            + f"\n— The ApesTogether Team"
        )
    elif milestone == 10:
        subject = "🔥 10 subscribers! You're building momentum"
        body = (
            f"Hey {username},\n\n"
            f"You just hit 10 subscribers on ApesTogether. That's real traction.\n\n"
            f"10 people are now watching your trades and trusting your strategy. "
            f"Keep sharing your moves — the next milestone is 25."
            + share_cta
            + f"\n— The ApesTogether Team"
        )
    elif milestone == 25:
        subject = "⭐ 25 subscribers — you're in the top tier"
        body = (
            f"Hey {username},\n\n"
            f"25 subscribers! You're one of the most-followed traders on the platform.\n\n"
            f"At this rate, you're building a real following. "
            f"Your trades are making an impact."
            + share_cta
            + f"\n— The ApesTogether Team"
        )
    elif milestone == 50:
        subject = "🚀 50 subscribers!"
        body = (
            f"Hey {username},\n\n"
            f"Half a hundred subscribers are now following your trades. Incredible.\n\n"
            f"You're in elite territory on ApesTogether. Keep it up."
            + share_cta
            + f"\n— The ApesTogether Team"
        )
    elif milestone == 100:
        subject = "💯 100 subscribers — triple digits!"
        body = (
            f"Hey {username},\n\n"
            f"You just crossed 100 subscribers on ApesTogether.\n\n"
            f"100 people are following your every trade. That's a real community."
            + share_cta
            + f"\n— The ApesTogether Team"
        )
    else:
        subject = f"🏆 {milestone} subscribers!"
        body = (
            f"Hey {username},\n\n"
            f"You've reached {milestone} subscribers on ApesTogether. "
            f"That's an incredible milestone."
            + share_cta
            + f"\n— The ApesTogether Team"
        )

    result = send_email(email, subject, body)
    logger.info(f"Milestone email sent to {influencer.username}: {milestone} subscribers (result: {result.get('status')})")
    return result.get('status') == 'sent'
