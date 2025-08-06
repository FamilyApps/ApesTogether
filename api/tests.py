import os
import unittest
import tempfile
from index import app, db, User

class StockPortfolioTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, app.config['DATABASE'] = tempfile.mkstemp()
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            
    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(app.config['DATABASE'])
        
    def test_empty_db(self):
        """Ensure database starts empty."""
        with app.app_context():
            user_count = User.query.count()
            self.assertEqual(user_count, 0)
            
    def test_register_and_login(self):
        """Test user registration and login."""
        # Register a new user
        response = self.client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Check user was created
        with app.app_context():
            user = User.query.filter_by(username='testuser').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.email, 'test@example.com')
            
        # Test login
        response = self.client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
    def test_health_check(self):
        """Test the health check endpoint."""
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertEqual(json_data['status'], 'ok')
        self.assertIn('database', json_data)
        
    def test_admin_access(self):
        """Test admin access control."""
        # Create regular user
        with app.app_context():
            user = User(username='regular', email='regular@example.com')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
            
        # Login as regular user
        self.client.post('/login', data={
            'email': 'regular@example.com',
            'password': 'password123'
        })
        
        # Try to access admin page
        response = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertEqual(response.status_code, 403)  # Should be forbidden
        
        # Create admin user
        with app.app_context():
            admin = User(username=os.environ.get('ADMIN_USERNAME', 'admin'), 
                         email=os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai'))
            admin.set_password('adminpass')
            db.session.add(admin)
            db.session.commit()
            
        # Login as admin
        self.client.post('/login', data={
            'email': os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai'),
            'password': 'adminpass'
        })
        
        # Try to access admin page again
        response = self.client.get('/admin/dashboard')
        self.assertEqual(response.status_code, 200)  # Should be allowed

if __name__ == '__main__':
    unittest.main()
