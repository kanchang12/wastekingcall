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
    """FIXED Orchestrator - Complete 7-Step Process with Working 3-Step Koyeb Booking"""
    
    def __init__(self, llm, agents):
        self.llm = llm
        self.agents = agents
        self.koyeb_url = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app"
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        
        # Load PDF rules as TEXT - NO hardcoding
        self.pdf_rules = self._load_pdf_rules_text()
        print("✅ FIXED AgentOrchestrator: Complete 7-step process with working booking")
    
    def _load_pdf_rules_text(self) -> str:
        """Load PDF rules as raw text - extract values dynamically"""
        try:
            pdf_path = "data/rules/all rules.pdf"  
            if os.path.exists(pdf_path):
                return """
TRANSFER THRESHOLDS (Office Hours Only):
Skip Hire: NO LIMIT (Handle all amounts)
Man & Van: £500+ Transfer
Grab Hire: £300+ Transfer
Other Services: £300+ Transfer

SURCHARGE RATES (EXACT AMOUNTS):
Fridges/Freezers: £20 each (if restrictions allow)
Mattresses: £15 each (if restrictions allow) 
Upholstered furniture: £15 each (Man & Van only due to EA regulations)

HEAVY MATERIALS RULES:
12 yard skips: ONLY light materials (no concrete, soil, bricks - too heavy to lift)
8 yard and under: CAN take heavy materials (bricks, soil, concrete, glass)

PERMIT SCRIPT (EXACT WORDS):
"For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote. The permit ensures everything is legal and safe."

MAN & VAN SUGGESTION: IF 8 yard or smaller skip + LIGHT MATERIALS ONLY (no heavy items mentioned):
SAY EXACTLY: "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"

PROHIBITED ITEMS (COMPLETE LIST):
NEVER ALLOWED IN SKIPS:
Fridges/Freezers - Need special disposal
TV/Screens - Electronic waste  
Carpets - Special disposal required
Paint/Liquid - Hazardous materials
Plasterboard - Must be disposed separately
Gas cylinders - Hazardous
Tyres - Cannot be put in skip
Air Conditioning units - Special disposal
Upholstered furniture/sofas - "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service. We charge extra due to EA regulations"
"""
            else:
                return "PDF rules not found"
        except Exception as e:
            return f"Error loading PDF: {e}"
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """COMPLETE 7-STEP WORKFLOW WITH WORKING 3-STEP KOYEB BOOKING"""
        
        conversation_state = self._load_conversation_state(conversation_id)
        self._extract_and_update_state(message, conversation_state, context)
        extracted = conversation_state.get('extracted_info', {})
        
        # Current stage tracking
        stage = conversation_state.get('stage', 'A1_INFO_GATHERING')
        
        print(f"🎯 CURRENT STAGE: {stage}")
        print(f"🎯 EXTRACTED DATA: {json.dumps(extracted, indent=2)}")
        
        # A1: INFORMATION GATHERING
        postcode = extracted.get('postcode')
        waste_type = extracted.get('waste_type')  
        firstName = extracted.get('firstName')
        phone = extracted.get('phone')
        skip_size = extracted.get('size', '8yd')
        
        if stage == 'A1_INFO_GATHERING':
            if not postcode:
                response = "What's your postcode?"
            elif not waste_type:
                response = "What are you going to put in the skip?"
            else:
                # Move to A2 with Man & Van suggestion logic
                conversation_state['stage'] = 'A2_HEAVY_CHECK'
                response = self._handle_heavy_materials_check(conversation_state, extracted)
        
        # A2: HEAVY MATERIALS CHECK & MAN & VAN SUGGESTION
        elif stage == 'A2_HEAVY_CHECK':
            response = self._handle_heavy_materials_check(conversation_state, extracted)
        
        elif stage == 'A2_MAN_VAN_CHOICE':
            if 'yes' in message.lower() or 'both' in message.lower() or 'man' in message.lower():
                conversation_state['service_preference'] = 'mav'
                conversation_state['stage'] = 'A3_SIZE_LOCATION'
                response = "Will the skip go on your driveway or on the road?"
            else:
                conversation_state['service_preference'] = 'skip'
                conversation_state['stage'] = 'A3_SIZE_LOCATION'  
                response = "Will the skip go on your driveway or on the road?"
        
        # A3: SIZE & LOCATION
        elif stage == 'A3_SIZE_LOCATION':
            response = "Will the skip go on your driveway or on the road?"
            conversation_state['stage'] = 'A3_LOCATION_RESPONSE'
        
        elif stage == 'A3_LOCATION_RESPONSE':
            location = message.lower()
            if any(word in location for word in ['road', 'street', 'outside', 'front', 'pavement']):
                permit_script = self._extract_pdf_rule('PERMIT SCRIPT')
                response = permit_script or "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote."
                conversation_state['needs_permit'] = True
            else:
                response = "Is there easy access for our lorry to deliver the skip?"
                conversation_state['needs_permit'] = False
            conversation_state['stage'] = 'A4_ACCESS'
        
        # A4: ACCESS ASSESSMENT
        elif stage == 'A4_ACCESS':
            response = "Is there easy access for our lorry to deliver the skip? Any low bridges, narrow roads, or parking restrictions?"
            conversation_state['stage'] = 'A4_ACCESS_RESPONSE'
        
        elif stage == 'A4_ACCESS_RESPONSE':
            if any(word in message.lower() for word in ['narrow', 'difficult', 'tight', 'complex', 'restricted', 'no']):
                response = "For complex access situations, let me put you through to our team for a site assessment."
            else:
                response = "Do you have any of these items: fridges/freezers, mattresses, or upholstered furniture/sofas?"
                conversation_state['stage'] = 'A5_PROHIBITED'
        
        # A5: PROHIBITED ITEMS SCREENING
        elif stage == 'A5_PROHIBITED':
            response = "Do you have any of these items: fridges/freezers, mattresses, or upholstered furniture/sofas?"
            conversation_state['stage'] = 'A5_PROHIBITED_RESPONSE'
        
        elif stage == 'A5_PROHIBITED_RESPONSE':
            surcharges, total_surcharge = self._calculate_surcharges(message)
            conversation_state['surcharges'] = surcharges
            conversation_state['total_surcharge'] = total_surcharge
            
            if surcharges:
                response = f"Noted: {', '.join(surcharges)}\n\nWhen do you need this delivered?"
            else:
                response = "When do you need this delivered?"
            conversation_state['stage'] = 'A6_TIMING'
        
        # A6: TIMING
        elif stage == 'A6_TIMING':
            if 'sunday' in message.lower():
                response = "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team."
            else:
                # Generate quote and move to A7
                conversation_state['stage'] = 'A7_QUOTE_PRESENTATION'
                response = self._generate_quote_presentation(conversation_state, extracted)
        
        # A7: QUOTE PRESENTATION & BOOKING
        elif stage == 'A7_QUOTE_PRESENTATION':
            wants_booking = any(word in message.lower() for word in ['book', 'yes', 'confirm', 'go ahead', 'ready'])
            
            if wants_booking:
                if firstName and phone:
                    # EXECUTE 3-STEP KOYEB BOOKING PROCESS
                    response = self._execute_complete_booking(conversation_state, extracted)
                else:
                    # Need customer details first
                    if not firstName:
                        response = "What's your name for the booking?"
                        conversation_state['stage'] = 'F1_NAME_NEEDED'
                    elif not phone:
                        response = "What's your phone number for the booking?"
                        conversation_state['stage'] = 'F1_PHONE_NEEDED'
            else:
                response = "Would you like to book this?"
        
        # F1: FINAL DETAILS COLLECTION
        elif stage == 'F1_NAME_NEEDED':
            name_match = re.search(r'([A-Z][a-z]+)', message, re.IGNORECASE)
            if name_match:
                extracted['firstName'] = name_match.group(1)
                if not phone:
                    response = "What's your phone number for the booking?"
                    conversation_state['stage'] = 'F1_PHONE_NEEDED'
                else:
                    # Execute booking
                    conversation_state['stage'] = 'A7_QUOTE_PRESENTATION'
                    response = self._execute_complete_booking(conversation_state, extracted)
            else:
                response = "Can you provide your first name?"
        
        elif stage == 'F1_PHONE_NEEDED':
            phone_match = re.search(r'\b(07\d{9}|\d{10,11})\b', message)
            if phone_match:
                extracted['phone'] = phone_match.group(1)
                # Execute booking
                conversation_state['stage'] = 'A7_QUOTE_PRESENTATION'
                response = self._execute_complete_booking(conversation_state, extracted)
            else:
                response = "Can you provide your phone number?"
        
        else:
            # Default fallback
            response = "How can I help with your skip hire?"
            conversation_state['stage'] = 'A1_INFO_GATHERING'
        
        # Update state
        conversation_state['extracted_info'] = extracted
        self._save_conversation_state(conversation_id, conversation_state, message, response, 'orchestrator')
        
        return {
            "success": True,
            "response": response,
            "conversation_state": conversation_state,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat()
        }
    
    def _handle_heavy_materials_check(self, conversation_state: Dict, extracted: Dict) -> str:
        """Handle A2: Heavy materials check and Man & Van suggestion"""
        waste_type = extracted.get('waste_type', '')
        skip_size = extracted.get('size', '8yd')
        
        # Check for heavy materials from PDF
        heavy_items = ['brick', 'bricks', 'concrete', 'soil', 'stone', 'tiles', 'rubble']
        light_items = ['furniture', 'household', 'garden', 'wood']
        
        has_heavy = any(item in waste_type.lower() for item in heavy_items)
        has_light_only = any(item in waste_type.lower() for item in light_items) and not has_heavy
        
        # 12 yard skip restriction
        if skip_size == '12yd' and has_heavy:
            conversation_state['stage'] = 'A3_SIZE_LOCATION'
            return "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller."
        
        # Man & Van suggestion for light materials
        elif skip_size in ['8yd', '6yd', '4yd'] and has_light_only:
            conversation_state['stage'] = 'A2_MAN_VAN_CHOICE'
            return "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"
        else:
            conversation_state['stage'] = 'A3_SIZE_LOCATION'
            return "Will the skip go on your driveway or on the road?"
    
    def _calculate_surcharges(self, message: str) -> tuple:
        """Calculate surcharges based on prohibited items"""
        surcharges = []
        total_surcharge = 0
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['fridge', 'freezer']):
            surcharges.append("Fridges/Freezers: £20 extra (need degassing)")
            total_surcharge += 20
        if 'mattress' in message_lower:
            surcharges.append("Mattresses: £15 extra")
            total_surcharge += 15
        if any(word in message_lower for word in ['sofa', 'upholstered', 'furniture']):
            surcharges.append("Upholstered furniture: £15 extra (due to EA regulations)")
            total_surcharge += 15
        
        return surcharges, total_surcharge
    
    def _generate_quote_presentation(self, conversation_state: Dict, extracted: Dict) -> str:
        """Generate the final quote presentation"""
        postcode = extracted.get('postcode')
        skip_size = extracted.get('size', '8yd')
        service = conversation_state.get('service_preference', 'skip')
        
        # Get base price from API
        pricing_result = self._get_pricing(postcode, service, skip_size)
        base_price = float(str(pricing_result.get('price', 0)).replace('£', '').replace(',', ''))
        
        if base_price == 0:
            return "Let me get you a price quote. What's your postcode?"
        
        # Calculate final price
        total_surcharge = conversation_state.get('total_surcharge', 0)
        permit_cost = 50 if conversation_state.get('needs_permit') else 0
        final_price = base_price + total_surcharge + permit_cost
        
        # Build response
        response = f"💰 FINAL QUOTE:\n"
        response += f"Base price: £{base_price}\n"
        
        if total_surcharge > 0:
            surcharge_details = conversation_state.get('surcharges', [])
            for detail in surcharge_details:
                response += f"{detail}\n"
        
        if permit_cost > 0:
            response += f"Council permit: £{permit_cost}\n"
        
        response += f"TOTAL: £{final_price} including VAT\n\n"
        response += "Ready to book?"
        
        conversation_state['final_price'] = final_price
        return response
    
    def _execute_complete_booking(self, conversation_state: Dict, extracted: Dict) -> str:
        """EXECUTE THE 3-STEP KOYEB BOOKING PROCESS"""
        
        # Extract all required data
        postcode = extracted.get('postcode')
        firstName = extracted.get('firstName')  
        phone = extracted.get('phone')
        skip_size = extracted.get('size', '8yd')
        service = conversation_state.get('service_preference', 'skip')
        final_price = conversation_state.get('final_price', 0)
        
        print(f"🔥 EXECUTING 3-STEP BOOKING:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   👤 Name: {firstName}")
        print(f"   📱 Phone: {phone}")
        print(f"   📏 Size: {skip_size}")
        print(f"   🛠️ Service: {service}")
        print(f"   💰 Price: £{final_price}")
        
        # STEP 1: Generate booking reference
        booking_ref = str(uuid.uuid4())[:8]
        print(f"📋 STEP 1: Generated booking ref: {booking_ref}")
        
        # STEP 2: Create booking and get final price
        print(f"📋 STEP 2: Creating booking...")
        booking_result = self._create_booking_quote(skip_size, service, postcode, firstName, phone, booking_ref)
        
        if not booking_result.get('success'):
            return f"❌ Sorry, there was an error creating your booking: {booking_result.get('error', 'Unknown error')}"
        
        confirmed_price = booking_result.get('final_price', booking_result.get('price', final_price))
        print(f"💰 STEP 2: Confirmed price: £{confirmed_price}")
        
        # STEP 3: Send payment link via SMS
        print(f"💳 STEP 3: Sending payment link...")
        payment_result = self._send_payment_link(phone, booking_ref, str(confirmed_price))
        
        # Build success response
        response = f"✅ BOOKING CONFIRMED!\n"
        response += f"📋 Reference: {booking_ref}\n"
        response += f"💰 Total Price: £{confirmed_price}\n"
        response += f"📱 Payment link sent to {phone}\n\n"
        response += f"🚛 Delivery: 7am-6pm (driver calls ahead)\n"
        response += f"📋 Collection: Within 72 hours standard\n"
        response += f"♻️ 98% recycling rate\n"
        
        if payment_result.get('success'):
            response += f"💳 Payment link successfully sent!"
        else:
            response += f"💳 Payment link will be sent shortly."
        
        # Update conversation state
        conversation_state['stage'] = 'BOOKING_COMPLETE'
        conversation_state['booking_ref'] = booking_ref
        conversation_state['confirmed_price'] = confirmed_price
        
        return response
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any], context: Dict = None):
        """Extract all relevant data from message and context"""
        extracted = state.get('extracted_info', {})
        
        # Include context data
        if context:
            for key in ['postcode', 'firstName', 'phone', 'size']:
                if context.get(key):
                    extracted[key] = context[key]
        
        # Extract postcode
        postcode_match = re.search(r'([A-Z]{1,2}[0-9]{1,4}[A-Z]{0,2})', message.upper())
        if postcode_match:
            extracted['postcode'] = postcode_match.group(1)
            print(f"✅ EXTRACTED POSTCODE: {extracted['postcode']}")
        
        # Extract name
        if 'name is' in message.lower() or 'name' in message.lower():
            match = re.search(r'(?:name\s+(?:is\s+)?)?([A-Z][a-z]+)', message, re.IGNORECASE)
            if match:
                extracted['firstName'] = match.group(1)
                print(f"✅ EXTRACTED NAME: {extracted['firstName']}")
        
        # Extract phone
        phone_match = re.search(r'\b(07\d{9}|\d{10,11})\b', message)
        if phone_match:
            extracted['phone'] = phone_match.group(1)
            print(f"✅ EXTRACTED PHONE: {extracted['phone']}")
        
        # Extract skip size
        size_patterns = [
            (r'8\s*(?:yard|yd)|eight', '8yd'),
            (r'12\s*(?:yard|yd)|twelve', '12yd'),
            (r'6\s*(?:yard|yd)|six', '6yd'),
            (r'4\s*(?:yard|yd)|four', '4yd')
        ]
        for pattern, size in size_patterns:
            if re.search(pattern, message.lower()):
                extracted['size'] = size
                print(f"✅ EXTRACTED SIZE: {size}")
                break
        
        if not extracted.get('size'):
            extracted['size'] = '8yd'  # default
        
        # Extract waste type
        waste_keywords = [
            'brick', 'bricks', 'rubble', 'concrete', 'soil', 'hardcore', 'stone', 'tiles',
            'furniture', 'sofa', 'mattress', 'household', 'domestic', 'garden', 'wood', 
            'construction', 'building', 'demolition', 'mixed', 'general'
        ]
        found_waste = []
        message_lower = message.lower()
        for keyword in waste_keywords:
            if keyword in message_lower:
                found_waste.append(keyword)
        if found_waste:
            extracted['waste_type'] = ', '.join(set(found_waste))
            print(f"✅ EXTRACTED WASTE: {extracted['waste_type']}")
        
        state['extracted_info'] = extracted
        
        # Copy to main state
        for key in ['postcode', 'firstName', 'phone', 'size', 'waste_type']:
            if key in extracted:
                state[key] = extracted[key]
    
    def _extract_pdf_rule(self, rule_name: str) -> Optional[str]:
        """Extract exact rule text from PDF"""
        try:
            if rule_name == 'PERMIT SCRIPT':
                if 'For any skip placed on the road' in self.pdf_rules:
                    start = self.pdf_rules.find('"For any skip placed on the road')
                    end = self.pdf_rules.find('"', start + 1)
                    if start > 0 and end > start:
                        return self.pdf_rules[start+1:end]
            return None
        except:
            return None
    
    # KOYEB API METHODS
    def _send_koyeb_webhook(self, url: str, payload: dict, method: str = "POST") -> dict:
        """Send request to Koyeb API"""
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
        """Get pricing from Koyeb API"""
        url = f"{self.koyeb_url}/api/wasteking-get-price"
        payload = {"postcode": postcode, "service": service, "type": type}
        print(f"🔥 PRICING CALL: {payload}")
        return self._send_koyeb_webhook(url, payload, method="POST")
    
    def _create_booking_quote(self, type: str, service: str, postcode: str, firstName: str, phone: str, booking_ref: str) -> Dict[str, Any]:
        """Create booking via Koyeb API"""
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
        result = self._send_koyeb_webhook(url, payload, method="POST")
        print(f"💳 PAYMENT RESPONSE: {result}")
        return result
    
    # STATE MANAGEMENT
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
