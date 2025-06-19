import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import desc
import stripe
from datetime import datetime
from app import db, User, Stock, Transaction, Subscription

# Create a Blueprint for the admin routes
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Admin authentication check
def admin_required(f):
    """Decorator to check if user is an admin"""
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.email != 'fordutilityapps@gmail.com':
            flash('You must be an admin to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
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
