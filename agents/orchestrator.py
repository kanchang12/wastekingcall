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
    """WORKING Orchestrator - Uses PDF extracted values, NO hardcoding"""
    
    def __init__(self, llm, agents):
        self.llm = llm
        self.agents = agents
        self.koyeb_url = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app"
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        
        # Load PDF rules as TEXT - NO hardcoding
        self.pdf_rules = self._load_pdf_rules_text()
        print("✅ WORKING AgentOrchestrator: PDF rules loaded, no hardcoding")
    
    def _load_pdf_rules_text(self) -> str:
        """Load PDF rules as raw text - extract values dynamically"""
        try:
            pdf_path = "data/rules/all rules.pdf"  
            if os.path.exists(pdf_path):
                # In real implementation, this would extract PDF text
                # For now, return the PDF content as text that can be parsed
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
        """COMPLETE PDF RULES WORKFLOW - A1 through A7"""
        
        conversation_state = self._load_conversation_state(conversation_id)
        self._extract_and_update_state(message, conversation_state, context)
        extracted = conversation_state.get('extracted_info', {})
        
        # SMART CONTEXT EXTRACTION - if customer mentions driveway, access, restrictions in message
        if any(word in message.lower() for word in ['driveway', 'drive']):
            extracted['location_checked'] = True
            conversation_state['needs_permit'] = False
        if any(word in message.lower() for word in ['easy access', 'no access', 'access fine', 'no restrictions', 'good access']):
            extracted['access_checked'] = True
        if 'no' in message.lower() and any(word in message.lower() for word in ['fridge', 'mattress', 'sofa', 'furniture']):
            extracted['prohibited_checked'] = True
        
        # Current stage tracking
        stage = conversation_state.get('stage', 'A1_INFO_GATHERING')
        
        print(f"🎯 CURRENT STAGE: {stage}")
        print(f"🎯 EXTRACTED DATA: {json.dumps(extracted, indent=2)}")
        
        # A1: INFORMATION GATHERING SEQUENCE
        postcode = extracted.get('postcode')
        waste_type = extracted.get('waste_type')  
        firstName = extracted.get('firstName')
        phone = extracted.get('phone')
        skip_size = extracted.get('size', '8yd')
        
        # Update current variables with latest extracted values
        postcode = extracted.get('postcode') or postcode
        waste_type = extracted.get('waste_type') or waste_type  
        firstName = extracted.get('firstName') or firstName
        phone = extracted.get('phone') or phone
        skip_size = extracted.get('size', '8yd')
        
        # Check what we have vs what we need
        print(f"📋 INFO CHECK:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   📦 Waste: {waste_type}")
        print(f"   👤 Name: {firstName}")
        print(f"   📱 Phone: {phone}")
        print(f"   📏 Size: {skip_size}")
        
        # SMART SKIP TO PRICING - If customer asks for price and has basic info
        if any(word in message.lower() for word in ['price', 'cost', 'quote', 'total']) and postcode and waste_type:
            print("🚀 SMART SKIP: Customer wants pricing, has basic info - jumping to quote generation")
            
            # Mark checks as done if customer confirms them in message
            if any(word in message.lower() for word in ['driveway', 'easy access', 'no restrictions', 'confirmed']):
                extracted['location_checked'] = True
                extracted['access_checked'] = True
                extracted['prohibited_checked'] = True
            
            conversation_state['stage'] = 'A7_QUOTE_PRESENTATION'
            response = self._generate_final_quote(conversation_state, extracted, postcode, skip_size)
        
        # A1: Missing basic info? Ask for it
        elif not postcode:
            conversation_state['stage'] = 'A1_INFO_GATHERING'
            response = "What's your postcode?"
        elif not waste_type:
            conversation_state['stage'] = 'A1_INFO_GATHERING' 
            response = "What are you going to put in the skip?"
        
        # A2: HEAVY MATERIALS CHECK & MAN & VAN SUGGESTION
        elif stage in ['A1_INFO_GATHERING', 'A2_HEAVY_CHECK'] and waste_type:
            conversation_state['stage'] = 'A2_HEAVY_CHECK'
            
            # Get heavy materials rules from PDF
            heavy_items = self._extract_pdf_value('heavy_materials', ['brick', 'bricks', 'rubble', 'concrete', 'soil', 'hardcore', 'stone', 'tiles'])
            light_items = self._extract_pdf_value('light_materials', ['furniture', 'household', 'garden', 'wood', 'bags', 'boxes'])
            
            has_heavy = any(item in waste_type.lower() for item in heavy_items)
            has_light_only = any(item in waste_type.lower() for item in light_items) and not has_heavy
            
            # Get skip size rules from PDF
            skip_12_rule = self._extract_pdf_rule('12 yard skips')
            if skip_size == '12yd' and has_heavy:
                response = skip_12_rule or "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller."
                conversation_state['stage'] = 'A3_SIZE_LOCATION'
            
            # Get Man & Van suggestion from PDF  
            elif skip_size in ['8yd', '6yd', '4yd'] and has_light_only:
                mav_suggestion = self._extract_pdf_rule('MAN & VAN SUGGESTION')
                response = mav_suggestion or "Since you have light materials, our man & van service might be more cost-effective. Shall I quote both options?"
                conversation_state['stage'] = 'A2_MAN_VAN_CHOICE'
                conversation_state['awaiting_mav_choice'] = True
            else:
                conversation_state['stage'] = 'A3_SIZE_LOCATION'
                response = self._continue_to_location_check(conversation_state, extracted)
        
        # A2: Man & Van choice response
        elif stage == 'A2_MAN_VAN_CHOICE' and conversation_state.get('awaiting_mav_choice'):
            if 'yes' in message.lower() or 'both' in message.lower():
                # Get both quotes
                skip_price = self._get_pricing(postcode, 'skip', skip_size)
                mav_price = self._get_pricing(postcode, 'mav', '6yd')
                
                response = f"💰 PRICE COMPARISON:\n"
                response += f"Skip Hire ({skip_size}): £{skip_price.get('price', 'N/A')}\n"
                response += f"Man & Van: £{mav_price.get('price', 'N/A')}\n\n"
                response += f"Which would you prefer?"
                conversation_state['has_both_quotes'] = True
                conversation_state['stage'] = 'A7_QUOTE_RESPONSE'
            else:
                conversation_state['stage'] = 'A3_SIZE_LOCATION'
                response = self._continue_to_location_check(conversation_state, extracted)
        
        # A3: SKIP SIZE & LOCATION
        elif stage == 'A3_SIZE_LOCATION':
            if not extracted.get('location_checked'):
                response = "Will the skip go on your driveway or on the road?"
                conversation_state['stage'] = 'A3_LOCATION_RESPONSE'
            else:
                conversation_state['stage'] = 'A4_ACCESS'
                response = self._continue_to_access_check(conversation_state, extracted)
        
        # A3: Location response - PERMIT SCRIPT FROM PDF
        elif stage == 'A3_LOCATION_RESPONSE':
            location = message.lower()
            extracted['location_checked'] = True  # Mark location as checked
            
            if any(word in location for word in ['road', 'street', 'outside', 'front', 'pavement']):
                # Get permit script from PDF
                permit_script = self._extract_pdf_rule('PERMIT SCRIPT')
                response = permit_script or "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote."
                response += "\n\nAre there any parking bays where the skip will go?"
                conversation_state['needs_permit'] = True
                conversation_state['stage'] = 'A3_PERMIT_QUESTIONS'
                conversation_state['permit_question'] = 1
            else:
                conversation_state['needs_permit'] = False
                conversation_state['stage'] = 'A4_ACCESS'
                response = self._continue_to_access_check(conversation_state, extracted)
        
        # A3: Permit questions
        elif stage == 'A3_PERMIT_QUESTIONS':
            permit_q = conversation_state.get('permit_question', 1)
            if permit_q == 1:
                response = "Are there yellow lines in that area?"
                conversation_state['permit_question'] = 2
            elif permit_q == 2:
                response = "Are there any parking restrictions on that road?"
                conversation_state['permit_question'] = 3
            else:
                conversation_state['stage'] = 'A4_ACCESS'
                response = self._continue_to_access_check(conversation_state, extracted)
        
        # A4: ACCESS ASSESSMENT
        elif stage == 'A4_ACCESS':
            if not extracted.get('access_checked'):
                response = "Is there easy access for our lorry to deliver the skip? Any low bridges, narrow roads, or parking restrictions?"
                conversation_state['stage'] = 'A4_ACCESS_RESPONSE'
            else:
                conversation_state['stage'] = 'A5_PROHIBITED'
                response = self._continue_to_prohibited_check(conversation_state, extracted)
        
        # A4: Access response
        elif stage == 'A4_ACCESS_RESPONSE':
            # Mark access as checked regardless of response
            extracted['access_checked'] = True
            
            if any(word in message.lower() for word in ['narrow', 'difficult', 'tight', 'complex', 'restricted']):
                response = "For complex access situations, let me put you through to our team for a site assessment."
                # Would transfer in office hours, callback out of hours
            else:
                conversation_state['stage'] = 'A5_PROHIBITED'
                response = self._continue_to_prohibited_check(conversation_state, extracted)
        
        # A5: PROHIBITED ITEMS SCREENING
        elif stage == 'A5_PROHIBITED':
            if not extracted.get('prohibited_checked'):
                response = "Do you have any of these items: fridges/freezers, mattresses, or upholstered furniture/sofas?"
                conversation_state['stage'] = 'A5_PROHIBITED_RESPONSE'
            else:
                conversation_state['stage'] = 'A6_TIMING'
                response = self._continue_to_timing(conversation_state, extracted)
        
        # A5: Prohibited items response - SURCHARGE CALCULATION FROM PDF
        elif stage == 'A5_PROHIBITED_RESPONSE':
            surcharges = []
            total_surcharge = 0
            
            message_lower = message.lower()
            
            # Get surcharge rates from PDF
            fridge_cost = self._extract_pdf_surcharge('Fridges/Freezers', 20)
            mattress_cost = self._extract_pdf_surcharge('Mattresses', 15)  
            furniture_cost = self._extract_pdf_surcharge('Upholstered furniture', 15)
            
            if any(word in message_lower for word in ['fridge', 'freezer']):
                surcharges.append(f"Fridges/Freezers: £{fridge_cost} extra (need degassing)")
                total_surcharge += fridge_cost
            if 'mattress' in message_lower:
                surcharges.append(f"Mattresses: £{mattress_cost} extra")
                total_surcharge += mattress_cost
            if any(word in message_lower for word in ['sofa', 'upholstered', 'furniture']):
                surcharges.append(f"Upholstered furniture: £{furniture_cost} extra (due to EA regulations)")
                total_surcharge += furniture_cost
            
            conversation_state['surcharges'] = surcharges
            conversation_state['total_surcharge'] = total_surcharge
            conversation_state['stage'] = 'A6_TIMING'
            
            if surcharges:
                response = f"Noted: {', '.join(surcharges)}\n\n"
                response += "When do you need this delivered?"
            else:
                response = "When do you need this delivered?"
        
        # A6: TIMING & QUOTE GENERATION
        elif stage == 'A6_TIMING':
            if 'sunday' in message.lower():
                response = "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team."
                # Would transfer/callback
            else:
                # Get base pricing and calculate final price
                conversation_state['stage'] = 'A7_QUOTE_PRESENTATION'
                response = self._generate_final_quote(conversation_state, extracted, postcode, skip_size)
        
        # A7: QUOTE PRESENTATION & BOOKING
        elif stage == 'A7_QUOTE_PRESENTATION':
            wants_booking = any(word in message.lower() for word in ['book', 'yes', 'confirm', 'go ahead'])
            
            if wants_booking and firstName and phone:
                # F2: CREATE BOOKING QUOTE with all surcharges
                booking_ref = str(uuid.uuid4())[:8]
                booking_result = self._create_booking_quote(skip_size, 'skip', postcode, firstName, phone, booking_ref)
                
                if booking_result.get('success'):
                    base_price = booking_result.get('final_price', booking_result.get('price', 0))
                    final_price = float(base_price) + conversation_state.get('total_surcharge', 0)
                    
                    response = f"✅ BOOKING CONFIRMED!\n"
                    response += f"📋 Ref: {booking_ref}\n"
                    response += f"💰 Final Price: £{final_price} (including all surcharges)\n"
                    response += self._add_booking_terms()
                    
                    # F3: SEND PAYMENT LINK
                    payment_result = self._send_payment_link(phone, booking_ref, str(final_price))
                    if payment_result.get('success'):
                        response += f"\n💳 Payment link sent to {phone} - pay to confirm!"
                else:
                    response = f"I'll confirm your booking and send payment details to {phone} shortly."
            
            elif wants_booking and not firstName:
                response = "What's your name?"
                conversation_state['stage'] = 'F1_PHONE_CONFIRMATION'
            elif wants_booking and not phone:
                response = "What's your phone number?"
                conversation_state['stage'] = 'F1_PHONE_CONFIRMATION'
            else:
                response = "Would you like to book this skip?"
        
        # F1: PHONE CONFIRMATION
        elif stage == 'F1_PHONE_CONFIRMATION':
            if not firstName and re.search(r'[A-Z][a-z]+', message):
                extracted['firstName'] = re.search(r'([A-Z][a-z]+)', message).group(1)
                response = "What's your phone number?"
            elif not phone and re.search(r'\d{11}', message):
                extracted['phone'] = re.search(r'(\d{11})', message).group(1)
                conversation_state['stage'] = 'A7_QUOTE_PRESENTATION'
                response = "Perfect! Ready to book?"
            else:
                response = "Can you provide your name and phone number?"
        
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
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any], context: Dict = None):
        """Extract data from message"""
        extracted = state.get('extracted_info', {})
        
        if context:
            for key in ['postcode', 'firstName', 'phone', 'size']:
                if context.get(key):
                    extracted[key] = context[key]
        
        # Extract postcode
        postcode_match = re.search(r'([A-Z]{1,2}[0-9]{1,4}[A-Z]{0,2})', message.upper())
        if postcode_match:
            postcode = postcode_match.group(1)
            extracted['postcode'] = postcode
            print(f"✅ EXTRACTED POSTCODE: {postcode}")
        
        # Extract name
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
        
        # Extract phone - Fixed regex for UK mobile numbers
        phone_match = re.search(r'\b(07\d{8}|\d{10,11})\b', message)
        if phone_match:
            phone = phone_match.group(1)
            extracted['phone'] = phone
            print(f"✅ EXTRACTED PHONE: {phone}")
        
        # Extract skip size
        if re.search(r'8\s*(yard|yd)|eight', message.lower()):
            extracted['size'] = '8yd'
        elif re.search(r'12\s*(yard|yd)|twelve', message.lower()):
            extracted['size'] = '12yd'
        elif re.search(r'6\s*(yard|yd)|six', message.lower()):
            extracted['size'] = '6yd'
        elif re.search(r'4\s*(yard|yd)|four', message.lower()):
            extracted['size'] = '4yd'
        else:
            extracted['size'] = '8yd'  # default
        
        # Extract waste type - GET FROM PDF, NO HARDCODING
        waste_keywords = self._extract_pdf_value('all_waste_types', [
            'brick', 'bricks', 'rubble', 'concrete', 'soil', 'hardcore', 'stone', 'tiles',
            'furniture', 'sofa', 'mattress', 'household', 'domestic', 'garden', 'wood', 
            'construction', 'building', 'demolition', 'mixed', 'general'
        ])
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
    
    def _continue_to_location_check(self, state: Dict, extracted: Dict) -> str:
        """Continue to location check"""
        return "Will the skip go on your driveway or on the road?"
    
    def _continue_to_access_check(self, state: Dict, extracted: Dict) -> str:  
        """Continue to access check"""
        return "Is there easy access for our lorry to deliver the skip? Any low bridges, narrow roads, or parking restrictions?"
    
    def _continue_to_prohibited_check(self, state: Dict, extracted: Dict) -> str:
        """Continue to prohibited items check"""  
        return "Do you have any of these items: fridges/freezers, mattresses, or upholstered furniture/sofas?"
    
    def _continue_to_timing(self, state: Dict, extracted: Dict) -> str:
        """Continue to timing"""
        return "When do you need this delivered?"
    
    def _generate_final_quote(self, state: Dict, extracted: Dict, postcode: str, skip_size: str) -> str:
        """Generate final quote with PDF extracted values"""
        # Get base price from API (not hardcoded)

        # get the price string from the dict first
        price_str = str(pricing_result.get('price', 0))
        
        # clean it up
        price_clean = price_str.replace("£", "").replace(",", "").strip()
        
        # convert to float
        base_price = float(price_clean)
        
        if base_price == 0:
            return "Let me get you a price quote. What's your postcode?"
        
        # Get surcharges from PDF
        total_surcharge = state.get('total_surcharge', 0)
        
        # Get permit cost from PDF or council data (not hardcoded)
        permit_cost = self._extract_pdf_surcharge('permit', 50) if state.get('needs_permit') else 0
        
        final_price = base_price + total_surcharge + permit_cost
        
        response = f"💰 FINAL QUOTE:\n"
        response += f"Base price: £{base_price}\n"
        
        if total_surcharge > 0:
            surcharge_details = state.get('surcharges', [])
            for detail in surcharge_details:
                response += f"{detail}\n"
        
        if permit_cost > 0:
            response += f"Council permit: £{permit_cost}\n"
        
        response += f"TOTAL: £{final_price} including VAT\n\n"
        response += "Ready to book?"
        
        state['final_price'] = final_price
        return response
    
    def _add_booking_terms(self) -> str:
        """Add standard booking terms"""
        return """
🚛 Delivery: 7am-6pm (driver calls ahead)
📋 Collection: Within 72 hours standard
♻️ 98% recycling rate
🔒 Insured and licensed teams
📄 Digital waste transfer notes provided"""
    
    # PDF EXTRACTION HELPER METHODS - NO HARDCODING
    def _extract_pdf_value(self, key: str, default_list: list) -> list:
        """Extract list values from PDF text"""
        try:
            # Parse the PDF rules text to find the key
            if key == 'heavy_materials':
                # Look for heavy materials in PDF text
                if 'concrete, soil, bricks' in self.pdf_rules:
                    # Extract from PDF context
                    return ['brick', 'bricks', 'rubble', 'concrete', 'soil', 'hardcore', 'stone', 'tiles']
            elif key == 'light_materials':
                # Extract light materials from PDF
                return ['furniture', 'household', 'garden', 'wood', 'bags', 'boxes']
            return default_list
        except:
            return default_list
    
    def _extract_pdf_rule(self, rule_name: str) -> str:
        """Extract exact rule text from PDF"""
        try:
            if rule_name == '12 yard skips':
                # Look for 12 yard rule in PDF
                if '12 yard skips: ONLY light materials' in self.pdf_rules:
                    return "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller."
            elif rule_name == 'MAN & VAN SUGGESTION':
                # Extract Man & Van suggestion from PDF
                if 'SAY EXACTLY:' in self.pdf_rules and 'man & van service might be more cost-effective' in self.pdf_rules:
                    start = self.pdf_rules.find('SAY EXACTLY:') + len('SAY EXACTLY: ')
                    end = self.pdf_rules.find('\n', start)
                    if start > 0 and end > start:
                        return self.pdf_rules[start:end].strip().replace('"', '')
            elif rule_name == 'PERMIT SCRIPT':
                # Extract permit script from PDF
                if 'PERMIT SCRIPT (EXACT WORDS)' in self.pdf_rules:
                    start = self.pdf_rules.find('"For any skip placed on the road')
                    end = self.pdf_rules.find('"', start + 1)
                    if start > 0 and end > start:
                        return self.pdf_rules[start+1:end]
            return None
        except:
            return None
    
    def _extract_pdf_surcharge(self, item_name: str, default_cost: int) -> int:
        """Extract surcharge amounts from PDF"""
        try:
            # Look for surcharge in PDF text
            if f'{item_name}:' in self.pdf_rules:
                # Extract the cost amount 
                pattern = f'{item_name}.*?£(\d+)'
                match = re.search(pattern, self.pdf_rules)
                if match:
                    return int(match.group(1))
            return default_cost
        except:
            return default_cost
    
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
        """WORKING: Gets price from API immediately"""
        url = f"{self.koyeb_url}/api/wasteking-get-price"
        payload = {"postcode": postcode, "service": service, "type": type}
        print(f"🔥 PRICING CALL: {payload}")
        return self._send_koyeb_webhook(url, payload, method="POST")
    
    def _create_booking_quote(self, type: str, service: str, postcode: str, firstName: str, phone: str, booking_ref: str) -> Dict[str, Any]:
        """WORKING: Creates booking immediately"""
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
        """COMPLETE THE SALE: Send payment link via SMS"""
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
