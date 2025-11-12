#!/usr/bin/env python3
"""
Simple HTTP server to serve the BIDS viewer with proper file access.
This bypasses browser CORS restrictions for local file access.
"""

import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

PORT = 8000

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers to allow local file access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
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
