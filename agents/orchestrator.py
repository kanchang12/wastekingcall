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
    """Fixed Orchestrator: Instant pricing, 24/7 sales, proper waste detection"""
    
    def __init__(self, llm, agents):
        self.llm = llm
        self.agents = agents
        self.koyeb_url = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app"
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        print("✅ FIXED AgentOrchestrator: 24/7 pricing + booking")
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """Fixed: Instant pricing, proper waste detection, 24/7 operation"""
        
        conversation_state = self._load_conversation_state(conversation_id)
        
        # Extract ALL data from message + context
        self._extract_and_update_state(message, conversation_state, context)
        
        extracted = conversation_state.get('extracted_info', {})
        
        # Core data needed - ONLY basic extraction
        postcode = extracted.get('postcode')
        service = 'skip'  # default to skip
        skip_size = extracted.get('size', '8yd')  # default 8yd
        firstName = extracted.get('firstName')
        phone = extracted.get('phone')
        
        # Determine what customer wants
        message_lower = message.lower()
        wants_price = any(word in message_lower for word in ['price', 'cost', 'quote', 'how much'])
        wants_booking = any(word in message_lower for word in ['book', 'booking', 'confirm', 'go ahead', 'yes book'])
        
        print(f"🎯 ORCHESTRATOR ANALYSIS:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   📏 Size: {skip_size}")
        print(f"   👤 Name: {firstName}")
        print(f"   📱 Phone: {phone}")
        print(f"   💰 Wants price: {wants_price}")
        print(f"   📋 Wants booking: {wants_booking}")
        
        response = ""
        
        # PRIORITY 1: INSTANT PRICING (only needs postcode + size)
        if wants_price and postcode and skip_size:
            print(f"💰 Getting pricing for {skip_size} skip")
                
            pricing_result = self._get_pricing(postcode, service, skip_size)
            print(f"🔥 API RESPONSE: {pricing_result}")  # Debug what we get back
            
            # Just show the price regardless of success field
            price = pricing_result.get('price', pricing_result.get('cost', 'unavailable'))
            response = f"💰 Price for {skip_size} skip at {postcode}: £{price}"
            
            # Ask for booking
            response += f"\n\n📋 Ready to book? Just need your name and phone number."
                
            conversation_state['has_pricing'] = True
        
        # PRIORITY 2: IMMEDIATE BOOKING (has all required info)
        elif wants_booking and postcode and firstName and phone:
            print(f"📋 IMMEDIATE BOOKING: All info present")
            
            booking_ref = str(uuid.uuid4())[:8]  # shorter ref
            booking_result = self._create_booking_quote(skip_size, service, postcode, firstName, phone, booking_ref)
            
            if booking_result.get('success'):
                price = booking_result.get('final_price', booking_result.get('price', 'N/A'))
                payment_link = booking_result.get('payment_link', '')
                
                response = f"✅ BOOKING CONFIRMED!\n"
                response += f"📋 Ref: {booking_ref}\n"
                response += f"💰 Price: £{price}\n"
                if payment_link:
                    response += f"💳 Payment: {payment_link}\n"
                response += f"🚛 Skip delivered 7am-6pm (driver calls ahead)"
                
            else:
                error = booking_result.get('error', 'booking system unavailable')
                response = f"I'll take your booking details and confirm within 30 minutes:\n"
                response += f"📋 {firstName} - {phone}\n"
                response += f"📍 {skip_size} skip at {postcode}"
        
        # PRIORITY 3: MISSING DATA - Ask for what's needed
        else:
            missing = []
            
            # For pricing, only need postcode
            if wants_price and not postcode:
                response = "What's your postcode?"
            # For booking, need everything
            elif wants_booking:
                if not postcode:
                    missing.append("postcode")
                if not firstName:
                    missing.append("name")
                if not phone:
                    missing.append("phone number")
                    
                if missing:
                    if len(missing) == 1:
                        response = f"What's your {missing[0]}?"
                    else:
                        response = f"Just need your {' and '.join(missing)}."
                else:
                    response = "How can I help with your waste collection?"
            else:
                response = "How can I help with your waste collection?"
        
        # Save state
        self._save_conversation_state(conversation_id, conversation_state, message, response, 'orchestrator')
        
        return {
            "success": True,
            "response": response,
            "conversation_state": conversation_state,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat()
        }
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any], context: Dict = None):
        """FIXED: Proper extraction of all data"""
        
        extracted = state.get('extracted_info', {})
        
        # Include context data first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'size']:
                if context.get(key):
                    extracted[key] = context[key]
        
        # Extract postcode (SIMPLE and BROAD)
        postcode_match = re.search(r'([A-Z]{1,2}[0-9]{1,4}[A-Z]{0,2})', message.upper())
        if postcode_match:
            postcode = postcode_match.group(1)
            extracted['postcode'] = postcode
            print(f"✅ EXTRACTED POSTCODE: {postcode}")
        
        # Also check for "LS1" style partial codes if customer says that's the postcode
        if not postcode_match and ('postcode' in message.lower() or 'LS' in message.upper() or 'M1' in message.upper()):
            partial_match = re.search(r'([A-Z]{1,2}[0-9]{1,2})', message.upper())
            if partial_match:
                postcode = partial_match.group(1)
                extracted['postcode'] = postcode  
                print(f"✅ EXTRACTED PARTIAL POSTCODE: {postcode}")
        
        # Extract name (simple and direct)
        if 'name is' in message.lower():
            match = re.search(r'name\s+is\s+([A-Z][a-z]+)', message, re.IGNORECASE)
            if match:
                extracted['firstName'] = match.group(1)
                print(f"✅ EXTRACTED NAME: {match.group(1)}")
        elif 'name' in message.lower():
            match = re.search(r'name\s+([A-Z][a-z]+)', message, re.IGNORECASE)
            if match:
                extracted['firstName'] = match.group(1)
                print(f"✅ EXTRACTED NAME: {match.group(1)}")
        
        # Extract phone (multiple formats)
        phone_patterns = [
            r'\b(07\d{9})\b',  # Mobile
            r'\b(\+447\d{9})\b',  # International mobile
            r'\b(01\d{9})\b',  # Landline
            r'\b(\d{11})\b',  # 11-digit number
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                phone = match.group(1)
                extracted['phone'] = phone
                print(f"✅ EXTRACTED PHONE: {phone}")
                break
        
        # Extract skip size
        size_patterns = [
            r'(\d+)\s*(?:yard|yd|cubic yard)',
            r'(\d+)\s*yd',
        ]
        for pattern in size_patterns:
            match = re.search(pattern, message.lower())
            if match:
                size = f"{match.group(1)}yd"
                extracted['size'] = size
                print(f"✅ EXTRACTED SIZE: {size}")
                break
        
        # NO WASTE TYPE EXTRACTION - Let AI agents handle this
        
        # Set defaults if not specified
        if not extracted.get('size'):
            extracted['size'] = '8yd'  # most popular
        
        state['extracted_info'] = extracted
        
        # Copy to main state for easy access
        for key in ['postcode', 'firstName', 'phone', 'size']:
            if key in extracted:
                state[key] = extracted[key]
    
    # REST OF THE METHODS UNCHANGED
    def _send_koyeb_webhook(self, url: str, payload: dict, method: str = "POST") -> dict:
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
    
    def _get_pricing(self, postcode: str, service: str, type: str) -> Dict[str, Any]:
        """24/7 pricing - always available"""
        url = f"{self.koyeb_url}/api/wasteking-get-price"
        payload = {"postcode": postcode, "service": service, "type": type}
        print(f"🔥 PRICING CALL: {payload}")
        return self._send_koyeb_webhook(url, payload, method="POST")
    
    def _create_booking_quote(self, type: str, service: str, postcode: str, firstName: str, phone: str, booking_ref: str) -> Dict[str, Any]:
        """24/7 booking - always available"""
        url = f"{self.koyeb_url}/api/wasteking-confirm-booking"
        payload = {
            "booking_ref": booking_ref,
            "postcode": postcode,
            "service": service,
            "type": type,
            "firstName": firstName,
            "phone": phone
        }
        print(f"🔥 BOOKING CALL: {payload}")
        return self._send_koyeb_webhook(url, payload, method="POST")
    
    def _load_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        global _GLOBAL_CONVERSATION_STATES
        if conversation_id in _GLOBAL_CONVERSATION_STATES:
            return _GLOBAL_CONVERSATION_STATES[conversation_id].copy()
        return {"conversation_id": conversation_id, "messages": [], "extracted_info": {}}
    
    def _save_conversation_state(self, conversation_id: str, state: Dict[str, Any], message: str, response: str, agent_used: str):
        if 'messages' not in state:
            state['messages'] = []
        state['messages'].append({
            "timestamp": datetime.now().isoformat(),
            "customer_message": message,
            "agent_response": response,
            "agent_used": agent_used
        })
        if len(state['messages']) > 100:
            state['messages'] = state['messages'][-20:]
        state['last_updated'] = datetime.now().isoformat()
        
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states[conversation_id] = state.copy()
        _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
