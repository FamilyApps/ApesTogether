from app import app, db, User, Subscription, Stock

def list_users():
    print("Listing all users in the database...")
    with app.app_context():
        users = User.query.all()
        print(f"\nTotal users: {len(users)}")
        
        print('\nUser details:')
        for u in users:
            print(f'Username: {u.username}, ID: {u.id}, Email: {u.email}')
            print(f'Stripe Price ID: {u.stripe_price_id}, Subscription Price: {u.subscription_price}')
            print(f'Stripe Customer ID: {u.stripe_customer_id}')
            print('-' * 50)

if __name__ == "__main__":
    list_users()
