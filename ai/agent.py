"""
Agent-Pay: AI Agent Service (v4.11 - Final Balance Sync)
Goal: Ensure all payment flows (Manual and Voice) use 1 USDC.
"""
# --- Core Libraries ---
from flask import Flask, request, jsonify, g
from flask_cors import CORS
import requests
import json
import os
import re
from io import BytesIO
from datetime import datetime
import time
import random 

# --- Load .env file BEFORE accessing os.environ ---
from dotenv import load_dotenv
load_dotenv() 

# --- AI Service Clients ---
from elevenlabs.client import ElevenLabs
from elevenlabs.errors import UnprocessableEntityError
import google.generativeai as genai

# --- Configuration ---
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:8000"}})

# Backend (Executor) URLs
BACKEND_EXECUTOR_URL = "http://localhost:5001"
BACKEND_CREATE_URL = f"{BACKEND_EXECUTOR_URL}/api/create-on-chain"
BACKEND_TRIGGER_URL = f"{BACKEND_EXECUTOR_URL}/api/trigger-payment"
BACKEND_BALANCE_CHECK_URL = f"{BACKEND_EXECUTOR_URL}/api/check-balance"

# --- API Key Configuration (Now reads from .env) ---
ELEVEN_API_KEY = os.environ.get("ELEVEN_API_KEY")
GOOGLE_AI_KEY = os.environ.get("GOOGLE_AI_KEY")

# --- Client Initialization ---
try:
    if not ELEVEN_API_KEY:
        print("WARNING: ELEVEN_API_KEY env var not set.")
    eleven_client = ElevenLabs(api_key=ELEVEN_API_KEY)
    
    if not GOOGLE_AI_KEY:
        print("WARNING: GOOGLE_AI_KEY env var not set.")
    genai.configure(api_key=GOOGLE_AI_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"FATAL: Could not initialize AI clients. Check API keys? Error: {e}")

# --- DB Cache (Remains the same) ---
DB_FILE = os.path.join(os.path.dirname(__file__), '..', 'backend', 'invoice_data.json')
INVOICE_DB = {} 
shipping_confirmation_registry = set()

def load_database():
    global INVOICE_DB
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r') as f:
                INVOICE_DB = dict(json.load(f))
                print(f"✅ [AI Brain] In-Memory DB loaded successfully with {len(INVOICE_DB)} items.")
                return
    except Exception as e:
        print(f"Warning: Failed to load DB file: {e}. Starting fresh.")
    INVOICE_DB = {}

def save_database():
    global INVOICE_DB
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(list(INVOICE_DB.items()), f, indent=4)
    except Exception as e:
        print(f"CRITICAL: Failed to save DB file: {e}")

def get_db():
    global INVOICE_DB
    return INVOICE_DB

# --- Balance Check Function ---
def check_backend_balance(amount_needed):
    """Checks if the executor wallet has enough USDC (including gas buffer)."""
    try:
        response = requests.get(BACKEND_BALANCE_CHECK_URL)
        if response.status_code == 200:
            current_balance = float(response.json().get('balance', 0))
            
            # 💡 التعديل: نستخدم 1.1 USDC كحد أدنى للتحقق
            total_needed = float(amount_needed) + 0.1 
            
            if current_balance < total_needed:
                print(f"[AI Brain] LOW BALANCE! Current: {current_balance}, Needed: {total_needed}")
                return False, current_balance
            else:
                return True, current_balance
        else:
            print(f"[AI Brain] ERROR: Could not get balance from backend.")
            return False, 0
    except Exception as e:
        print(f"[AI Brain] CRITICAL ERROR checking balance: {e}")
        return False, 0

# --- API Endpoints ---
@app.route("/health", methods=['GET'])
def health_check():
    return jsonify({"status": "AI Agent (v4.11 Brain) is running"}), 200

