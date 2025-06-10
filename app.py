from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import pytesseract
from PIL import Image
from googletrans import Translator
import tempfile
import os
from pdf2image import convert_from_path
import traceback
import requests
import socket
import time
from functools import wraps

app = Flask(__name__)
CORS(app)  # Allow CORS for frontend access

# Configure translator with multiple endpoints
translator = Translator(service_urls=[
    'translate.google.com',
    'translate.google.co.kr',
    'translate.google.de'
])

# Set socket timeout globally
socket.setdefaulttimeout(10)

# Configure Tesseract path if needed
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'bmp', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_image(image_path):
    try:
        with Image.open(image_path) as img:
            text = pytesseract.image_to_string(img)
            return text if text.strip() else None
    except Exception as e:
        print("OCR failed:", e)
        traceback.print_exc()
        return None

def extract_text_from_pdf(pdf_path):
    try:
        images = convert_from_path(pdf_path)
        text = ''
        for image in images:
            text += pytesseract.image_to_string(image)
        return text if text.strip() else None
    except Exception as e:
        print("PDF to text failed:", e)
        traceback.print_exc()
        return None

def translate_text(text, target_language):
    try:
        # Split text into chunks to avoid timeout with large texts
        max_chunk_size = 5000
        chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
        
        translated_text = ''
        for chunk in chunks:
            try:
                translated = translator.translate(chunk, dest=target_language)
                translated_text += translated.text
            except Exception as e:
                print(f"Translation chunk failed: {e}")
                continue
                
        return translated_text if translated_text else None
    except Exception as e:
        print("Translation failed:", e)
        traceback.print_exc()
        return None

def safe_delete(filepath):
    """Safely delete a file with retries"""
    if not filepath or not os.path.exists(filepath):
        return
        
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            os.unlink(filepath)
            break
        except PermissionError:
            if attempt == max_attempts - 1:
                print(f"Failed to delete {filepath} after {max_attempts} attempts")
            time.sleep(0.1)

@app.route('/upload', methods=['POST'])
def upload_file():
    temp_input_path = None
    output_path = None
    
    try:
        if not request.content_type or 'multipart/form-data' not in request.content_type:
            return jsonify({"error": "Content-Type must be multipart/form-data"}), 400
            
        file = request.files.get('file')
        target_language = request.form.get('target_language')
        
        if not file:
            return jsonify({"error": "No file provided"}), 400
        if not target_language:
            return jsonify({"error": "No target language specified"}), 400
        if file.filename == '':
            return jsonify({"error": "Empty filename"}), 400
        if not allowed_file(file.filename):
            return jsonify({"error": "Unsupported file type"}), 400

        filename = file.filename.lower()
        
        # Create temporary input file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[-1]) as temp_input:
            file.save(temp_input.name)
            temp_input_path = temp_input.name

        # Extract text
        if filename.endswith(".pdf"):
            extracted_text = extract_text_from_pdf(temp_input_path)
        else:
            extracted_text = extract_text_from_image(temp_input_path)

        if extracted_text is None:
            return jsonify({"error": "Text extraction failed"}), 500
        if not extracted_text.strip():
            return jsonify({"error": "No text found in document"}), 400

        # Translate text
        translated_text = translate_text(extracted_text, target_language)
        if translated_text is None:
            return jsonify({"error": "Translation failed"}), 500

        # Create output file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode='w', encoding='utf-8') as temp_output:
            temp_output.write(translated_text)
            output_path = temp_output.name

        # Send file and ensure it's closed before deletion
        response = send_file(
            output_path,
            as_attachment=True,
            download_name='translated.txt',
            mimetype='text/plain'
        )
        
        # Close the file explicitly
        try:
            response.direct_passthrough = False
        except:
            pass
            
        return response

    except Exception as e:
        print("Error during processing:", e)
        traceback.print_exc()
        return jsonify({"error": "Internal Server Error"}), 500
        
    finally:
        # Clean up files with retries
        safe_delete(temp_input_path)
        safe_delete(output_path)

if __name__ == '__main__':
    app.run(debug=True)