from app import app, db, User, Subscription, Stock

def check_users():
    print("Checking problematic users...")
    with app.app_context():
        # Check user details
        users = User.query.filter(User.username.in_(['wild-bronco', 'wise-buffalo'])).all()
        print('\nUser details:')
        for u in users:
            print(f'Username: {u.username}, ID: {u.id}, Email: {u.email}')
            print(f'Stripe Price ID: {u.stripe_price_id}, Subscription Price: {u.subscription_price}')
            print(f'Stripe Customer ID: {u.stripe_customer_id}')
            print('-' * 50)
        
        # Check subscriptions
        print('\nSubscriptions:')
        for user in users:
            subs = Subscription.query.filter_by(subscribed_to_id=user.id).all()
            print(f"{user.username} has {len(subs)} subscribers:")
            for sub in subs:
                subscriber = User.query.get(sub.subscriber_id)
                print(f"  - {subscriber.username} (ID: {sub.subscriber_id}, Status: {sub.status})")
            print('-' * 50)
        
        # Check stocks
        print('\nStocks:')
        for user in users:
            stocks = Stock.query.filter_by(user_id=user.id).all()
            print(f"{user.username} has {len(stocks)} stocks:")
            for stock in stocks:
                print(f"  - {stock.ticker}: {stock.quantity} shares @ ${stock.purchase_price}")
            print('-' * 50)

if __name__ == "__main__":
    check_users()
