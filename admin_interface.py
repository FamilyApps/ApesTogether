import os
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc
import stripe
from datetime import datetime
from models import db, User, Stock, Transaction, Subscription

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
        problematic_users=problematic_users
    )

# User management
@admin_bp.route('/users')
@login_required
@admin_required
def user_list():
    """List all users"""
    users = User.query.all()
    return render_template('admin/users.html', users=users)

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
        subscriptions=subscriptions
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
    
    return render_template('admin/user_edit.html', user=user, stripe_prices=stripe_prices)

# Stock management
@admin_bp.route('/users/<int:user_id>/stocks/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_stock(user_id):
    """Add a stock to user's portfolio"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        symbol = request.form.get('symbol').upper()
        shares = float(request.form.get('shares'))
        price = float(request.form.get('price'))
        
        # Check if stock already exists
        existing_stock = Stock.query.filter_by(user_id=user.id, symbol=symbol).first()
        if existing_stock:
            # Update existing stock
            existing_stock.shares += shares
            # Create a transaction record
            transaction = Transaction(
                user_id=user.id,
                symbol=symbol,
                shares=shares,
                price=price,
                transaction_type='buy',
                date=datetime.now()
            )
            db.session.add(transaction)
        else:
            # Create new stock
            stock = Stock(
                user_id=user.id,
                symbol=symbol,
                shares=shares
            )
            # Create a transaction record
            transaction = Transaction(
                user_id=user.id,
                symbol=symbol,
                shares=shares,
                price=price,
                transaction_type='buy',
                date=datetime.now()
            )
            db.session.add(stock)
            db.session.add(transaction)
        
        try:
            db.session.commit()
            flash(f'Added {shares} shares of {symbol} at ${price}/share', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding stock: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/add_stock.html', user=user)

@admin_bp.route('/users/<int:user_id>/transactions/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_transaction(user_id):
    """Add a manual transaction with custom date and price"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        symbol = request.form.get('symbol').upper()
        shares = float(request.form.get('shares'))
        price = float(request.form.get('price'))
        transaction_type = request.form.get('transaction_type')
        date_str = request.form.get('transaction_date')
        notes = request.form.get('notes', '')
        
        # Parse the date string to a datetime object
        try:
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD', 'danger')
            return render_template('admin/add_transaction.html', user=user)
        
        # Create the transaction record
        transaction = Transaction(
            user_id=user.id,
            symbol=symbol,
            shares=shares,
            price=price,
            transaction_type=transaction_type,
            date=transaction_date,
            notes=notes
        )
        
        # Update the stock position
        existing_stock = Stock.query.filter_by(user_id=user.id, symbol=symbol).first()
        
        if transaction_type == 'buy':
            if existing_stock:
                existing_stock.shares += shares
            else:
                stock = Stock(
                    user_id=user.id,
                    symbol=symbol,
                    shares=shares
                )
                db.session.add(stock)
        elif transaction_type == 'sell':
            if not existing_stock or existing_stock.shares < shares:
                flash(f'Cannot sell {shares} shares of {symbol}. User only has {existing_stock.shares if existing_stock else 0} shares.', 'danger')
                return render_template('admin/add_transaction.html', user=user)
            
            existing_stock.shares -= shares
            
            # If shares become zero, optionally remove the stock
            if existing_stock.shares <= 0:
                db.session.delete(existing_stock)
        
        db.session.add(transaction)
        
        try:
            db.session.commit()
            flash(f'Added {transaction_type} transaction of {shares} shares of {symbol} at ${price}/share on {date_str}', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding transaction: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/add_transaction.html', user=user)


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
        original_symbol = transaction.symbol
        original_shares = transaction.shares
        original_type = transaction.transaction_type
        
        # Get form data
        shares = float(request.form.get('shares'))
        price = float(request.form.get('price'))
        date_str = request.form.get('transaction_date')
        notes = request.form.get('notes', '')
        
        # Parse the date
        try:
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD', 'danger')
            return render_template('admin/edit_transaction.html', user=user, transaction=transaction)
        
        # Update transaction record
        transaction.shares = shares
        transaction.price = price
        transaction.date = transaction_date
        transaction.notes = notes
        
        # Update stock position if shares changed
        if shares != original_shares:
            stock = Stock.query.filter_by(user_id=user.id, symbol=original_symbol).first()
            
            if original_type == 'buy':
                # Reverse the original buy
                stock.shares -= original_shares
                # Apply the new buy
                stock.shares += shares
            elif original_type == 'sell':
                # Reverse the original sell
                stock.shares += original_shares
                # Apply the new sell
                stock.shares -= shares
            
            # Check if stock should be removed
            if stock.shares <= 0:
                db.session.delete(stock)
        
        try:
            db.session.commit()
            flash(f'Transaction updated successfully', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating transaction: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/edit_transaction.html', user=user, transaction=transaction)


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
    stock = Stock.query.filter_by(user_id=user.id, symbol=transaction.symbol).first()
    
    if transaction.transaction_type == 'buy':
        # Reverse the buy
        if stock:
            stock.shares -= transaction.shares
            # If shares become zero or negative, remove the stock
            if stock.shares <= 0:
                db.session.delete(stock)
    elif transaction.transaction_type == 'sell':
        # Reverse the sell
        if stock:
            stock.shares += transaction.shares
        else:
            # Create a new stock position if it was fully sold before
            new_stock = Stock(
                user_id=user.id,
                symbol=transaction.symbol,
                shares=transaction.shares
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
        old_shares = stock.shares
        new_shares = float(request.form.get('shares'))
        price = float(request.form.get('price'))
        
        # Update stock shares
        stock.shares = new_shares
        
        # Create a transaction record for the adjustment
        shares_diff = new_shares - old_shares
        if shares_diff != 0:
            transaction_type = 'buy' if shares_diff > 0 else 'sell'
            transaction = Transaction(
                user_id=user.id,
                symbol=stock.symbol,
                shares=abs(shares_diff),
                price=price,
                transaction_type=transaction_type,
                date=datetime.now()
            )
            db.session.add(transaction)
        
        try:
            db.session.commit()
            flash(f'Updated {stock.symbol} to {new_shares} shares', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating stock: {str(e)}', 'danger')
        
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/edit_stock.html', user=user, stock=stock)

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
            symbol=stock.symbol,
            shares=stock.shares,
            price=0,  # Admin deletion doesn't have a price
            transaction_type='sell',
            date=datetime.now()
        )
        db.session.add(transaction)
        
        # Delete the stock
        db.session.delete(stock)
        db.session.commit()
        flash(f'Deleted {stock.symbol} from portfolio', 'success')
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

# Register the blueprint in your app.py
# Add this line to app.py:
# from admin_interface import admin_bp
# app.register_blueprint(admin_bp)
