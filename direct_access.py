#!/usr/bin/env python
"""
Standalone WSGI application for diagnosing routing issues
"""

import os
import sys
import json
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def application(environ, start_response):
    """
    Simple WSGI application that returns diagnostic information
    for any path that's requested.
    """
    path = environ.get('PATH_INFO', '').lstrip('/')
    method = environ.get('REQUEST_METHOD', 'GET')
    
    logger.debug(f"Direct access request: {method} {path}")
    
    # Create a simple response based on the path
    if path == '':
        # Root path - return a simple HTML page
        start_response('200 OK', [('Content-Type', 'text/html')])
        return [b"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Direct Access Diagnostic</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 800px; margin: 0 auto; }
                h1 { color: #0066cc; }
                .link { display: block; margin: 10px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Direct Access Diagnostic</h1>
                <p>This page is being served by a simple WSGI application, bypassing Flask.</p>
                <p>Try these diagnostic links:</p>
                <a class="link" href="/env">Environment Variables</a>
                <a class="link" href="/request">Request Information</a>
                <a class="link" href="/login">/login Path Test</a>
                <a class="link" href="/register">/register Path Test</a>
            </div>
        </body>
        </html>
        """]
    
    elif path == 'env':
        # Return environment variables
        env_vars = {k: v for k, v in os.environ.items() 
                   if k.startswith(('FLASK_', 'RENDER_', 'PYTHON'))}
        
        start_response('200 OK', [('Content-Type', 'application/json')])
        return [json.dumps(env_vars, indent=2).encode()]
    
    elif path == 'request':
        # Return request information
        request_info = {
            'path': environ.get('PATH_INFO', ''),
            'method': environ.get('REQUEST_METHOD', ''),
            'query_string': environ.get('QUERY_STRING', ''),
            'server_name': environ.get('SERVER_NAME', ''),
            'server_port': environ.get('SERVER_PORT', ''),
            'server_protocol': environ.get('SERVER_PROTOCOL', ''),
            'http_host': environ.get('HTTP_HOST', ''),
            'wsgi_path': environ.get('wsgi.path', ''),
        }
        
        # Add all environment variables for completeness
        request_info['environ'] = {k: str(v) for k, v in environ.items()}
        
        start_response('200 OK', [('Content-Type', 'application/json')])
        return [json.dumps(request_info, indent=2).encode()]
    
    else:
        # For any other path, return information about it
        start_response('200 OK', [('Content-Type', 'text/html')])
        return [f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Path Test: /{path}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                h1 {{ color: #0066cc; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Path Test: /{path}</h1>
                <p>This page is handling the path <code>/{path}</code> directly via a standalone WSGI app.</p>
                <p>Method: {method}</p>
                <p>If you can see this page but not the same path in your Flask app, the issue is likely with how Flask is handling routes.</p>
                <p><a href="/">Back to diagnostics home</a></p>
            </div>
        </body>
        </html>
        """.encode()]

# If run directly, serve this application
if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    
    port = int(os.environ.get("PORT", 5000))
    httpd = make_server('', port, application)
    print(f"Serving on port {port}...")
    
    # Serve until process is killed
    httpd.serve_forever() 