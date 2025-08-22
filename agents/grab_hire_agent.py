# agents/grab_hire_agent.py - FIXED BOOKING LOGIC
# CHANGES: Fixed to recognize booking requests and create actual bookings

import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Grab Hire specialist - friendly, British, and GET PRICING NOW!

IMPORTANT ROUTING: You handle ALL waste services EXCEPT "mav" (man and van) and "skip" (skip hire).
This includes: grab hire, general waste, large items, heavy materials, construction waste, garden waste, office clearance, etc.

CRITICAL WORKFLOW:
1. If customer says "book" or wants to book: IMMEDIATELY call smp_api with action="create_booking_quote"
2. If just asking for price: Call smp_api with action="get_pricing" then ask "Shall I book this for you?"
3. Missing data → Ask once

BOOKING KEYWORDS: book, booking, confirm, yes book it, proceed, go ahead, arrange

API CALLS:
- For pricing: smp_api(action="get_pricing", postcode=X, service="grab", type="8yd")
- For booking: smp_api(action="create_booking_quote", postcode=X, service="grab", type="8yd", firstName=X, phone=X, booking_ref=X)

AFTER PRICING: Always ask "Right then! Shall I book this grab hire for you?"

PERSONALITY:
- Start with: "Alright love!" or "Right then!"
- Get pricing first, then ask to book
- Create booking if customer confirms

MATERIAL GUIDANCE:
- Heavy materials (soil, rubble, concrete) = grab lorry ideal
- Large volumes = grab lorry
- Light materials = can still use grab if customer prefers

CRITICAL: Always call smp_api with correct action based on customer intent."""),
            ("human", """Customer: {input}

Extracted data: {extracted_info}

