"""
Tests for payout integrity (June 2026):
  - Renewals create their own InAppPurchase row (per-period revenue + payout).
  - Transaction-driven payout aggregation (monthly vs annual).
  - Refund clawback netting (greedy, bounded, carry-forward).

Run with: pytest tests/test_payout_integrity.py -v
"""

import os
import sys
from datetime import datetime, timedelta, date

try:
    import pytest
except ImportError:  # allow running without pytest via a manual harness
    pytest = None
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_app():
    from models import db
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app, db


def _mk_users(db):
    from models import User
    trader = User(email="trader@example.com", username="trader1", portfolio_slug="trader1")
    subscriber = User(email="sub@example.com", username="sub1")
    db.session.add_all([trader, subscriber])
    db.session.commit()
    return trader, subscriber


def _mk_purchase(db, subscriber, trader, *, txn, when, price=9.00,
                 influencer_payout=6.50, platform_revenue=1.15, store_fee=1.35,
                 status="active", original=None, token=None, platform="apple"):
    from models import InAppPurchase
    p = InAppPurchase(
        subscriber_id=subscriber.id, subscribed_to_id=trader.id,
        platform=platform, product_id="sub.s01.monthly",
        transaction_id=txn, original_transaction_id=(original or txn),
        receipt_data=token, status=status, purchase_date=when,
        expires_date=when + timedelta(days=30), price=price,
        influencer_payout=influencer_payout, platform_revenue=platform_revenue,
        store_fee=store_fee,
    )
    db.session.add(p)
    db.session.commit()
    return p


# ---------------------------------------------------------------------------
# Keystone: renewals create a new row
# ---------------------------------------------------------------------------

class TestRenewalRows:
    def test_renewal_clones_economics_into_new_row(self):
        from models import db, InAppPurchase, MobileSubscription
        from iap_webhooks import _record_renewal
        app, db = _make_app()
        with app.app_context():
            db.create_all()
            trader, sub = _mk_users(db)
            base = _mk_purchase(db, sub, trader, txn="T1",
                                when=datetime(2026, 1, 5), original="ORIG1")
            ms = MobileSubscription(subscriber_id=sub.id, subscribed_to_id=trader.id,
                                    in_app_purchase_id=base.id, status="active")
            db.session.add(ms)
            db.session.commit()

            new_exp = datetime(2026, 3, 5)
            created = _record_renewal(
                db, platform="apple", new_transaction_id="T2",
                purchase_date=datetime(2026, 2, 5), expires_date=new_exp,
                original_transaction_id="ORIG1")

            assert created  # returns new id
            rows = InAppPurchase.query.order_by(InAppPurchase.purchase_date).all()
            assert len(rows) == 2
            renewal = InAppPurchase.query.filter_by(transaction_id="T2").one()
            # Economics cloned from template
            assert renewal.price == base.price
            assert renewal.influencer_payout == base.influencer_payout
            assert renewal.store_fee == base.store_fee
            assert renewal.subscribed_to_id == trader.id
            assert renewal.original_transaction_id == "ORIG1"
            assert renewal.status == "active"
            # Access subscription extended
            db.session.refresh(ms)
            assert ms.expires_at == new_exp

    def test_renewal_is_idempotent_on_existing_txn(self):
        from models import db, InAppPurchase
        from iap_webhooks import _record_renewal
        app, db = _make_app()
        with app.app_context():
            db.create_all()
            trader, sub = _mk_users(db)
            _mk_purchase(db, sub, trader, txn="T1", when=datetime(2026, 1, 5), original="ORIG1")
            # Pretend the client already recorded the renewal txn "T2"
            _mk_purchase(db, sub, trader, txn="T2", when=datetime(2026, 2, 5), original="ORIG1")

            created = _record_renewal(db, platform="apple", new_transaction_id="T2",
                                      purchase_date=datetime(2026, 2, 5),
                                      original_transaction_id="ORIG1")
            assert created == 0
            assert InAppPurchase.query.count() == 2  # no duplicate

    def test_renewal_without_template_does_not_fabricate(self):
        from models import db, InAppPurchase
        from iap_webhooks import _record_renewal
        app, db = _make_app()
        with app.app_context():
            db.create_all()
            _mk_users(db)
            created = _record_renewal(db, platform="apple", new_transaction_id="T9",
                                      purchase_date=datetime(2026, 2, 5),
                                      original_transaction_id="UNKNOWN")
            assert created == 0
            assert InAppPurchase.query.count() == 0


# ---------------------------------------------------------------------------
# Refund clawback netting
# ---------------------------------------------------------------------------

