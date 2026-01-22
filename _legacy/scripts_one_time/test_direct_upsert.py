"""
Direct database test - bypass all Flask-SQLAlchemy session issues
Add this route to api/index.py temporarily
"""

@app.route('/admin/test-direct-upsert')
@login_required
def test_direct_upsert():
    """Test UPSERT directly with raw connection"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from sqlalchemy import text
        import json
        from datetime import datetime
        
        # Get user 5
        user_id = 5
        period = '1M'
        test_data = {'test': 'direct_upsert', 'timestamp': datetime.now().isoformat()}
        
        results = {'steps': []}
        
        # STEP 1: Check if constraint exists
        with db.engine.connect() as conn:
            constraint_check = conn.execute(text("""
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = 'user_portfolio_chart_cache'
                  AND con.contype = 'u'
            """))
            constraints = [row[0] for row in constraint_check.fetchall()]
            results['steps'].append({
                'step': 'Check constraints',
                'constraints': constraints
            })
        
        # STEP 2: Try UPSERT with explicit transaction
        with db.engine.begin() as conn:  # begin() auto-commits on exit
            # Try to upsert
            upsert_sql = text("""
                INSERT INTO user_portfolio_chart_cache (user_id, period, chart_data, generated_at)
                VALUES (:user_id, :period, :chart_data, :generated_at)
                ON CONFLICT (user_id, period)
                DO UPDATE SET
                    chart_data = EXCLUDED.chart_data,
                    generated_at = EXCLUDED.generated_at
                RETURNING id, user_id, period, generated_at
            """)
            
            result = conn.execute(upsert_sql, {
                'user_id': user_id,
                'period': period,
                'chart_data': json.dumps(test_data),
                'generated_at': datetime.now()
            })
            
            row = result.fetchone()
            results['steps'].append({
                'step': 'UPSERT executed',
                'returned': {
                    'id': row[0],
                    'user_id': row[1],
                    'period': row[2],
                    'generated_at': row[3].isoformat() if row[3] else None
                }
            })
        
        # STEP 3: Query back from PRIMARY to verify
        with db.engine.connect() as conn:
            verify_sql = text("""
                SELECT chart_data, generated_at
                FROM user_portfolio_chart_cache
                WHERE user_id = :user_id AND period = :period
            """)
            result = conn.execute(verify_sql, {'user_id': user_id, 'period': period})
            row = result.fetchone()
            
            if row:
                data = json.loads(row[0])
                results['steps'].append({
                    'step': 'Verify query',
                    'found': True,
                    'data': data,
                    'generated_at': row[1].isoformat() if row[1] else None
                })
            else:
                results['steps'].append({
                    'step': 'Verify query',
                    'found': False
                })
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
