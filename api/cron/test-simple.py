"""
Minimal test for Vercel Python handler
"""
import json

def handler(request):
    """Minimal Vercel handler test"""
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Simple test works', 'timestamp': '2025-09-23T21:19:00Z'}),
        'headers': {
            'Content-Type': 'application/json'
        }
    }
