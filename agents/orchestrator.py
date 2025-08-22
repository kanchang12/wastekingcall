import re
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
import requests
import uuid

# GLOBAL STATE STORAGE - survives instance recreation
_GLOBAL_CONVERSATION_STATES = {}

class AgentOrchestrator:
    """Orchestrates customer interactions between specialized agents with persistent state"""
    
    def __init__(self, koyeb_url: str):
        self.koyeb_url = koyeb_url
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        print("✅ AgentOrchestrator initialized with GLOBAL state management")
    
    # -------------------------
    # PUBLIC METHODS
    # -------------------------
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """Process customer message and decide to fetch price or create booking"""
        conversation_state = self._load_conversation_state(conversation_id)
        self._extract_and_update_state(message, conversation_state)
        
        if context:
            conversation_state.update(context)
        
        extracted = conversation_state.get('extracted_info', {})
        postcode = extracted.get('postcode')
        service = 'skip'  # For simplicity; can extend to other services
        type_ = extracted.get('type', '8yd')
        firstName = extracted.get('firstName')
        phone = extracted.get('phone')
        
        wants_booking = any(word in message.lower() for word in ['book', 'booking', 'confirm', 'go ahead'])
        wants_price = any(word in message.lower() for word in ['price', 'cost', 'quote'])
        
        response = ""
        
        # -------------------------
        # FETCH PRICING
        # -------------------------
        if wants_price and postcode and service and type_:
            print("💰 Customer asked for pricing")
            pricing_result = self._get_pricing(postcode, service, type_)
            response = f"Price for {type_} {service} at {postcode}: £{pricing_result.get('price', 'N/A')}"
            conversation_state['has_pricing'] = True
        
        # -------------------------
        # CREATE BOOKING
        # -------------------------
        elif wants_booking and postcode and service and type_ and firstName and phone:
            print("📋 Customer asked to book")
            booking_ref = str(uuid.uuid4())
            booking_result = self._create_booking_quote(type_, service, postcode, firstName, phone, booking_ref)
            
            if booking_result.get('success'):
                response = (f"✅ Booking confirmed!\n"
                            f"Booking Ref: {booking_result.get('booking_ref')}\n"
                            f"Payment Link: {booking_result.get('payment_link')}\n"
                            f"Price: £{booking_result.get('final_price')}")
            else:
                response = f"❌ Booking failed: {booking_result.get('error')}"
        
        # -------------------------
        # ASK FOR MISSING INFO
        # -------------------------
        else:
            missing = []
            if not postcode:
                missing.append("postcode")
            if not type_:
                missing.append("type of waste/skip size")
            if wants_booking:
                if not firstName:
                    missing.append("first name")
                if not phone:
                    missing.append("phone number")
            response = f"Please provide the following info: {', '.join(missing)}" if missing else "I'm processing your request..."
        
        # Save state
        self._save_conversation_state(conversation_id, conversation_state, message, response, 'orchestrator')
        
        return {
            "success": True,
            "response": response,
            "conversation_state": conversation_state,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat()
        }
    
    # -------------------------
    # HELPER FUNCTIONS
    # -------------------------
    
    def _send_koyeb_webhook(self, url: str, payload: dict, method: str = "POST") -> dict:
        """Send HTTP request to Koyeb webhook"""
        try:
            headers = {"Content-Type": "application/json"}
            if method.upper() == "POST":
                r = requests.post(url, json=payload, headers=headers, timeout=10)
            else:
                r = requests.get(url, params=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # -------------------------
    # REAL API CALLS
    # -------------------------
    
    def _get_pricing(self, postcode: str, service: str, type: str) -> Dict[str, Any]:
        """Call Koyeb endpoint to get pricing"""
        url = f"{self.koyeb_url}/api/wasteking-get-price"
        payload = {"postcode": postcode, "service": service, "type": type}
        return self._send_koyeb_webhook(url, payload, method="POST")
    
    def _create_booking_quote(self, type: str, service: str, postcode: str, firstName: str, phone: str, booking_ref: str) -> Dict[str, Any]:
        """Call Koyeb endpoint to create booking and get payment link"""
        url = f"{self.koyeb_url}/api/wasteking-confirm-booking"
        payload = {
            "booking_ref": booking_ref,
            "postcode": postcode,
            "service": service,
            "type": type,
            "firstName": firstName,
            "phone": phone
        }
        return self._send_koyeb_webhook(url, payload, method="POST")
    
    # -------------------------
    # STATE MANAGEMENT
    # -------------------------
    
    def _load_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        global _GLOBAL_CONVERSATION_STATES
        if conversation_id in _GLOBAL_CONVERSATION_STATES:
            return _GLOBAL_CONVERSATION_STATES[conversation_id].copy()
        default_state = {"conversation_id": conversation_id, "messages": [], "extracted_info": {}}
        return default_state
    
    def _save_conversation_state(self, conversation_id: str, state: Dict[str, Any], message: str, response: str, agent_used: str):
        if 'messages' not in state:
            state['messages'] = []
        state['messages'].append({"timestamp": datetime.now().isoformat(), "customer_message": message,
                                  "agent_response": response, "agent_used": agent_used})
        if len(state['messages']) > 100:
            state['messages'] = state['messages'][-20:]
        state['last_updated'] = datetime.now().isoformat()
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states[conversation_id] = state.copy()
        _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any]):
        """Extract postcode, name, phone, type/waste from customer message"""
        extracted = state.get('extracted_info', {})
        
        # Postcode
        postcode_match = re.search(r'\b([A-Z]{1,2}[0-9][0-9A-Z]?\s?[0-9][A-Z]{2})\b', message.upper())
        if postcode_match:
            extracted['postcode'] = postcode_match.group(1).replace(' ', '')
        
        # Name
        name_match = re.search(r'\b(?:name|my name is|i am|call me)\s+([A-Z][a-z]+)', message)
        if name_match:
            extracted['firstName'] = name_match.group(1)
        
        # Phone
        phone_match = re.search(r'\b(07\d{9})\b', message)
        if phone_match:
            extracted['phone'] = phone_match.group(1)
        
        # Type/size
        size_match = re.search(r'(\d+)\s*(yd|yard|cubic)', message.lower())
        if size_match:
            extracted['type'] = f"{size_match.group(1)}yd"
        
        # Waste keywords
        waste_keywords = ['household', 'construction', 'garden', 'mixed', 'bricks', 'concrete', 'soil', 'rubble']
        found = [w for w in waste_keywords if w in message.lower()]
        if found:
            extracted['waste_type'] = ', '.join(found)
        
        state['extracted_info'] = extracted
        for key in ['postcode', 'firstName', 'phone', 'type', 'waste_type']:
            if key in extracted:
                state[key] = extracted[key]
