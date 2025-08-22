# agents/skip_hire_agent.py - FIXED BOOKING LOGIC
# CHANGES: Fixed to recognize booking requests and create actual bookings

import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Skip Hire agent. Be FAST and DIRECT.

CRITICAL WORKFLOW:
1. If customer says "book" or wants to book: IMMEDIATELY call smp_api with action="create_booking_quote"
2. If just asking for price: Call smp_api with action="get_pricing" then ask "Shall I book this for you?"
3. Missing data → Ask once

BOOKING KEYWORDS: book, booking, confirm, yes book it, proceed, go ahead, arrange

API CALLS:
- For pricing: smp_api(action="get_pricing", postcode=X, service="skip", type="8yd")
- For booking: smp_api(action="create_booking_quote", postcode=X, service="skip", type="8yd", firstName=X, phone=X, booking_ref=X)

AFTER PRICING: Always ask "Shall I book this skip for you?"

SKIP SIZES: 4yd, 6yd, 8yd, 12yd (default 8yd)

Be direct. Get price. Ask to book. Create booking if confirmed."""),
            ("human", "Customer: {input}\n\nData: {extracted_info}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=10)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Enhanced processing with booking recognition"""
        
        # Extract data with context
        extracted_data = self._extract_data(message, context)
        
        print(f"🔧 SKIP DATA: {json.dumps(extracted_data, indent=2)}")
        
        # Check if this is a booking request
        is_booking_request = self._is_booking_request(message)
        
        # Check if ready for API call
        postcode = extracted_data.get('postcode')
        waste_type = extracted_data.get('waste_type')
        
        if postcode and waste_type:
            print(f"🔧 READY FOR API - {'BOOKING' if is_booking_request else 'PRICING'}")
            
            # Determine action based on whether it's a booking request
            action = "create_booking_quote" if is_booking_request else "get_pricing"
            
            extracted_info = f"""
Postcode: {postcode}
Waste Type: {waste_type}
Service: skip
Type: {extracted_data.get('size', '8yd')}
Customer Name: {extracted_data.get('firstName', 'NOT PROVIDED')}
Customer Phone: {extracted_data.get('phone', 'NOT PROVIDED')}
Action: {action}
Is Booking Request: {is_booking_request}
Ready for API: True
"""
            
            agent_input = {
                "input": message,
                "extracted_info": extracted_info,
                "action": action,
                **extracted_data
            }
            
            response = self.executor.invoke(agent_input)
            return response["output"]
        
        # Missing data - ask directly
        if not postcode:
            return "I need your postcode to get skip hire pricing. What's your postcode?"
        
        if not waste_type:
            return "What type of waste do you have? (construction, garden, household, etc.)"
        
        return "Let me get you a skip hire quote."
    
    def _is_booking_request(self, message: str) -> bool:
        """Check if customer wants to book (not just get pricing)"""
        message_lower = message.lower()
        
        booking_keywords = [
            'book', 'booking', 'confirm', 'yes book', 'proceed', 'go ahead', 
            'arrange', 'order', 'want to book', 'please book', 'book it',
            'yes please', 'confirm booking', 'make booking'
        ]
        
        return any(keyword in message_lower for keyword in booking_keywords)
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Enhanced data extraction with context handling"""
        data = {}
        
        # Check context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress', 'waste_type']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract postcode
        postcode = self._get_postcode(message, context)
        if postcode:
            data['postcode'] = postcode
        
        # Extract waste type
        waste_type = self._get_waste_type(message, context)
        if waste_type:
            data['waste_type'] = waste_type
        
        # Extract skip size
        size = self._get_size(message, context)
        data['size'] = size
        
        # Extract customer info
        name_match = re.search(r'(?:name is|i\'m|call me|name)\s+(\w+)', message, re.IGNORECASE)
        if name_match:
            data['firstName'] = name_match.group(1).title()
        
        phone_match = re.search(r'\b(07\d{9}|\d{11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
        
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
        if email_match:
            data['emailAddress'] = email_match.group()
        
        # Generate booking reference if this is a booking request
        if self._is_booking_request(message):
            import uuid
            data['booking_ref'] = str(uuid.uuid4())
        
        data['service'] = 'skip'
        data['type'] = size  # Use size as type for API
        
        return data
    
    def _get_postcode(self, message: str, context: Dict) -> str:
        """Extract postcode with context priority"""
        # Check context first
        if context and context.get('postcode'):
            return context['postcode']
        
        # Extract from message
        patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b',
            r'postcode\s*:?\s*([A-Z0-9\s]+)'
        ]
        for pattern in patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean = match.strip().replace(' ', '')
                if len(clean) >= 4 and any(c.isdigit() for c in clean) and any(c.isalpha() for c in clean):
                    return clean
        
        return None
    
    def _get_waste_type(self, message: str, context: Dict) -> str:
        """Extract waste type with context priority"""
        # Check context first
        if context and context.get('waste_type'):
            return context['waste_type']
        
        # Extract from message
        waste_types = [
            'construction', 'building', 'garden', 'household', 'mixed', 
            'bricks', 'concrete', 'soil', 'rubble', 'mortar', 'wood',
            'metal', 'plastic', 'cardboard', 'general', 'office',
            'demolition', 'renovation', 'clearance'
        ]
        found = []
        message_lower = message.lower()
        for waste in waste_types:
            if waste in message_lower:
                found.append(waste)
        
        return ', '.join(found) if found else None
    
    def _get_size(self, message: str, context: Dict) -> str:
        """Extract skip size with context priority"""
        # Check context first
        if context and context.get('size'):
            return context['size']
        
        # Extract from message
        size_patterns = [r'(\d+)\s*(?:yard|yd)', r'(\d+)yd', r'eight\s*yard', r'six\s*yard']
        for pattern in size_patterns:
            match = re.search(pattern, message.lower())
            if match:
                if 'eight' in pattern:
                    return "8yd"
                elif 'six' in pattern:
                    return "6yd"
                else:
                    return f"{match.group(1)}yd"
        
        return "8yd"  # Default size