INSTRUCTION: If customer wants to BOOK, call create_booking_quote. If just pricing, call get_pricing then ask to book."""),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )
        
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            max_iterations=10
        )
    
    def extract_and_validate_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Enhanced data extraction with booking recognition"""
        data = {}
        missing = []
        
        # Check context first to prevent data loss
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract name
        name_patterns = [
            r'name\s+(?:is\s+)?(\w+)',
            r'i\'?m\s+(\w+)',
            r'my\s+name\s+is\s+(\w+)',
            r'this\s+is\s+(\w+)',
            r'name\s+(\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['firstName'] = match.group(1).title()
                break
        
        # Improved postcode extraction
        postcode_found = False
        postcode_patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b',  # Full UK postcode
            r'postcode\s*:?\s*([A-Z0-9\s]+)',
            r'(?:at|in|from)\s+([A-Z0-9\s]{4,8})',
        ]
        
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean_match = match.strip().replace(' ', '')
                if len(clean_match) >= 4 and any(c.isdigit() for c in clean_match) and any(c.isalpha() for c in clean_match):
                    data['postcode'] = clean_match  # Store without spaces for API
                    postcode_found = True
                    break
            if postcode_found:
                break
        
        # Enhanced material detection for all waste types
        material_keywords = {
            # Heavy materials (ideal for grab)
            'soil': 'heavy', 'muck': 'heavy', 'rubble': 'heavy', 'hardcore': 'heavy',
            'sand': 'heavy', 'gravel': 'heavy', 'concrete': 'heavy', 'stone': 'heavy',
            'brick': 'heavy', 'bricks': 'heavy', 'mortar': 'heavy',
            
            # Construction materials
            'construction': 'heavy', 'building': 'heavy', 'demolition': 'heavy',
            'tiles': 'heavy', 'plaster': 'heavy',
            
            # General waste (grab can handle)
            'household': 'general', 'general': 'general', 'office': 'general',
            'garden': 'general', 'green': 'general', 'wood': 'general',
            'metal': 'general', 'plastic': 'general', 'cardboard': 'general'
        }
        
        message_lower = message.lower()
        found_material = None
        material_category = None
        
        for keyword, category in material_keywords.items():
            if keyword in message_lower:
                found_material = keyword
                material_category = category
                break
        
        if found_material:
            data['material_type'] = found_material
            data['material_category'] = material_category
        
        # Extract phone
        phone_patterns = [
            r'\b(07\d{9})\b',  # UK mobile
            r'\b(\d{11})\b',
            r'phone\s+(?:is\s+|number\s+)?(\d{10,11})',
            r'mobile\s+(?:is\s+|number\s+)?(\d{10,11})',
            r'number\s+(?:is\s+)?(\d{10,11})'
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                data['phone'] = match.group(1)
                break
        
        # Extract email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, message)
        if email_match:
            data['emailAddress'] = email_match.group()
        
        # Service determination
        service_type = 'grab'  # Default for grab agent
        data['service'] = service_type
        data['type'] = '8yd'  # Default size
        
        # Check if this is a booking request
        is_booking_request = self._is_booking_request(message)
        data['is_booking_request'] = is_booking_request
        
        # Generate booking reference if booking request
        if is_booking_request:
            import uuid
            data['booking_ref'] = str(uuid.uuid4())
        
        # Check what's missing for pricing/booking
        if 'postcode' not in data:
            missing.append('postcode')
        if not found_material and 'material_type' not in data:
            missing.append('material_type')
        
        # For booking, need name and phone
        if is_booking_request:
            if 'firstName' not in data:
                missing.append('firstName')
            if 'phone' not in data:
                missing.append('phone')
        
        data['missing_info'] = missing
        data['ready_for_pricing'] = 'postcode' in data and (found_material or 'material_type' in data)
        data['ready_for_booking'] = data['ready_for_pricing'] and 'firstName' in data and 'phone' in data
        
        return data
    
    def _is_booking_request(self, message: str) -> bool:
        """Check if customer wants to book (not just get pricing)"""
        message_lower = message.lower()
        
        booking_keywords = [
            'book', 'booking', 'confirm', 'yes book', 'proceed', 'go ahead', 
            'arrange', 'order', 'want to book', 'please book', 'book it',
            'yes please', 'confirm booking', 'make booking'
        ]
        
        return any(keyword in message_lower for keyword in booking_keywords)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Enhanced message processing with booking recognition"""
        
        # Clear old data if new postcode detected
        extracted = self.extract_and_validate_data(message, context)
        
        # If we have a new postcode different from context, prioritize the new one
        if context and context.get('postcode') and extracted.get('postcode'):
            if context['postcode'] != extracted['postcode']:
                print(f"🔄 NEW POSTCODE DETECTED: {extracted['postcode']} (clearing old: {context['postcode']})")
                context = {'postcode': extracted['postcode']}  # Reset context
        
        # Merge context with extracted data
        if context:
            for key, value in context.items():
                if value and key not in extracted:
                    extracted[key] = value
        
        # Determine action based on booking request and data availability
        action = "get_pricing"  # Default
        if extracted.get('is_booking_request') and extracted.get('ready_for_booking'):
            action = "create_booking_quote"
        elif extracted.get('ready_for_pricing'):
            action = "get_pricing"
        
        extracted_info = f"""
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Material Type: {extracted.get('material_type', 'NOT PROVIDED')}
Material Category: {extracted.get('material_category', 'unknown')}
Service: {extracted.get('service', 'grab')}
Type: {extracted.get('type', '8yd')}
Is Booking Request: {extracted.get('is_booking_request', False)}
Ready for Pricing: {extracted.get('ready_for_pricing', False)}
Ready for Booking: {extracted.get('ready_for_booking', False)}
Action: {action}
Missing: {extracted.get('missing_info', [])}
Customer Name: {extracted.get('firstName', 'NOT PROVIDED')}
Customer Phone: {extracted.get('phone', 'NOT PROVIDED')}

*** API Parameters: action={action}, postcode={extracted.get('postcode', 'NOT PROVIDED')}, service={extracted.get('service', 'grab')}, type={extracted.get('type', '8yd')} ***
"""
        
        agent_input = {
            "input": message,
            "extracted_info": extracted_info,
            "action": action
        }
        
        # Add all extracted data to agent input
        agent_input.update(extracted)
        
        try:
            response = self.executor.invoke(agent_input)
            return response["output"]
        except Exception as e:
            print(f"❌ Grab Agent Error: {str(e)}")
            return "Right then! I need your postcode and what type of waste you have to get you a quote. What's your postcode?"
