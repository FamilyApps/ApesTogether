"""
Market close cron job endpoint for Vercel cron jobs.
Simple redirect to Flask endpoint to avoid code duplication.
"""
import os
import json
import requests

def handler(request):
    """Vercel serverless function handler - redirects to Flask endpoint"""
    try:
        # Get CRON_SECRET token
        token = os.environ.get('CRON_SECRET')
        if not token:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'CRON_SECRET not configured'})
            }
        
        # Call the working Flask endpoint
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://apestogether.ai/api/cron/market-close',
            headers=headers,
            timeout=30
        )
        
        return {
            'statusCode': response.status_code,
            'body': response.text,
            'headers': {
                'Content-Type': 'application/json'
            }
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Market close failed: {str(e)}'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
