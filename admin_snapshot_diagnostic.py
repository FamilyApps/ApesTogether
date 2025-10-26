"""
Admin route to diagnose max_cash_deployed tracking in snapshots
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required
from models import PortfolioSnapshot, User
from datetime import date

diagnostic_bp = Blueprint('snapshot_diagnostic', __name__)

ADMIN_EMAIL = "catalystcatalyst101@gmail.com"


@diagnostic_bp.route('/admin/diagnose-max-cash-deployed')
@login_required
def diagnose_max_cash_deployed():
    """
    Check if max_cash_deployed is being properly tracked in snapshots.
    
    Usage: /admin/diagnose-max-cash-deployed?username=witty-raven
    """
    from flask import session
    email = session.get('email', '')
    if email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        username = request.args.get('username', 'witty-raven')
        
        # Get user
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': f'User {username} not found'}), 404
        
        # Get YTD snapshots
        start_date = date(2025, 1, 1)
        end_date = date.today()
        
        snapshots = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.user_id == user.id,
            PortfolioSnapshot.date >= start_date,
            PortfolioSnapshot.date <= end_date
        ).order_by(PortfolioSnapshot.date.asc()).all()
        
        if not snapshots:
            return jsonify({'error': 'No snapshots found'}), 404
        
        # Analyze max_cash_deployed changes
        first = snapshots[0]
        last = snapshots[-1]
        
        changes = []
        prev_deployed = first.max_cash_deployed
        
        for snapshot in snapshots:
            if snapshot.max_cash_deployed != prev_deployed:
                changes.append({
                    'date': snapshot.date.isoformat(),
                    'old_deployed': prev_deployed,
                    'new_deployed': snapshot.max_cash_deployed,
                    'change': snapshot.max_cash_deployed - prev_deployed,
                    'total_value': snapshot.total_value,
                    'stock_value': snapshot.stock_value,
                    'cash_proceeds': snapshot.cash_proceeds
                })
                prev_deployed = snapshot.max_cash_deployed
        
        # Sample snapshots
        sample_snapshots = []
        indices = [0, len(snapshots)//4, len(snapshots)//2, 3*len(snapshots)//4, -1]
        for i in indices:
            s = snapshots[i]
            sample_snapshots.append({
                'date': s.date.isoformat(),
                'total_value': s.total_value,
                'stock_value': s.stock_value,
                'cash_proceeds': s.cash_proceeds,
                'max_cash_deployed': s.max_cash_deployed
            })
        
        return jsonify({
            'success': True,
            'user': username,
            'period': f'{start_date} to {end_date}',
            'summary': {
                'total_snapshots': len(snapshots),
                'first_deployed': first.max_cash_deployed,
                'last_deployed': last.max_cash_deployed,
                'net_change': last.max_cash_deployed - first.max_cash_deployed,
                'changes_count': len(changes)
            },
            'deployed_changes': changes,
            'sample_snapshots': sample_snapshots,
            'diagnosis': {
                'issue': 'max_cash_deployed not changing' if len(changes) == 0 else 'max_cash_deployed is being tracked',
                'impact': (
                    'Modified Dietz collapses to simple % when CF_net = 0'
                    if len(changes) == 0
                    else 'Modified Dietz should account for capital deployment timing'
                ),
                'question': 'Is this a paper trading app where users start with virtual cash and never add more?'
            }
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
