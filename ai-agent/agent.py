"""
Agent-Pay: AI Agent Service (agent.py)

This Flask server acts as the "brain" for the Agent-Pay system
and implements a state machine for handling invoice payments.

State Machine (per invoice):
  - PROCESSING: Actively parsing audio to extract invoice details.
  - MONITORING: Invoice details extracted; awaiting external trigger (e.g., shipping).
  - EXECUTING: Trigger received; actively calling backend to process payment.
  - PAID: Backend confirmed payment; workflow complete.

Endpoints:
  - POST /api/transcribe: (Voice Command) Creates a new invoice. If shipping is
    already confirmed, pays immediately. Otherwise, sets to 'MONITORING'.
  - POST /api/mock-shipping-confirmation: (External Trigger) Logs shipping
    confirmation. If invoice is 'MONITORING', pays it.
  - GET  /api/payment-status: (Frontend Polling) Returns the state of all
    invoices.
  - GET  /health: A simple health check for the service.
"""

# --- Core Libraries ---
from flask import Flask, request, jsonify
import requests
import os
import re
from io import BytesIO

# --- Third-Party Service Clients ---
from elevenlabs.client import ElevenLabs
from elevenlabs.errors import UnprocessableEntityError
import google.generativeai as genai

# ==============================================================================
# --- SERVICE CONFIGURATION ---
# ==============================================================================

app = Flask(__name__)

# --- API Key Configuration ---
ELEVEN_API_KEY = os.environ.get("ELEVEN_API_KEY", "YOUR_ELEVENLABS_API_KEY_GOES_HERE")
GOOGLE_AI_KEY = os.environ.get("GOOGLE_AI_KEY", "YOUR_GOOGLE_AI_API_KEY_GOES_HERE")

# --- Backend Service URL ---
BACKEND_API_URL = "http://localhost:5000/api/trigger-payment"

# Check if API keys are set
if ELEVEN_API_KEY == "YOUR_ELEVENLABS_API_KEY_GOES_HERE":
    print("WARNING: ELEVEN_API_KEY is not set. Please set the environment variable.")
if GOOGLE_AI_KEY == "YOUR_GOOGLE_AI_API_KEY_GOES_HERE":
    print("WARNING: GOOGLE_AI_KEY is not set. Please set the environment variable.")

