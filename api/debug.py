"""
Debug script to help identify issues with the Vercel deployment
"""
import os
import sys
import json

def get_environment_info():
    """Get information about the environment"""
    env_vars = {
        'DATABASE_URL': os.environ.get('DATABASE_URL', 'Not set'),
        'SECRET_KEY': 'Present' if os.environ.get('SECRET_KEY') else 'Not set',
        'VERCEL_ENV': os.environ.get('VERCEL_ENV', 'Not set'),
        'PYTHON_VERSION': sys.version,
        'PYTHONPATH': os.environ.get('PYTHONPATH', 'Not set'),
        'PWD': os.environ.get('PWD', 'Not set')
    }
    
    return env_vars

def handler(event, context):
    """Serverless function handler for debugging"""
    try:
        env_info = get_environment_info()
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Debug information',
                'environment': env_info
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'type': str(type(e))
            })
        }

# For local testing
if __name__ == '__main__':
    print(json.dumps(get_environment_info(), indent=2))