class TestClawback:
    def _paid_record(self, db, trader, period_start):
        from models import XeroPayoutRecord
        from calendar import monthrange
        pe = date(period_start.year, period_start.month,
                  monthrange(period_start.year, period_start.month)[1])
        rec = XeroPayoutRecord(portfolio_user_id=trader.id, period_start=period_start,
                               period_end=pe, payment_status='paid')
        db.session.add(rec)
        db.session.commit()
        return rec

    def test_no_clawback_when_prior_period_not_paid(self):
        from models import db
        from mobile_api import _compute_creator_clawback
        app, db = _make_app()
        with app.app_context():
            db.create_all()
            trader, sub = _mk_users(db)
            # Refunded Jan purchase, but NO paid payout record for Jan
            _mk_purchase(db, sub, trader, txn="R1", when=datetime(2026, 1, 10),
                         status="refunded")
            applied, carried, netted = _compute_creator_clawback(
                trader.id, date(2026, 2, 1), budget=100.0)
            assert applied == 0.0 and carried == 0.0 and netted == []

    def test_clawback_applies_within_budget(self):
        from models import db
        from mobile_api import _compute_creator_clawback
        app, db = _make_app()
        with app.app_context():
            db.create_all()
            trader, sub = _mk_users(db)
            self._paid_record(db, trader, date(2026, 1, 1))
            _mk_purchase(db, sub, trader, txn="R1", when=datetime(2026, 1, 10),
                         status="refunded", influencer_payout=6.50)
            applied, carried, netted = _compute_creator_clawback(
                trader.id, date(2026, 2, 1), budget=100.0)
            assert applied == 6.50 and carried == 0.0 and len(netted) == 1

    def test_clawback_carries_forward_when_over_budget(self):
        from models import db
        from mobile_api import _compute_creator_clawback
        app, db = _make_app()
        with app.app_context():
            db.create_all()
            trader, sub = _mk_users(db)
            self._paid_record(db, trader, date(2026, 1, 1))
            # Two refunded rows @ 6.50 each = 13.00, budget only 6.50
            _mk_purchase(db, sub, trader, txn="R1", when=datetime(2026, 1, 10),
                         status="refunded", influencer_payout=6.50)
            _mk_purchase(db, sub, trader, txn="R2", when=datetime(2026, 1, 12),
                         status="refunded", influencer_payout=6.50)
            applied, carried, netted = _compute_creator_clawback(
                trader.id, date(2026, 2, 1), budget=6.50)
            assert applied == 6.50
            assert carried == 6.50
            assert len(netted) == 1

    def test_already_reversed_rows_excluded(self):
        from models import db
        from mobile_api import _compute_creator_clawback
        app, db = _make_app()
        with app.app_context():
            db.create_all()
            trader, sub = _mk_users(db)
            self._paid_record(db, trader, date(2026, 1, 1))
            p = _mk_purchase(db, sub, trader, txn="R1", when=datetime(2026, 1, 10),
                             status="refunded", influencer_payout=6.50)
            p.payout_reversed_at = datetime.utcnow()
            db.session.commit()
            applied, carried, netted = _compute_creator_clawback(
                trader.id, date(2026, 2, 1), budget=100.0)
            assert applied == 0.0 and netted == []


# ---------------------------------------------------------------------------
# 1099 readiness dashboard
# ---------------------------------------------------------------------------

class Test1099Readiness:
    def _setup_app(self):
        os.environ['ADMIN_API_KEY'] = 'testkey'
        os.environ.pop('ADMIN_TOTP_SECRET', None)
        from models import db
        from flask import Flask
        from mobile_api import mobile_api
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['TESTING'] = True
        db.init_app(app)
        app.register_blueprint(mobile_api)
        return app, db

    def _payout(self, db, uid, *, amount, status, paid_at=None, period=None):
        from models import XeroPayoutRecord
        from calendar import monthrange
        period = period or date(2026, 6, 1)
        pe = date(period.year, period.month, monthrange(period.year, period.month)[1])
        rec = XeroPayoutRecord(portfolio_user_id=uid, period_start=period, period_end=pe,
                               influencer_payout=amount, bonus_payout=0.0,
                               payment_status=status, paid_at=paid_at)
        db.session.add(rec)

    def test_categorization(self):
        from models import db, User, TaxpayerProfile
        app, db = self._setup_app()
        with app.app_context():
            db.create_all()
            a = User(email="a@x.com", username="creatorA")
            b = User(email="b@x.com", username="creatorB")
            c = User(email="c@x.com", username="creatorC")
            d = User(email="d@x.com", username="creatorD")
            db.session.add_all([a, b, c, d])
            db.session.commit()

            # A: paid $700, no W-9 -> action_required
            self._payout(db, a.id, amount=700.0, status='paid', paid_at=datetime(2026, 6, 30))
            # B: paid $700, W-9 on file -> reportable
            self._payout(db, b.id, amount=700.0, status='paid', paid_at=datetime(2026, 6, 30))
            db.session.add(TaxpayerProfile(user_id=b.id, status='on_file', tin_last4='1234'))
            # C: pending $700, no W-9 -> at_risk
            self._payout(db, c.id, amount=700.0, status='pending')
            # D: paid $100 -> below_threshold
            self._payout(db, d.id, amount=100.0, status='paid', paid_at=datetime(2026, 6, 30))
            db.session.commit()

            client = app.test_client()
            resp = client.get('/api/mobile/admin/tax/1099-readiness?year=2026',
                               headers={'X-Admin-Key': 'testkey'})
            assert resp.status_code == 200, resp.get_data(as_text=True)
            data = resp.get_json()
            assert data['summary']['action_required'] == 1
            assert data['summary']['reportable'] == 1
            assert data['summary']['at_risk'] == 1
            assert data['summary']['below_threshold'] == 1
            cats = {c['username']: c['category'] for c in data['creators']}
            assert cats['creatorA'] == 'action_required'
            assert cats['creatorB'] == 'reportable'
            assert cats['creatorC'] == 'at_risk'
            assert cats['creatorD'] == 'below_threshold'
            assert [c['username'] for c in data['action_required']] == ['creatorA']

    def test_requires_admin_auth(self):
        app, db = self._setup_app()
        with app.app_context():
            db.create_all()
            client = app.test_client()
            resp = client.get('/api/mobile/admin/tax/1099-readiness')
            assert resp.status_code == 403


if __name__ == '__main__':
    if pytest:
        pytest.main([__file__, '-v'])