# --- Client Initialization ---
try:
    eleven_client = ElevenLabs(api_key=ELEVEN_API_KEY)
    
    genai.configure(api_key=GOOGLE_AI_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    print(f"FATAL: Could not initialize AI clients. Check API keys? Error: {e}")

# In-memory state machine database for payment status.
# e.g., {"991": "MONITORING", "992": "PAID"}
invoice_registry = {}

# NEW: In-memory set to store IDs of invoices with confirmed shipping.
# This is independent of the payment state.
shipping_confirmation_registry = set()

# ==============================================================================
# --- AI & PAYMENT HELPER FUNCTIONS ---
# ==============================================================================

def extract_invoice_id_from_text(text: str) -> str | None:
    """
    Uses a Generative AI model to extract an invoice ID from transcribed text.
    """
    print(f"[AI Agent] Sending to Google AI for extraction: '{text}'")
    
    prompt = f"""
    You are an invoice processing assistant. Your only job is to extract an invoice number 
    from the following text. The invoice number may be spoken as digits (e.g., 'one two three' 
    or 'nine nine one') or as a full number (e.g., 'one hundred twenty-three'). 
    
    Respond with *only* the digits of the invoice number. 
    Do not add any other text, explanation, or punctuation.
    If no invoice number is found, respond with "NULL".

    Text: "{text}"
    """
    
    try:
        response = gemini_model.generate_content(prompt)
        invoice_id = re.sub(r'\D', '', response.text)
        
        if not invoice_id:
            print("[AI Agent] Google AI could not find an invoice ID.")
            return None
            
        print(f"[AI Agent] Google AI extracted invoice ID: {invoice_id}")
        return invoice_id
        
    except Exception as e:
        print(f"[AI Agent] ERROR calling Google AI: {e}")
        return None


def execute_payment(invoice_id: str) -> bool:
    """
    (NEW HELPER)
    Triggers the backend payment and handles the state machine.
    This is now called by both /transcribe and /mock-shipping-confirmation.
    
    Returns:
        bool: True on success, False on failure.
    """
    if invoice_registry.get(invoice_id) == "PAID":
        print(f"[AI Agent] Payment for {invoice_id} already complete.")
        return True
        
    # --- Set state to EXECUTING ---
    invoice_registry[invoice_id] = "EXECUTING"
    print(f"[AI Agent] State for {invoice_id} set to: EXECUTING")

    try:
        # Trigger the payment on the backend.
        payload = {"invoiceId": invoice_id}
        print(f"[AI Agent] Telling backend to pay: {invoice_id} at {BACKEND_API_URL}")
        
        response = requests.post(BACKEND_API_URL, json=payload)

        if response.status_code == 200:
            # --- Set state to PAID ---
            invoice_registry[invoice_id] = "PAID"
            print(f"[AI Agent] Backend confirmed payment. State for {invoice_id} set to: PAID")
            return True
        else:
            # --- Revert state to MONITORING on failure ---
            print(f"[AI Agent] Backend returned an error: {response.text}")
            invoice_registry[invoice_id] = "MONITORING"
            print(f"[AI Agent] Payment failed. State for {invoice_id} reverted to: MONITORING")
            return False

    except Exception as e:
        # --- Revert state to MONITORING on failure ---
        print(f"[AI Agent] An unexpected error occurred during payment: {e}")
        invoice_registry[invoice_id] = "MONITORING"
        print(f"[AI Agent] Payment failed. State for {invoice_id} reverted to: MONITORING")
        return False

# ==============================================================================
# --- API ENDPOINTS ---
# ==============================================================================

@app.route("/health", methods=['GET'])
def health_check():
    """
    Health check endpoint.
    Confirms that the AI Agent server is running.
    """
    return jsonify({"status": "AI Agent is running"}), 200


@app.route("/api/payment-status", methods=['GET'])
def get_payment_status():
    """
    Returns the state of all invoices in the registry.
    The frontend polls this to update its dashboard.
    """
    print("[AI Agent] Frontend requested payment status for all invoices.")
    status_list = [
        {"invoiceId": inv_id, "status": state} 
        for inv_id, state in invoice_registry.items()
    ]
    return jsonify(status_list), 200


@app.route("/api/transcribe", methods=['POST'])
def transcribe_audio():
    """
    (REFACTORED for new logic)
    Handles the *creation* of a new payment task via voice.
    1. Receives audio, sets state to 'PROCESSING'.
    2. Transcribes (ElevenLabs) and Extracts (Google AI).
    3. Checks if shipping is already confirmed for this ID.
       - If YES: Executes payment immediately.
       - If NO: Sets state to 'MONITORING'.
    """
    print("[AI Agent] Received request at /api/transcribe (Create Invoice)")
    
    if 'audio' not in request.files:
        return jsonify({"error": "No 'audio' file found in request"}), 400
        
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    temp_id = f"temp_{len(invoice_registry)}"
    invoice_registry[temp_id] = "PROCESSING"

    try:
        # --- Part 1: Transcribe with ElevenLabs ---
        print("[AI Agent] Sending audio to ElevenLabs...")
        audio_bytes = audio_file.read() 
        audio_io = BytesIO(audio_bytes) 
        
        response = eleven_client.speech_to_text.convert(
            file=audio_io,
            model_id="scribe_v1" 
        )
        transcribed_text = response.text.strip()
        if not transcribed_text:
            print("[AI Agent] ElevenLabs returned empty transcription.")
            del invoice_registry[temp_id] # Clean up
            return jsonify({"error": "Audio was unclear or silent."}), 400
            
        print(f"[AI Agent] Transcription successful: '{transcribed_text}'")

        # --- Part 2: Extract with Google AI ---
        invoice_id = extract_invoice_id_from_text(transcribed_text)
        del invoice_registry[temp_id] # Clean up temp_id
        
        if not invoice_id:
            return jsonify({
                "error": "Could not extract an invoice ID from the audio.",
                "text": transcribed_text
            }), 400

        if invoice_id in invoice_registry and invoice_registry[invoice_id] == "PAID":
             return jsonify({
                "status": "Invoice was already paid.",
                "invoiceId": invoice_id,
                "invoiceState": "PAID"
            }), 200
        
        # --- Part 3: (NEW LOGIC) Check Shipping Status ---
        if invoice_id in shipping_confirmation_registry:
            # Shipping was confirmed *before* this voice command was given.
            # We can pay immediately.
            print(f"[AI Agent] Invoice {invoice_id} has pre-confirmed shipping. Executing payment.")
            
            payment_success = execute_payment(invoice_id)
            
            if payment_success:
                return jsonify({
                    "status": "Invoice was pre-confirmed and paid immediately.",
                    "invoiceId": invoice_id,
                    "transcribedText": transcribed_text,
                    "invoiceState": "PAID"
                }), 200
            else:
                return jsonify({
                    "error": "Invoice was pre-confirmed, but payment execution failed.",
                    "invoiceId": invoice_id,
                    "invoiceState": "MONITORING"
                }), 500
        
        else:
            # Normal flow: Shipping is not confirmed. Set to MONITORING.
            print(f"[AI Agent] New invoice {invoice_id} created. State: MONITORING.")
            invoice_registry[invoice_id] = "MONITORING"
            
            return jsonify({
                "status": "Invoice created and is now being monitored.",
                "invoiceId": invoice_id,
                "transcribedText": transcribed_text,
                "invoiceState": "MONITORING"
            }), 201 # 201 Created
    
    except UnprocessableEntityError as e:
        print(f"[AI Agent] ERROR: Unprocessable Entity (ElevenLabs). {e}")
        if temp_id in invoice_registry: del invoice_registry[temp_id]
        return jsonify({"error": f"Invalid audio format or file: {str(e)}"}), 422
    except Exception as e:
        print(f"[AI Agent] ERROR during transcription: {e}")
        if temp_id in invoice_registry: del invoice_registry[temp_id]
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route("/api/mock-shipping-confirmation", methods=['POST'])
def mock_shipping_confirmation():
    """
    (REFACTORED for new logic)
    MOCK ENDPOINT (Demo Presenter Button)
    1. Logs that shipping is confirmed for an invoiceId.
    2. Checks if that invoice is waiting in 'MONITORING' state.
    3. If yes, it executes the payment.
    """
    data = request.json
    invoice_id = data.get('invoiceId')
    print(f"[AI Agent] Received shipping confirmation trigger for: {invoice_id}")

    if not invoice_id:
        return jsonify({"error": "invoiceId is required"}), 400

    # --- Part 1: Log the shipping confirmation ---
    shipping_confirmation_registry.add(invoice_id)
    print(f"[AI Agent] Invoice {invoice_id} added to shipping confirmation registry.")

    # --- Part 2: Check state machine ---
    current_state = invoice_registry.get(invoice_id)
    
    if current_state == "MONITORING":
        # This is the primary flow: The invoice was waiting for this trigger.
        print(f"[AI Agent] Invoice {invoice_id} was MONITORING. Executing payment now.")
        
        payment_success = execute_payment(invoice_id)
        
        if payment_success:
            return jsonify({
                "status": "Condition met and payment triggered",
                "invoiceId": invoice_id,
                "invoiceState": "PAID"
            }), 200
        else:
            return jsonify({
                "error": "Payment execution failed.",
                "invoiceId": invoice_id,
                "invoiceState": "MONITORING"
            }), 500
            
    elif current_state is None:
        # This is fine. The shipping confirmation arrived *before* the invoice
        # was created. /api/transcribe will handle it.
        print(f"[AI Agent] Shipping confirmation for {invoice_id} recorded (invoice not yet created).")
        return jsonify({
            "status": "Shipping confirmation recorded. Waiting for invoice creation.",
            "invoiceId": invoice_id
        }), 200
        
    elif current_state == "PAID":
        print(f"[AI Agent] WARNING: Invoice {invoice_id} is already paid.")
        return jsonify({"status": "Invoice was already paid."}), 200
        
    elif current_state == "EXECUTING":
        print(f"[AI Agent] WARNING: Payment for {invoice_id} is already in progress.")
        return jsonify({"status": "Payment is already in progress."}), 202
    
    else:
        # e.g., PROCESSING
        print(f"[AI Agent] Invoice {invoice_id} is in state '{current_state}', not 'MONITORING'.")
        return jsonify({
            "error": "Invoice is in a non-standard state.",
            "currentState": current_state
        }), 409

# ==============================================================================
# --- RUN SERVER ---
# ==============================================================================

if __name__ == '__main__':
    # Run on port 5001 to avoid conflict with the backend (port 5000)
    app.run(port=5001, debug=True)

