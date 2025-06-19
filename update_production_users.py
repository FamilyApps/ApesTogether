import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    """
    This script helps update users in the production environment
    by calling the admin route we'll add to the app.
    """
    # Get the production URL
    production_url = input("Enter the production URL (e.g., https://your-app.vercel.app): ")
    
    # Get admin credentials
    email = input("Enter your admin email: ")
    password = input("Enter your admin password: ")
    
    # Login to get session cookie
    print("Logging in...")
    session = requests.Session()
    login_response = session.post(
        f"{production_url}/login",
        data={"email": email, "password": password}
    )
    
    if login_response.status_code != 200:
        print(f"Login failed with status code {login_response.status_code}")
        return
    
    # Update problematic users
    users_to_update = ['wild-bronco', 'wise-buffalo']
    for username in users_to_update:
        print(f"Updating {username}...")
        update_response = session.post(
            f"{production_url}/admin/update-user/{username}",
            json={"subscription_price": 5.99}
        )
        
        if update_response.status_code == 200:
            print(f"Successfully updated {username}")
        else:
            print(f"Failed to update {username}: {update_response.status_code}")
            print(update_response.text)

if __name__ == "__main__":
    main()
