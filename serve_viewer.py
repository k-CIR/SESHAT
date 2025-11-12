#!/usr/bin/env python3
"""
Simple HTTP server to serve the BIDS viewer with proper file access.
This bypasses browser CORS restrictions for local file access.
"""

import http.server
import socketserver
import webbrowser
import os
import json
from pathlib import Path

PORT = 8000

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers to allow local file access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
    def do_POST(self):
        """Handle POST requests for saving files"""
        if self.path == '/save':
            try:
                # Read the request body
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                # Get the file path and content
                file_path = data.get('path', '').lstrip('./')
                content = data.get('content', '')
                
                if not file_path:
                    self.send_error(400, "No file path provided")
                    return
                
                # Resolve the full path (security: stay within server directory)
                full_path = Path(os.getcwd()) / file_path
                if not str(full_path.resolve()).startswith(str(Path(os.getcwd()).resolve())):
                    self.send_error(403, "Access denied: path outside server directory")
                    return
                
                # Create parent directories if needed
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Write the file
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'File saved: {file_path}'
                }).encode('utf-8'))
                
                print(f"✅ Saved file: {file_path}")
                
            except Exception as e:
                self.send_error(500, f"Error saving file: {str(e)}")
                print(f"❌ Error saving file: {e}")
        else:
            self.send_error(404, "Endpoint not found")
    
    def log_message(self, format, *args):
        # Custom logging format
        print(f"[{self.log_date_time_string()}] {format % args}")

if __name__ == "__main__":
    # Change to the script's directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    print("=" * 60)
    print("🧠 BIDS Conversion Viewer Server")
    print("=" * 60)
    print(f"📂 Serving from: {script_dir}")
    print(f"🌐 Server running at: http://localhost:{PORT}")
    print(f"📄 Opening viewer at: http://localhost:{PORT}/bids_viewer.html")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()
    
    try:
        with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
            # Open the browser after a short delay
            webbrowser.open(f'http://localhost:{PORT}/bids_viewer.html')
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"\n❌ Error: Port {PORT} is already in use.")
            print(f"Try closing other applications or use a different port.")
            print(f"\nAlternatively, open this URL in your browser:")
            print(f"   http://localhost:{PORT}/bids_viewer.html")
        else:
            raise
