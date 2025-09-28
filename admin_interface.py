import os
from functools import wraps
from flask import Blueprint, render_template, render_template_string, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc
import stripe
from datetime import datetime
from models import db, User, Stock, Transaction, Subscription
# Removed circular import - get_stock_data will be imported locally when needed

# Admin credentials from environment variables
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')

# Create a Blueprint for the admin routes
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Add DataTables initialization for sortable tables
@admin_bp.after_request
def add_datatables(response):
    """Add DataTables initialization script to appropriate pages"""
    if response.content_type.startswith('text/html'):
        # Only modify HTML responses
        html = response.get_data(as_text=True)
        if 'id="transactionsTable"' in html or 'id="usersTable"' in html:
            # Add DataTables initialization script
            script = '''
            <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/dataTables.bootstrap5.min.css">
            <script type="text/javascript" src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
            <script type="text/javascript" src="https://cdn.datatables.net/1.11.5/js/dataTables.bootstrap5.min.js"></script>
            <script>
                $(document).ready(function() {
                    $('.datatable').DataTable({
                        "order": [[0, "desc"]],
                        "pageLength": 25
                    });
                });
            </script>
            '''
            html = html.replace('</body>', script + '</body>')
            response.set_data(html)
    return response

# Admin authentication check
def admin_required(f):
    """Decorator to check if user is an admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated
        if not current_user.is_authenticated:
            flash('You must be logged in to access this page.', 'danger')
            return redirect(url_for('login'))
            
        # Allow access for admin email regardless of username
        if current_user.email == ADMIN_EMAIL:
            return f(*args, **kwargs)
            
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('index'))
    decorated_function.__name__ = f.__name__
    return decorated_function

# Admin dashboard
@admin_bp.route('/')
@login_required
@admin_required
def admin_dashboard():
    """Admin dashboard showing system overview"""
    # Get counts for dashboard
    user_count = User.query.count()
    stock_count = Stock.query.count()
    transaction_count = Transaction.query.count()
    subscription_count = Subscription.query.count()
    
    # Get recent users
    recent_users = User.query.order_by(desc(User.id)).limit(5).all()
    
    # Get problematic users (missing subscription data)
    problematic_users = User.query.filter(
        (User.subscription_price == None) | 
        (User.stripe_price_id == None)
    ).all()
    
    return render_template(
        'admin/dashboard.html',
        user_count=user_count,
        stock_count=stock_count,
        transaction_count=transaction_count,
        subscription_count=subscription_count,
        recent_users=recent_users,
        problematic_users=problematic_users,
        now=datetime.now()
    )

# User management
@admin_bp.route('/users')
@login_required
@admin_required
def user_list():
    """List all users with portfolio values and trade counts"""
    from sqlalchemy import func, and_
    from datetime import datetime, timedelta
    
    users = User.query.all()
    
    # Calculate summary statistics for all users
    total_portfolio_value = 0
    total_yesterday_trades = 0
    total_subscriptions = Subscription.query.count()
    
    # Calculate additional data for each user
    for user in users:
        # Calculate portfolio value using simple estimation
        user_stocks = Stock.query.filter_by(user_id=user.id).all()
        portfolio_value = 0
        
        for stock in user_stocks:
            try:
                # Import locally to avoid circular import
                from api.index import get_stock_data
                stock_data = get_stock_data(stock.ticker)
                current_price = stock_data.get('price', 150.0)
                portfolio_value += current_price * stock.quantity
            except:
                # Fallback to estimated price
                portfolio_value += 150 * stock.quantity
        
        user.portfolio_value = portfolio_value
        total_portfolio_value += portfolio_value
        
        # Count yesterday's trades
        yesterday = datetime.now().date() - timedelta(days=1)
        yesterday_trades = Transaction.query.filter(
            and_(
                Transaction.user_id == user.id,
                func.date(Transaction.timestamp) == yesterday
            )
        ).count()
        user.yesterday_trades = yesterday_trades
        total_yesterday_trades += yesterday_trades
        
        # Count subscriber count (how many people subscribe to this user's portfolio)
        subscriber_count = Subscription.query.filter_by(subscribed_to_id=user.id).count()
        user.subscriber_count = subscriber_count
    
    return render_template('admin/users.html', 
                         users=users, 
                         total_portfolio_value=total_portfolio_value,
                         total_yesterday_trades=total_yesterday_trades,
                         total_subscriptions=total_subscriptions,
                         now=datetime.now())

@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """View user details"""
    user = User.query.get_or_404(user_id)
    stocks = Stock.query.filter_by(user_id=user.id).all()
    transactions = Transaction.query.filter_by(user_id=user.id).all()
    subscriptions = Subscription.query.filter_by(subscriber_id=user.id).all()
    
    return render_template(
        'admin/user_detail.html',
        user=user,
        stocks=stocks,
        transactions=transactions,
        subscriptions=subscriptions,
        now=datetime.now()
    )

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def user_edit(user_id):
    """Edit user details"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Update basic user info
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        user.subscription_price = float(request.form.get('subscription_price') or 0)
        user.stripe_price_id = request.form.get('stripe_price_id')
        
        try:
            db.session.commit()
            flash('User updated successfully', 'success')
            return redirect(url_for('admin.user_detail', user_id=user.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')
    
    # Get available Stripe prices for the form
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    stripe_prices = []
    try:
        prices = stripe.Price.list(active=True, limit=10)
        for price in prices.data:
            product = stripe.Product.retrieve(price.product)
            stripe_prices.append({
                'id': price.id,
                'product_name': product.name,
                'amount': price.unit_amount / 100,
                'currency': price.currency,
                'interval': price.recurring.interval if price.recurring else None
            })
    except Exception as e:
        flash(f'Error fetching Stripe prices: {str(e)}', 'warning')
    
    return render_template('admin/user_edit.html', user=user, stripe_prices=stripe_prices, now=datetime.now())

# Stock management
@admin_bp.route('/users/<int:user_id>/stocks/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_stock(user_id):
    """Add a stock to user's portfolio"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        ticker = request.form.get('ticker').upper()
        quantity = float(request.form.get('quantity'))
        price = float(request.form.get('price'))
        
        # Check if stock already exists
        existing_stock = Stock.query.filter_by(user_id=user.id, ticker=ticker).first()
        if existing_stock:
            # Update existing stock
            existing_stock.quantity += quantity
            # Create a transaction record
            transaction = Transaction(
                user_id=user.id,
                ticker=ticker,
                quantity=quantity,
                price=price,
                transaction_type='buy',
                timestamp=datetime.now()
            )
            db.session.add(transaction)
        else:
            # Create new stock
            stock = Stock(
                user_id=user.id,
                ticker=ticker,
                quantity=quantity
            )
            # Create a transaction record
            transaction = Transaction(
                user_id=user.id,
                ticker=ticker,
                quantity=quantity,
                price=price,
                transaction_type='buy',
                timestamp=datetime.now()
            )
            db.session.add(stock)
            db.session.add(transaction)
        
        try:
            db.session.commit()
            flash(f'Added {quantity} shares of {ticker} at ${price}/share', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding stock: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/add_stock.html', user=user, now=datetime.now())

@admin_bp.route('/users/<int:user_id>/transactions/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_transaction(user_id):
    """Add a manual transaction with custom date and price"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        ticker = request.form.get('ticker').upper()
        quantity = float(request.form.get('quantity'))
        price = float(request.form.get('price'))
        transaction_type = request.form.get('transaction_type')
        date_str = request.form.get('transaction_date')
        # notes = request.form.get('notes', '')  # Notes column doesn't exist in database
        
        # Parse the date string to a datetime object
        try:
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD', 'danger')
            return render_template('admin/add_transaction.html', user=user, now=datetime.now())
        
        # Create the transaction record
        transaction = Transaction(
            user_id=user.id,
            ticker=ticker,
            quantity=quantity,
            price=price,
            transaction_type=transaction_type,
            timestamp=transaction_date,
            # notes=notes  # Notes column doesn't exist in database
        )
        
        # Update the stock position
        existing_stock = Stock.query.filter_by(user_id=user.id, ticker=ticker).first()
        
        if transaction_type == 'buy':
            if existing_stock:
                existing_stock.quantity += quantity
            else:
                stock = Stock(
                    user_id=user.id,
                    ticker=ticker,
                    quantity=quantity
                )
                db.session.add(stock)
        elif transaction_type == 'sell':
            if not existing_stock or existing_stock.quantity < quantity:
                flash(f'Cannot sell {quantity} shares of {ticker}. User only has {existing_stock.quantity if existing_stock else 0} shares.', 'danger')
                return render_template('admin/add_transaction.html', user=user, now=datetime.now())
            
            existing_stock.quantity -= quantity
            
            # If shares become zero, optionally remove the stock
            if existing_stock.quantity <= 0:
                db.session.delete(existing_stock)
        
        db.session.add(transaction)
        
        try:
            db.session.commit()
            flash(f'Added {transaction_type} transaction of {quantity} shares of {ticker} at ${price}/share on {date_str}', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding transaction: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/add_transaction.html', user=user, now=datetime.now())


@admin_bp.route('/users/<int:user_id>/transactions/<int:transaction_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_transaction(user_id, transaction_id):
    """Edit an existing transaction with custom date and price"""
    user = User.query.get_or_404(user_id)
    transaction = Transaction.query.get_or_404(transaction_id)
    
    # Verify the transaction belongs to the user
    if transaction.user_id != user.id:
        flash('Transaction does not belong to this user', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    if request.method == 'POST':
        # Store original values to calculate position changes
        original_ticker = transaction.ticker
        original_quantity = transaction.quantity
        original_type = transaction.transaction_type
        
        # Get form data
        quantity = float(request.form.get('quantity'))
        price = float(request.form.get('price'))
        date_str = request.form.get('transaction_date')
        # notes = request.form.get('notes', '')  # Notes column doesn't exist in database
        
        # Parse the date
        try:
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD', 'danger')
            return render_template('admin/edit_transaction.html', user=user, transaction=transaction, now=datetime.now())
        
        # Update transaction record
        transaction.quantity = quantity
        transaction.price = price
        transaction.timestamp = transaction_date
        # transaction.notes = notes  # Notes column doesn't exist in database
        
        # Update stock position if quantity changed
        if quantity != original_quantity:
            stock = Stock.query.filter_by(user_id=user.id, ticker=original_ticker).first()
            
            if original_type == 'buy':
                # Reverse the original buy
                stock.quantity -= original_quantity
                # Apply the new buy
                stock.quantity += quantity
            elif original_type == 'sell':
                # Reverse the original sell
                stock.quantity += original_quantity
                # Apply the new sell
                stock.quantity -= quantity
            
            # Check if stock should be removed
            if stock.quantity <= 0:
                db.session.delete(stock)
        
        try:
            db.session.commit()
            flash(f'Transaction updated successfully', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating transaction: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/edit_transaction.html', user=user, transaction=transaction, now=datetime.now())


@admin_bp.route('/users/<int:user_id>/transactions/<int:transaction_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_transaction(user_id, transaction_id):
    """Delete a transaction and update stock position"""
    user = User.query.get_or_404(user_id)
    transaction = Transaction.query.get_or_404(transaction_id)
    
    # Verify the transaction belongs to the user
    if transaction.user_id != user.id:
        flash('Transaction does not belong to this user', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    # Update stock position
    stock = Stock.query.filter_by(user_id=user.id, ticker=transaction.ticker).first()
    
    if transaction.transaction_type == 'buy':
        # Reverse the buy
        if stock:
            stock.quantity -= transaction.quantity
            # If quantity becomes zero or negative, remove the stock
            if stock.quantity <= 0:
                db.session.delete(stock)
    elif transaction.transaction_type == 'sell':
        # Reverse the sell
        if stock:
            stock.quantity += transaction.quantity
        else:
            # Create a new stock position if it was fully sold before
            new_stock = Stock(
                user_id=user.id,
                ticker=transaction.ticker,
                quantity=transaction.quantity
            )
            db.session.add(new_stock)
    
    # Delete the transaction
    db.session.delete(transaction)
    
    try:
        db.session.commit()
        flash(f'Transaction deleted and stock position updated', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting transaction: {str(e)}', 'danger')
    
    return redirect(url_for('admin.user_detail', user_id=user.id))

@admin_bp.route('/users/<int:user_id>/stocks/<int:stock_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_stock(user_id, stock_id):
    """Edit a stock in user's portfolio"""
    user = User.query.get_or_404(user_id)
    stock = Stock.query.get_or_404(stock_id)
    
    if stock.user_id != user.id:
        flash('Stock does not belong to this user', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    if request.method == 'POST':
        old_quantity = stock.quantity
        new_quantity = float(request.form.get('quantity'))
        price = float(request.form.get('price'))
        
        # Update stock quantity
        stock.quantity = new_quantity
        
        # Create a transaction record for the adjustment
        quantity_diff = new_quantity - old_quantity
        if quantity_diff != 0:
            transaction_type = 'buy' if quantity_diff > 0 else 'sell'
            transaction = Transaction(
                user_id=user.id,
                ticker=stock.ticker,
                quantity=abs(quantity_diff),
                price=price,
                transaction_type=transaction_type,
                timestamp=datetime.now()
            )
            db.session.add(transaction)
        
        try:
            db.session.commit()
            flash(f'Updated {stock.ticker} to {new_quantity} shares', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating stock: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/edit_stock.html', user=user, stock=stock, now=datetime.now())

@admin_bp.route('/fix-subscription-prices', methods=['GET', 'POST'])
@login_required
@admin_required
def fix_subscription_prices():
    """Fix missing subscription prices for users via web interface"""
    if request.method == 'POST':
        # Find users without subscription prices
        users_without_prices = User.query.filter(
            (User.subscription_price == None) | (User.stripe_price_id == None)
        ).all()
        
        updated_count = 0
        for user in users_without_prices:
            if user.subscription_price is None:
                user.subscription_price = 4.00
                updated_count += 1
                
            if user.stripe_price_id is None:
                user.stripe_price_id = 'price_1RbX0yQWUhVa3vgDB8vGzoFN'  # Default $4 price
        
        try:
            db.session.commit()
            flash(f'Successfully updated {updated_count} users with default $4.00 subscription pricing.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating users: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_list'))
    
    # GET request - show users that need fixing
    users_without_prices = User.query.filter(
        (User.subscription_price == None) | (User.stripe_price_id == None)
    ).all()
    
    return render_template_string("""
    {% extends 'base.html' %}
    {% block title %}Fix Subscription Prices{% endblock %}
    {% block content %}
    <div class="container mt-4">
        <h1>Fix Subscription Prices</h1>
        
        {% if users_without_prices %}
        <div class="alert alert-warning">
            <h5>Found {{ users_without_prices|length }} users without subscription pricing:</h5>
            <ul>
            {% for user in users_without_prices %}
                <li><strong>{{ user.username }}</strong> - 
                    Price: {{ user.subscription_price or 'Not Set' }}, 
                    Stripe ID: {{ user.stripe_price_id or 'Not Set' }}
                </li>
            {% endfor %}
            </ul>
        </div>
        
        <form method="post">
            <button type="submit" class="btn btn-primary">Fix All Users ($4.00 default)</button>
            <a href="{{ url_for('admin.user_list') }}" class="btn btn-secondary">Cancel</a>
        </form>
        {% else %}
        <div class="alert alert-success">
            <h5>All users have subscription pricing configured!</h5>
        </div>
        <a href="{{ url_for('admin.user_list') }}" class="btn btn-primary">Back to Users</a>
        {% endif %}
    </div>
    {% endblock %}
    """, users_without_prices=users_without_prices, now=datetime.now())

@admin_bp.route('/users/<int:user_id>/stocks/<int:stock_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_stock(user_id, stock_id):
    """Delete a stock from user's portfolio"""
    user = User.query.get_or_404(user_id)
    stock = Stock.query.get_or_404(stock_id)
    
    if stock.user_id != user.id:
        flash('Stock does not belong to this user', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    try:
        # Create a sell transaction record
        transaction = Transaction(
            user_id=user.id,
            ticker=stock.ticker,
            quantity=stock.quantity,
            price=0,  # Admin deletion doesn't have a price
            transaction_type='sell',
            timestamp=datetime.now()
        )
        db.session.add(transaction)
        
        # Delete the stock
        db.session.delete(stock)
        db.session.commit()
        flash(f'Deleted {stock.ticker} from portfolio', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting stock: {str(e)}', 'danger')
    
    return redirect(url_for('admin.user_detail', user_id=user.id))

# API endpoints for AJAX operations
@admin_bp.route('/api/update-user-subscription', methods=['POST'])
@login_required
@admin_required
def update_user_subscription():
    """API endpoint to update user subscription data"""
    data = request.json
    user_id = data.get('user_id')
    subscription_price = data.get('subscription_price')
    stripe_price_id = data.get('stripe_price_id')
    
    if not user_id or not subscription_price or not stripe_price_id:
        return jsonify({'error': 'Missing required fields'}), 400
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        # Verify the price ID exists in Stripe
        stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
        price = stripe.Price.retrieve(stripe_price_id)
        
        # Update user
        user.subscription_price = float(subscription_price)
        user.stripe_price_id = stripe_price_id
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Updated {user.username} with price ${subscription_price} and price ID {stripe_price_id}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/comprehensive-leaderboard-fix')
@login_required
@admin_required
def comprehensive_leaderboard_fix():
    """Comprehensive leaderboard diagnosis and fix - addresses the core data population issues"""
    try:
        # Import and run the fix script
        from comprehensive_leaderboard_fix import run_fix_and_return_json
        
        current_app.logger.info("Starting comprehensive leaderboard fix via admin interface...")
        
        # Run the fix and get results
        result = run_fix_and_return_json()
        
        current_app.logger.info(f"Comprehensive leaderboard fix completed. Success: {result['success']}")
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error in comprehensive leaderboard fix: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to run comprehensive leaderboard fix'
        }), 500

@admin_bp.route('/debug-performance-calculations')
@login_required
@admin_required
def debug_performance_calculations():
    """Debug why performance calculations are broken (1D no data, 5D returns 0%)"""
    try:
        from datetime import datetime, date, timedelta
        from models import db, User, PortfolioSnapshot, PortfolioSnapshotIntraday, MarketData
        from portfolio_performance import PortfolioPerformanceCalculator
        from sqlalchemy import func, and_
        
        current_app.logger.info("Starting performance calculation debug...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_user': {},
            'snapshot_data': {},
            'market_data': {},
            'calculation_tests': {},
            'detailed_analysis': {}
        }
        
        # Get a test user
        test_user = User.query.join(User.stocks).distinct().first()
        if not test_user:
            return jsonify({
                'success': False,
                'error': 'No users with stocks found',
                'results': results
            }), 400
        
        results['test_user'] = {
            'id': test_user.id,
            'username': test_user.username
        }
        
        # Check portfolio snapshots
        today = date.today()
        yesterday = today - timedelta(days=1)
        five_days_ago = today - timedelta(days=5)
        
        # Check regular snapshots
        total_snapshots = PortfolioSnapshot.query.filter_by(user_id=test_user.id).count()
        recent_snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == test_user.id,
                PortfolioSnapshot.date >= five_days_ago
            )
        ).order_by(PortfolioSnapshot.date.desc()).all()
        
        # Check intraday snapshots
        intraday_count = PortfolioSnapshotIntraday.query.filter(
            and_(
                PortfolioSnapshotIntraday.user_id == test_user.id,
                func.date(PortfolioSnapshotIntraday.timestamp) == today
            )
        ).count()
        
        results['snapshot_data'] = {
            'total_snapshots': total_snapshots,
            'recent_snapshots_count': len(recent_snapshots),
            'recent_snapshots': [
                {'date': s.date.isoformat(), 'value': float(s.total_value)}
                for s in recent_snapshots[:5]
            ],
            'intraday_snapshots_today': intraday_count
        }
        
        # Check S&P 500 data
        sp500_daily = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_SP500',
                MarketData.date >= five_days_ago
            )
        ).order_by(MarketData.date.desc()).all()
        
        sp500_intraday = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date == today
            )
        ).count()
        
        results['market_data'] = {
            'sp500_daily_count': len(sp500_daily),
            'sp500_daily': [
                {'date': d.date.isoformat(), 'price': float(d.close_price)}
                for d in sp500_daily[:5]
            ],
            'sp500_intraday_today': sp500_intraday
        }
        
        # Test performance calculations
        calculator = PortfolioPerformanceCalculator()
        
        for period in ['1D', '5D']:
            try:
                perf_data = calculator.get_performance_data(test_user.id, period)
                
                portfolio_return = perf_data.get('portfolio_return')
                sp500_return = perf_data.get('sp500_return')
                chart_data = perf_data.get('chart_data', [])
                
                test_result = {
                    'portfolio_return': portfolio_return,
                    'sp500_return': sp500_return,
                    'chart_data_points': len(chart_data),
                    'first_point': chart_data[0] if chart_data else None,
                    'last_point': chart_data[-1] if chart_data else None,
                    'issues': []
                }
                
                # Check for specific issues
                if period == '1D' and len(chart_data) == 0:
                    test_result['issues'].append('1D ISSUE: No chart data - likely missing intraday snapshots')
                
                if period == '5D' and portfolio_return == 0.0 and len(chart_data) > 0:
                    test_result['issues'].append('5D ISSUE: 0% return despite chart data - calculation problem')
                
                results['calculation_tests'][period] = test_result
                
            except Exception as e:
                results['calculation_tests'][period] = {
                    'error': str(e)
                }
        
        # Detailed analysis for 5D
        try:
            start_date = today - timedelta(days=5)
            end_date = today
            
            dietz_return = calculator.calculate_modified_dietz_return(test_user.id, start_date, end_date)
            
            # Check snapshots in period
            period_snapshots = PortfolioSnapshot.query.filter(
                and_(
                    PortfolioSnapshot.user_id == test_user.id,
                    PortfolioSnapshot.date >= start_date,
                    PortfolioSnapshot.date <= end_date
                )
            ).order_by(PortfolioSnapshot.date).all()
            
            simple_return = None
            if len(period_snapshots) >= 2:
                start_value = period_snapshots[0].total_value
                end_value = period_snapshots[-1].total_value
                simple_return = ((end_value - start_value) / start_value) * 100
            
            sp500_return = calculator.calculate_sp500_return(start_date, end_date)
            
            results['detailed_analysis'] = {
                'modified_dietz_return': float(dietz_return * 100),
                'snapshots_in_period': len(period_snapshots),
                'simple_return_check': float(simple_return) if simple_return else None,
                'sp500_return': float(sp500_return * 100),
                'period_snapshots': [
                    {'date': s.date.isoformat(), 'value': float(s.total_value)}
                    for s in period_snapshots
                ]
            }
            
        except Exception as e:
            results['detailed_analysis'] = {
                'error': str(e)
            }
        
        current_app.logger.info("Performance calculation debug completed")
        
        return jsonify({
            'success': True,
            'message': 'Performance calculation debug completed',
            'results': results
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in performance calculation debug: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to run performance calculation debug'
        }), 500

@admin_bp.route('/fix-leaderboard-to-use-cache')
@login_required
@admin_required
def fix_leaderboard_to_use_cache():
    """Fix leaderboard to use cached chart data instead of broken live calculations"""
    try:
        from datetime import datetime, date, timedelta
        from models import db, User, UserPortfolioChartCache, LeaderboardCache, LeaderboardEntry
        from sqlalchemy import inspect
        import json
        
        current_app.logger.info("Starting leaderboard cache fix...")
        
        # First, check the actual database schema for LeaderboardEntry
        inspector = inspect(db.engine)
        leaderboard_columns = [col['name'] for col in inspector.get_columns('leaderboard_entry')]
        current_app.logger.info(f"Actual LeaderboardEntry columns: {leaderboard_columns}")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'database_columns': leaderboard_columns,
            'cache_status': {},
            'generated_leaderboards': {},
            'verification': {}
        }
        
        # Check cached chart data availability
        users_with_stocks = User.query.join(User.stocks).distinct().all()
        results['users_with_stocks'] = len(users_with_stocks)
        
        cache_status = {}
        for period in ['1D', '5D', '1M', '3M', 'YTD', '1Y']:
            cached_users = UserPortfolioChartCache.query.filter_by(period=period).count()
            cache_status[period] = cached_users
        
        results['cache_status'] = cache_status
        
        # Generate leaderboard data from cached charts
        successful_periods = []
        
        for period in ['1D', '5D']:  # Start with critical periods
            # Get all users with cached chart data for this period
            cached_charts = UserPortfolioChartCache.query.filter_by(period=period).all()
            
            if not cached_charts:
                results['generated_leaderboards'][period] = {
                    'success': False,
                    'error': 'No cached chart data available'
                }
                continue
            
            leaderboard_entries = []
            
            for chart_cache in cached_charts:
                try:
                    # Parse the cached Chart.js data
                    chart_data = json.loads(chart_cache.chart_data)
                    datasets = chart_data.get('datasets', [])
                    
                    if len(datasets) < 1:
                        continue
                    
                    # Get portfolio performance data
                    portfolio_data = datasets[0].get('data', [])
                    if not portfolio_data or len(portfolio_data) < 2:
                        continue
                    
                    # Calculate performance from first to last data point
                    start_value = portfolio_data[0]
                    end_value = portfolio_data[-1]
                    
                    if start_value > 0:
                        performance_percent = ((end_value - start_value) / start_value) * 100
                    else:
                        performance_percent = 0.0
                    
                    # Get user info
                    user = User.query.get(chart_cache.user_id)
                    if not user:
                        continue
                    
                    leaderboard_entries.append({
                        'user_id': user.id,
                        'username': user.username,
                        'performance_percent': performance_percent,
                        'portfolio_value': float(end_value),
                        'small_cap_percent': 50.0,  # Default for now
                        'large_cap_percent': 50.0,   # Default for now
                        'avg_trades_per_week': 5.0   # Default for now
                    })
                    
                except Exception as e:
                    current_app.logger.warning(f"Failed to process cache for user {chart_cache.user_id}: {str(e)}")
                    continue
            
            # Sort by performance
            leaderboard_entries.sort(key=lambda x: x['performance_percent'], reverse=True)
            
            results['generated_leaderboards'][period] = {
                'success': True,
                'entries_count': len(leaderboard_entries),
                'top_3': leaderboard_entries[:3] if leaderboard_entries else []
            }
            
            if len(leaderboard_entries) > 0:
                try:
                    # Clear existing cache
                    LeaderboardCache.query.filter_by(period=period).delete()
                    
                    # Create new cache entry
                    cache_entry = LeaderboardCache(
                        period=period,
                        leaderboard_data=json.dumps(leaderboard_entries),
                        generated_at=datetime.now()
                    )
                    db.session.add(cache_entry)
                    
                    # Update individual LeaderboardEntry records
                    LeaderboardEntry.query.filter_by(period=period).delete()
                    
                    # Use raw SQL to handle schema mismatch (database has 'date' column not in model)
                    today_date = date.today()
                    
                    for entry_data in leaderboard_entries:
                        # Use raw SQL INSERT to handle the 'date' column that exists in DB but not model
                        db.session.execute(
                            """INSERT INTO leaderboard_entry 
                               (user_id, period, performance_percent, small_cap_percent, large_cap_percent, 
                                avg_trades_per_week, portfolio_value, calculated_at, date) 
                               VALUES (:user_id, :period, :performance_percent, :small_cap_percent, 
                                       :large_cap_percent, :avg_trades_per_week, :portfolio_value, :calculated_at, :date)""",
                            {
                                'user_id': entry_data['user_id'],
                                'period': period,
                                'performance_percent': entry_data['performance_percent'],
                                'small_cap_percent': entry_data['small_cap_percent'],
                                'large_cap_percent': entry_data['large_cap_percent'],
                                'avg_trades_per_week': entry_data['avg_trades_per_week'],
                                'portfolio_value': entry_data['portfolio_value'],
                                'calculated_at': datetime.now(),
                                'date': today_date
                            }
                        )
                    
                    db.session.commit()
                    successful_periods.append(period)
                    
                except Exception as e:
                    db.session.rollback()
                    results['generated_leaderboards'][period]['cache_update_error'] = str(e)
        
        # Verify the fix
        for period in successful_periods:
            cache_entry = LeaderboardCache.query.filter_by(period=period).first()
            entry_count = LeaderboardEntry.query.filter_by(period=period).count()
            
            verification_data = {
                'cache_entries': 0,
                'db_entries': entry_count,
                'top_performer': None
            }
            
            if cache_entry:
                try:
                    cache_data = json.loads(cache_entry.leaderboard_data)
                    verification_data['cache_entries'] = len(cache_data)
                    if cache_data:
                        verification_data['top_performer'] = {
                            'username': cache_data[0]['username'],
                            'performance_percent': cache_data[0]['performance_percent']
                        }
                except:
                    pass
            
            results['verification'][period] = verification_data
        
        success = len(successful_periods) > 0
        
        current_app.logger.info(f"Leaderboard cache fix completed. Success: {success}, Periods: {successful_periods}")
        
        return jsonify({
            'success': success,
            'message': f'Fixed leaderboards for periods: {successful_periods}' if success else 'No periods were successfully fixed',
            'results': results,
            'successful_periods': successful_periods
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in leaderboard cache fix: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to run leaderboard cache fix'
        }), 500

# Register the blueprint in your app.py
# Add this line to app.py:
# from admin_interface import admin_bp
# app.register_blueprint(admin_bp)
