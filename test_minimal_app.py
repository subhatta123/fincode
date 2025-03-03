import unittest
import minimal_app

class TestMinimalApp(unittest.TestCase):
    def setUp(self):
        self.app = minimal_app.app.test_client()
        
    def test_home_page(self):
        """Test that the home page returns a 200 status code"""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Render Flask Test', response.data)
        
    def test_debug_page(self):
        """Test that the debug page returns a 200 status code"""
        response = self.app.get('/debug')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Debug Information', response.data)

if __name__ == '__main__':
    unittest.main() 