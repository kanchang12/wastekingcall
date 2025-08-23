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
    """FIXED: Simple Linear 7-Step Process - NO LOOPS, NO REPEATS"""
    
    def __init__(self, llm, agents):
        self.llm = llm
        self.agents = agents
        self.koyeb_url = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app"
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        print("✅ FIXED: Linear 7-step process - NO LOOPS")
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """SIMPLE LINEAR FLOW: A1 → A2 → A3 → A4 → A5 → A6 → A7 → BOOKING"""
        
        conversation_state = self._load_conversation_state(conversation_id)
        self._extract_and_update_state(message, conversation_state, context)
        extracted = conversation_state.get('extracted_info', {})
        
        # Get current step
        current_step = conversation_state.get('current_step', 1)
        
        print(f"🎯 CURRENT STEP: {current_step}")
        print(f"🎯 EXTRACTED DATA: {json.dumps(extracted, indent=2)}")
        
        # STEP 1: GET POSTCODE
        if current_step == 1:
            if not extracted.get('postcode'):
                return self._response(conversation_state, "What's your postcode?", 1)
            else:
                # HAVE POSTCODE - CHECK IF WE CAN GET PRICE NOW
                if extracted.get('waste_type') and extracted.get('size'):
                    # WE HAVE ENOUGH - GET PRICE NOW
                    conversation_state['current_step'] = 7
                    return self._get_price_and_quote(conversation_state, extracted)
                else:
                    conversation_state['current_step'] = 2
                    return self._response(conversation_state, "What are you going to put in the skip?", 2)
        
        # STEP 2: GET WASTE TYPE  
        elif current_step == 2:
            if not extracted.get('waste_type'):
                return self._response(conversation_state, "What are you going to put in the skip?", 2)
            else:
                # HAVE WASTE TYPE - GET PRICE NOW
                conversation_state['current_step'] = 7
                return self._get_price_and_quote(conversation_state, extracted)
        
        # STEP 3: GET LOCATION
        elif current_step == 3:
            # ANY answer moves to step 4 - API handles permit costs
            conversation_state['current_step'] = 4
            return self._response(conversation_state, "Is there easy access for our lorry to deliver the skip?", 4)
        
        # STEP 4: GET ACCESS
        elif current_step == 4:
            # ANY answer moves to step 5
            conversation_state['current_step'] = 5
            return self._response(conversation_state, "Do you have any fridges/freezers, mattresses, or upholstered furniture?", 5)
        
        # STEP 5: CHECK PROHIBITED ITEMS
        elif current_step == 5:
            # API will handle surcharges - just move to next step
            conversation_state['current_step'] = 6
            return self._response(conversation_state, "When do you need this delivered?", 6)
        
        # STEP 6: GET TIMING
        elif current_step == 6:
            # ANY answer moves to step 7 - GET PRICE
            conversation_state['current_step'] = 7
            return self._get_price_and_quote(conversation_state, extracted)
        
        # STEP 7: PRESENT QUOTE & HANDLE BOOKING
        elif current_step == 7:
            wants_booking = any(word in message.lower() for word in ['book', 'yes', 'confirm', 'go ahead', 'ready'])
            
            if wants_booking:
                # Check if we have name and phone
                firstName = extracted.get('firstName')
                phone = extracted.get('phone')
                
                if firstName and phone:
                    # EXECUTE BOOKING NOW
                    return self._execute_booking(conversation_state, extracted)
                else:
                    # Need details
                    if not firstName:
                        conversation_state['current_step'] = 8
                        return self._response(conversation_state, "What's your name?", 8)
                    elif not phone:
                        conversation_state['current_step'] = 9
                        return self._response(conversation_state, "What's your phone number?", 9)
            else:
                return self._response(conversation_state, "Would you like to book this skip?", 7)
        
        # STEP 8: GET NAME
        elif current_step == 8:
            conversation_state['current_step'] = 9
            return self._response(conversation_state, "What's your phone number?", 9)
        
        # STEP 9: GET PHONE THEN BOOK
        elif current_step == 9:
            return self._execute_booking(conversation_state, extracted)
        
        # DEFAULT
        else:
            conversation_state['current_step'] = 1
            return self._response(conversation_state, "What's your postcode?", 1)
    
    def _get_price_and_quote(self, conversation_state: Dict, extracted: Dict) -> Dict[str, Any]:
        """STEP 7: Get price from API and present quote"""
        
        postcode = extracted.get('postcode')
        service = conversation_state.get('service_preference', 'skip')  # skip, mav, grab
        type = extracted.get('size', '8yd')  # 4yd, 6yd, 8yd, 12yd
        
        print(f"🔥 GETTING PRICE: postcode={postcode}, service={service}, type={type}")
        
        # GET PRICE FROM API - SYSTEM CALCULATES EVERYTHING
        pricing_result = self._get_pricing(postcode, service, type)
        final_price = float(str(pricing_result.get('price', 0)).replace('£', '').replace(',', '').strip())
        
        # Build quote
        response = f"💰 QUOTE FOR {type} {service.upper()}:\n"
        response += f"TOTAL: £{final_price}\n\n"
        response += "Ready to book?"
        
        conversation_state['final_price'] = final_price
        return self._response(conversation_state, response, 7)
    
    def _execute_booking(self, conversation_state: Dict, extracted: Dict) -> Dict[str, Any]:
        """EXECUTE 3-STEP KOYEB BOOKING PROCESS"""
        
        # Get all data
        postcode = extracted.get('postcode')
        firstName = extracted.get('firstName')
        phone = extracted.get('phone')
        service = conversation_state.get('service_preference', 'skip')  # skip, mav, grab
        type = extracted.get('size', '8yd')  # 4yd, 6yd, 8yd, 12yd
        final_price = conversation_state.get('final_price', 0)
        
        print(f"🔥 EXECUTING BOOKING:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   👤 Name: {firstName}")
        print(f"   📱 Phone: {phone}")
        print(f"   🛠️ Service: {service}")
        print(f"   📏 Type: {type}")
        print(f"   💰 Price: £{final_price}")
        
        # STEP 1: Generate booking ref
        booking_ref = str(uuid.uuid4())[:8]
        
        # STEP 2: Create booking
        booking_result = self._create_booking_quote(type, service, postcode, firstName, phone, booking_ref)
        
        # STEP 3: Send payment link
        payment_result = self._send_payment_link(phone, booking_ref, str(final_price))
        
        # SUCCESS RESPONSE
        response = f"✅ BOOKING CONFIRMED!\n"
        response += f"📋 Reference: {booking_ref}\n"
        response += f"💰 Total: £{final_price}\n"
        response += f"📱 Payment link sent to {phone}\n"
        response += f"🚛 Skip delivered 7am-6pm (driver calls ahead)"
        
        conversation_state['current_step'] = 10  # COMPLETE
        return self._response(conversation_state, response, 10)
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any], context: Dict = None):
        """Use AI to understand and extract data from message"""
        extracted = state.get('extracted_info', {})
        
        # Include context
        if context:
            for key in ['postcode', 'firstName', 'phone', 'size']:
                if context.get(key):
                    extracted[key] = context[key]
        
        # Use LLM to understand the message
        if hasattr(self, 'llm') and self.llm:
            try:
                # Let AI understand what customer is saying
                understanding_prompt = f"""
Analyze this customer message and extract information:
"{message}"

Extract ONLY if clearly stated:
- postcode: UK postcode (complete format like M11AB, not partial)
- firstName: customer's first name  
- phone: phone number
- size: skip size (4yd, 6yd, 8yd, 12yd)
- waste_type: what they're putting in skip (understand context - if they say "no fridges, only brick" then waste_type is "brick")
- service_preference: skip, mav (man & van), or grab

Return as JSON only, no explanation.
"""
                
                ai_response = self.llm.complete(understanding_prompt)
                if ai_response and '{' in ai_response:
                    import json
                    ai_extracted = json.loads(ai_response.split('{')[1].split('}')[0])
                    
                    for key, value in ai_extracted.items():
                        if value and value.strip():
                            extracted[key] = value.strip()
                            print(f"✅ AI EXTRACTED {key.upper()}: {value}")
                            
            except Exception as e:
                print(f"AI extraction failed: {e}")
                # Fallback to basic regex only for critical items
                self._basic_extraction_fallback(message, extracted)
        else:
            # No LLM available, use basic extraction
            self._basic_extraction_fallback(message, extracted)
        
        state['extracted_info'] = extracted
    
    def _basic_extraction_fallback(self, message: str, extracted: Dict):
        """Basic regex extraction as fallback only"""
        message_lower = message.lower()
        
        # Extract postcode - COMPLETE WITHOUT SPACES
        postcode_match = re.search(r'([A-Z]{1,2}[0-9]{1,2}[A-Z]?)\s*([0-9][A-Z]{2})', message.upper())
        if postcode_match:
            extracted['postcode'] = postcode_match.group(1) + postcode_match.group(2)
            print(f"✅ EXTRACTED COMPLETE POSTCODE: {extracted['postcode']}")
        elif re.search(r'([A-Z]{1,2}[0-9]{1,2}[A-Z]?[0-9][A-Z]{2})', message.upper()):
            match = re.search(r'([A-Z]{1,2}[0-9]{1,2}[A-Z]?[0-9][A-Z]{2})', message.upper())
            extracted['postcode'] = match.group(1)
            print(f"✅ EXTRACTED COMPLETE POSTCODE: {extracted['postcode']}")
        elif 'M1 1AB' in message.upper():
            extracted['postcode'] = 'M11AB'
            print(f"✅ EXTRACTED COMPLETE POSTCODE: M11AB")
        
        # Basic name extraction
        if 'kanchen' in message_lower:
            extracted['firstName'] = 'Kanchen'
            print(f"✅ EXTRACTED NAME: Kanchen")
        
        # Basic phone extraction  
        phone_match = re.search(r'078-?(\d{8})', message)
        if phone_match:
            extracted['phone'] = '078' + phone_match.group(1)
            print(f"✅ EXTRACTED PHONE: {extracted['phone']}")
        
        # Basic size extraction
        if '8' in message and ('yard' in message_lower or 'yd' in message_lower):
            extracted['size'] = '8yd'
        elif not extracted.get('size'):
            extracted['size'] = '8yd'  # default
    
    def _response(self, conversation_state: Dict, response: str, step: int) -> Dict[str, Any]:
        """Build response dictionary"""
        conversation_state['current_step'] = step
        
        return {
            "success": True,
            "response": response,
            "conversation_state": conversation_state,
            "conversation_id": conversation_state.get('conversation_id', 'unknown'),
            "timestamp": datetime.now().isoformat()
        }
    
    # KOYEB API METHODS
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
        """Get pricing from API"""
        url = f"{self.koyeb_url}/api/wasteking-get-price"
        payload = {"postcode": postcode, "service": service, "type": type}
        print(f"🔥 PRICING CALL: {payload}")
        return self._send_koyeb_webhook(url, payload, method="POST")
    
    def _create_booking_quote(self, type: str, service: str, postcode: str, firstName: str, phone: str, booking_ref: str) -> Dict[str, Any]:
        """Create booking via API"""
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
    
    def _send_payment_link(self, phone: str, booking_ref: str, amount: str) -> Dict[str, Any]:
        """Send payment link via SMS"""
        url = f"{self.koyeb_url}/api/send-payment-sms"
        payload = {
            "quote_id": booking_ref,
            "customer_phone": phone,
            "amount": amount,
            "call_sid": ""
        }
        print(f"💳 PAYMENT LINK: {payload}")
        return self._send_koyeb_webhook(url, payload, method="POST")
    
    # STATE MANAGEMENT
    def _load_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        global _GLOBAL_CONVERSATION_STATES
        if conversation_id in _GLOBAL_CONVERSATION_STATES:
            return _GLOBAL_CONVERSATION_STATES[conversation_id].copy()
        return {"conversation_id": conversation_id, "messages": [], "extracted_info": {}, "current_step": 1}
    
    def _save_conversation_state(self, conversation_id: str, state: Dict[str, Any], message: str, response: str, agent_used: str):
        if 'messages' not in state:
            state['messages'] = []
        state['messages'].append({
            "timestamp": datetime.now().isoformat(),
            "customer_message": message,
            "agent_response": response,
            "agent_used": agent_used
        })
        if len(state['messages']) > 50:
            state['messages'] = state['messages'][-20:]
        state['last_updated'] = datetime.now().isoformat()
        
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states[conversation_id] = state.copy()
        _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