# --- Endpoint for Voice Recording ---
@app.route("/api/transcribe", methods=['POST'])
def transcribe_audio():
    print("[AI Brain] Received request at /api/transcribe (Voice Create)")
    
    if 'audio' not in request.files:
        return jsonify({"error": "No 'audio' file found in request"}), 400
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        # --- BYPASS: Generate stable ID ---
        random_id = random.randint(500, 999) 
        invoice_id = f"INV-VOICE-{random_id}" 
        
        db = get_db()
        while invoice_id in db:
            random_id = random.randint(500, 999)
            invoice_id = f"INV-VOICE-{random_id}"
        
        print(f"[AI Brain] Voice generated {invoice_id}. Calling internal create_payment...")
        
        voice_payload = {
            "invoiceId": invoice_id,
            "amount": "1", # 💡 التعديل هنا: 1 USDC للقيمة
            "recipientAddress": "0x57211cf52b7830f08588fea975ffccaed493eef3", 
            "condition": "goods_shipped"
        }
        
        response_dict, status_code = create_payment_logic(payload=voice_payload)
        
        if status_code == 201:
            response_dict['details']['invoiceId'] = invoice_id
        
        return jsonify(response_dict), status_code
    
    except Exception as e:
        print(f"[AI Brain] CRITICAL Error during voice flow bypass: {e}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# --- Endpoint for Manual/Voice (Step 1) ---
@app.route("/api/create-payment", methods=['POST'])
def create_payment_request(): 
    data = request.json
    response_dict, status_code = create_payment_logic(payload=data)
    return jsonify(response_dict), status_code

# --- Core Creation Logic (with Pre-Check) ---
def create_payment_logic(payload):
    db = get_db()
    
    invoice_id = payload.get('invoiceId')
    amount = payload.get('amount', '1') # 💡 التعديل هنا: القيمة الافتراضية 1 USDC
    
    if not invoice_id:
        return {"error": "invoiceId is required"}, 400

    if invoice_id in db:
        print(f"[AI Brain] Invoice {invoice_id} already exists. Status: {db[invoice_id]['status']}")
        return {"error": "Invoice ID already exists.", "status": db[invoice_id]['status']}, 409 

    # 1. PRE-CHECK BALANCE
    is_solvent, current_balance = check_backend_balance(amount)
    if not is_solvent:
        print(f"[AI Brain] FAILED: Insufficient balance pre-check.")
        return {"error": f"INSUFFICIENT_FUNDS. Wallet has only {current_balance} USDC. Requires {float(amount)+0.1} USDC (for funding and gas)."}, 402 # 402 Payment Required

    # 2. Create the invoice in our local database
    payment_details = {
        "amount": amount,
        "recipientAddress": payload.get("recipientAddress"),
        "condition": payload.get("condition", "goods_shipped"),
        "status": "Pending", 
        "transactionHash": None,
        "paidAt": None,
        "createdAt": datetime.now().isoformat()
    }
    db[invoice_id] = payment_details
    save_database() 
    print(f"[AI Brain] Saved {invoice_id} to DB (Cache) with status 'Pending'.")

    # 3. Call the Backend (Executor) to create it on-chain
    try:
        print(f"[AI Brain] Calling Backend Executor at {BACKEND_CREATE_URL}...")
        response = requests.post(BACKEND_CREATE_URL, json=payload) 

        if response.status_code == 201:
            print(f"[AI Brain] Backend Executor confirmed on-chain creation for {invoice_id}.")
            return {"message": "Payment created and pending condition", "details": payment_details}, 201
        else:
            backend_error = response.json().get('error', response.text)
            if "INSUFFICIENT_BALANCE" in backend_error:
                 error_message = f"INSUFFICIENT_FUNDS. Re-check: Wallet has only {current_balance} USDC."
            else:
                 error_message = f"ON_CHAIN_FAILURE: {backend_error}"

            print(f"[AI Brain] Backend Executor FAILED: {error_message}")
            del db[invoice_id] # Rollback
            save_database()
            return {"error": error_message}, 500
            
    except Exception as e:
        print(f"[AI Brain] CRITICAL Error calling Backend Executor: {e}")
        del db[invoice_id] # Rollback
        save_database()
        return {"error": f"Failed to connect to Backend Executor: {str(e)}"}, 500

@app.route("/api/payment-status", methods=['GET'])
def get_payment_status():
    db = get_db() 
    status_list = list(db.items())
    return jsonify(status_list), 200

@app.route("/api/process-invoice", methods=['POST'])
def process_invoice():
    db = get_db()
    data = request.json
    invoice_id = data.get('invoiceId')
    
    if not invoice_id:
        return jsonify({"error": "invoiceId is required"}), 400

    print(f"[AI Brain] Received STEP 2 (Monitoring) task for: {invoice_id}")
    
    if invoice_id in db:
        if db[invoice_id]["status"] == "Pending":
            db[invoice_id]["status"] = "MONITORING"
            save_database()
        else:
            print(f"[AI Brain] Invoice {invoice_id} is already {db[invoice_id]['status']}. No change needed.")
    else:
        return jsonify({"error": "Invoice not found. Run Step 1 first."}), 404

    if invoice_id in shipping_confirmation_registry:
        print(f"[AI Brain] Invoice {invoice_id} has PRE-CONFIRMED shipping. Executing payment NOW.")
        response_data, status_code = trigger_payment(invoice_id)
        if status_code == 200:
             return jsonify({"status": "Invoice was pre-confirmed and paid immediately.", "invoiceId": invoice_id}), 200
        else:
             return jsonify({"error": "Invoice was pre-confirmed, but payment execution failed."}), 500
    
    print(f"[AI Brain] State for {invoice_id} set to: MONITORING")
    return jsonify({"status": "Invoice is now being monitored."}), 200

@app.route("/api/mock-shipping-confirmation", methods=['POST'])
def mock_shipping_confirmation():
    data = request.json
    invoice_id = data.get('invoiceId')
    response_data, status_code = trigger_payment(invoice_id)
    return jsonify(response_data), status_code

def trigger_payment(invoice_id):
    db = get_db()
    if not invoice_id:
        return {"error": "invoiceId is required"}, 400

    shipping_confirmation_registry.add(invoice_id)
    current_status = db.get(invoice_id, {}).get('status')
    
    if current_status == "MONITORING":
        print(f"[AI Brain] Invoice {invoice_id} was MONITORING. Calling Backend to execute payment...")
        db[invoice_id]["status"] = "EXECUTING"
        save_database()
        
        try:
            payload = {"invoiceId": invoice_id}
            response = requests.post(BACKEND_TRIGGER_URL, json=payload)

            if response.status_code == 200:
                print(f"[AI Brain] Backend confirmed payment. State for {invoice_id} set to: PAID")
                db[invoice_id]["status"] = "PAID"
                db[invoice_id]["paidAt"] = response.json().get("paidAt") 
                db[invoice_id]["transactionHash"] = response.json().get("transactionHash") 
                save_database()
                return {"status": "Condition met and payment triggered"}, 200
            else:
                print(f"[AI Brain] Backend returned an error: {response.text}")
                db[invoice_id]["status"] = "MONITORING"
                save_database()
                return {"error": "Payment execution failed."}, 500
        except Exception as e:
            print(f"[AI Brain] An unexpected error occurred during payment: {e}")
            db[invoice_id]["status"] = "MONITORING"
            save_database()
            return {"error": f"An unexpected error occurred: {str(e)}"}, 500
            
    elif current_status is None:
        return {"status": "Shipping confirmation recorded. Waiting for invoice creation."}, 200
    elif current_status == "PAID":
        return {"status": "Invoice was already paid."}, 200
    elif current_status == "EXECUTING":
        return {"status": "Payment is already in progress."}, 202
    else: 
        return {"status": "Shipping confirmation recorded. Waiting for monitoring to start."}, 200

# --- RUN SERVER ---
if __name__ == '__main__':
    load_database() # Load DB into cache on startup
    app.run(port=5000, debug=True)