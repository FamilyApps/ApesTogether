# Stock Portfolio Tracker

A web application that allows users to log in with Apple or Google authentication (with FaceID and Face Unlock support), and manage their stock portfolio by inputting the quantity of shares and ticker symbols for each stock they own.

## Features

- **Secure Authentication**: Sign in with Apple or Google accounts with biometric authentication support (FaceID/Face Unlock)
- **Stock Portfolio Management**: Add stocks to your portfolio by entering ticker symbols and quantities
- **Real-time Data**: View current stock prices and portfolio value using Yahoo Finance data
- **Portfolio Analysis**: Visual breakdown of your portfolio allocation with interactive charts
- **Responsive Design**: Works on desktop and mobile devices

## Technology Stack

- **Backend**: Python with Flask
- **Database**: SQLAlchemy with SQLite
- **Authentication**: OAuth with Authlib (Google and Apple)
- **Stock Data**: Yahoo Finance API (yfinance)
- **Frontend**: HTML, CSS, JavaScript
- **Charts**: Chart.js for data visualization
- **Styling**: Bootstrap 5 for responsive design

## Setup Instructions

1. Clone the repository:
```
git clone <repository-url>
cd stock-portfolio-app
```

2. Create a virtual environment and activate it:
```
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the required dependencies:
```
pip install -r api/requirements.txt
```

4. Set up environment variables (for production):
```
export SECRET_KEY=your_secret_key
export GOOGLE_CLIENT_ID=your_google_client_id
export GOOGLE_CLIENT_SECRET=your_google_client_secret
export APPLE_CLIENT_ID=your_apple_client_id
export APPLE_CLIENT_SECRET=your_apple_client_secret
```

5. Run the application:
```
python app.py
```

6. Open your browser and navigate to `http://localhost:5000`

## OAuth Configuration

### Google OAuth Setup

1. Go to the [Google Developer Console](https://console.developers.google.com/)
2. Create a new project
3. Enable the Google+ API
4. Configure the OAuth consent screen
5. Create OAuth 2.0 credentials
6. Add authorized redirect URIs (e.g., `http://localhost:5000/login/google/authorize`)
7. Copy the Client ID and Client Secret to your environment variables

### Apple OAuth Setup

1. Go to the [Apple Developer Portal](https://developer.apple.com/)
2. Register a new App ID with "Sign In with Apple" capability
3. Create a Services ID for your web app
4. Configure domains and redirect URIs
5. Generate a private key and note the Key ID
6. Set up the necessary environment variables

## Security Notes

- In production, always use HTTPS
- Store API keys and secrets securely using environment variables
- The current implementation uses SQLite for simplicity, but for production, consider using a more robust database like PostgreSQL
- Implement rate limiting for API requests to prevent abuse

## License

This project is licensed under the MIT License - see the LICENSE file for details.
