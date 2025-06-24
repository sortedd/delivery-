from flask import Flask, render_template, request, jsonify, session, send_file, redirect, url_for
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
import uuid
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Have to Change This in Production 

# In-memory storage for orders
orders = {}

# Hardcoded credentials
VALID_USERNAME = 'test'
VALID_PASSWORD = 'test123'

@app.route('/')
def index():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session['logged_in'] = True
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'})
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/submit_order', methods=['POST'])
def submit_order():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    
    # Generate tracking number similar to React version (DL + timestamp + random)
    prefix = 'DL'
    timestamp_part = str(int(datetime.now().timestamp()))[-8:]  # Last 8 digits of timestamp
    random_part = ''.join([chr(65 + (int(c) % 26)) for c in str(uuid.uuid4().int)[:4]])  # 4 random letters
    delivery_id = f"{prefix}{timestamp_part}{random_part}"
    
    # Store order data
    order_data = {
        'delivery_id': delivery_id,
        'sender_name': data.get('sender_name'),
        'sender_address': data.get('sender_address'),
        'receiver_name': data.get('receiver_name'),
        'receiver_address': data.get('receiver_address'),
        'timestamp': datetime.now().isoformat()
    }
    
    orders[delivery_id] = order_data
    
    return jsonify({
        'success': True, 
        'delivery_id': delivery_id,
        'order_data': order_data
    })

def generate_barcode(delivery_id):
    """Generate barcode for delivery ID"""
    try:
        # Create barcode
        code128 = barcode.get_barcode_class('code128')
        barcode_instance = code128(delivery_id, writer=ImageWriter())
        
        # Save to bytes
        buffer = io.BytesIO()
        barcode_instance.write(buffer)
        buffer.seek(0)
        
        # Convert to base64 for embedding in PDF
        barcode_b64 = base64.b64encode(buffer.getvalue()).decode()
        return barcode_b64
    except Exception as e:
        print(f"Barcode generation error: {e}")
        return None

@app.route('/generate_label/<delivery_id>')
def generate_label(delivery_id):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    
    if delivery_id not in orders:
        return "Order not found", 404
    
    order = orders[delivery_id]
    
    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "DELIVERY LABEL")
    
    # Delivery ID
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 80, f"Delivery ID: {delivery_id}")
    
    # Generate and add barcode
    barcode_b64 = generate_barcode(delivery_id)
    if barcode_b64:
        try:
            # Decode barcode image
            barcode_data = base64.b64decode(barcode_b64)
            barcode_buffer = io.BytesIO(barcode_data)
            
            # Add barcode to PDF
            p.drawInlineImage(barcode_buffer, 50, height - 150, width=200, height=50)
        except Exception as e:
            print(f"Error adding barcode to PDF: {e}")
    
    # Sender Information
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 200, "SENDER:")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 220, f"Name: {order['sender_name']}")
    
    # Split address into multiple lines if too long
    sender_address = order['sender_address']
    if len(sender_address) > 60:
        # Simple word wrap
        words = sender_address.split()
        line1 = ""
        line2 = ""
        for word in words:
            if len(line1 + word) < 60:
                line1 += word + " "
            else:
                line2 += word + " "
        p.drawString(50, height - 240, f"Address: {line1.strip()}")
        if line2.strip():
            p.drawString(50, height - 260, f"         {line2.strip()}")
        next_y = height - 280
    else:
        p.drawString(50, height - 240, f"Address: {sender_address}")
        next_y = height - 260
    
    # Receiver Information
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, next_y, "RECEIVER:")
    p.setFont("Helvetica", 10)
    p.drawString(50, next_y - 20, f"Name: {order['receiver_name']}")
    
    # Split receiver address into multiple lines if too long
    receiver_address = order['receiver_address']
    if len(receiver_address) > 60:
        words = receiver_address.split()
        line1 = ""
        line2 = ""
        for word in words:
            if len(line1 + word) < 60:
                line1 += word + " "
            else:
                line2 += word + " "
        p.drawString(50, next_y - 40, f"Address: {line1.strip()}")
        if line2.strip():
            p.drawString(50, next_y - 60, f"         {line2.strip()}")
        next_y = next_y - 80
    else:
        p.drawString(50, next_y - 40, f"Address: {receiver_address}")
        next_y = next_y - 60
    
    # Timestamp
    p.setFont("Helvetica", 8)
    p.drawString(50, next_y - 20, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'delivery_label_{delivery_id}.pdf',
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    app.run(debug=True)