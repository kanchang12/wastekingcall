# agents/skip_hire_agent.py - CORRECT PROCESS WITH OFFICE RULES
# CHANGES: Proper sales flow + office time rules + correct supplier call timing

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
            ("system", """You are a Skip Hire agent. Follow CORRECT BUSINESS PROCESS.

OFFICE TIME RULES:
- Office hours: Monday-Friday 8AM-6PM, Saturday 8AM-4PM, Sunday closed
- Same day delivery: Only if booked before 2PM on weekdays
- Weekend delivery: Only Saturday, must book by Friday 4PM
- No delivery on Sundays or bank holidays

CORRECT SALES WORKFLOW:
1. Gather qualifying info: postcode, waste type, skip size, delivery date
2. Call smp_api(action="get_pricing") - SHOW PRICE
3. Sales push: "That's £X. Shall I book this skip for you?"
4. If customer says YES: Ask for name and phone
5. Discuss delivery date/time (check office rules)
6. Call supplier to confirm availability (smp_api action="call_supplier") 
7. ONLY AFTER supplier confirms: Create booking (action="create_booking_quote")

NEVER auto-book. Always: Price → Push → Confirm → Supplier call → Book

QUALIFYING QUESTIONS:
- "What's your postcode?"
- "What type of waste?" (construction, garden, household)
- "What size skip?" (4yd, 6yd, 8yd, 12yd)
- "When do you need it delivered?"

SUPPLIER CALL TIMING: After price discussion and before final booking."""),
            ("human", "Customer: {input}\n\nStage: {stage}\nData: {extracted_info}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=8)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Proper business process with office rules"""
        
        # Extract data with context
        extracted_data = self._extract_data(message, context)
        stage = self._determine_stage(extracted_data, message)
        
        print(f"🔧 SKIP DATA: {json.dumps(extracted_data, indent=2)}")
        print(f"📊 STAGE: {stage}")
        
        # Process based on stage
        if stage == "need_info":
            return self._handle_info_gathering(extracted_data)
        elif stage == "ready_for_pricing":
            return self._handle_pricing(extracted_data, message)
        elif stage == "customer_wants_to_book":
            return self._handle_booking_interest(extracted_data, message)
        elif stage == "ready_for_supplier_call":
            return self._handle_supplier_call(extracted_data, message)
        elif stage == "ready_for_booking":
            return self._handle_final_booking(extracted_data, message)
        else:
            return "Let me help you with skip hire. What's your postcode?"
    
    def _determine_stage(self, data: Dict, message: str) -> str:
        """Determine what stage of sales process we're at"""
        
        has_postcode = bool(data.get('postcode'))
        has_waste = bool(data.get('waste_type'))
        customer_interested = self._customer_wants_to_book(message)
        has_contact = bool(data.get('firstName') and data.get('phone'))
        has_date = bool(data.get('delivery_date'))
        
        if not has_postcode or not has_waste:
            return "need_info"
        elif has_postcode and has_waste and not customer_interested:
            return "ready_for_pricing"
        elif customer_interested and not has_contact:
            return "customer_wants_to_book"
        elif has_contact and not has_date:
            return "need_delivery_date"
        elif has_contact and has_date:
            return "ready_for_supplier_call"
        else:
            return "need_info"
    
    def _handle_info_gathering(self, data: Dict) -> str:
        """Ask qualifying questions"""
        if not data.get('postcode'):
            return "What's your postcode for the skip delivery?"
        if not data.get('waste_type'):
            return "What type of waste will you be putting in the skip? (construction, garden, household, etc.)"
        if not data.get('size'):
            return "What size skip do you need? (4yd, 6yd, 8yd, or 12yd)"
        return "Let me get you a quote."
    
    def _handle_pricing(self, data: Dict, message: str) -> str:
        """Show pricing and push for sale"""
        extracted_info = f"""
Postcode: {data.get('postcode')}
Waste Type: {data.get('waste_type')}
Service: skip
Type: {data.get('size', '8yd')}
Action: get_pricing
Stage: showing_price_and_pushing_sale
"""
        
        agent_input = {
            "input": message,
            "stage": "showing_price_and_pushing_sale",
            "extracted_info": extracted_info,
            "action": "get_pricing",
            **data
        }
        
        response = self.executor.invoke(agent_input)
        return response["output"]
    
    def _handle_booking_interest(self, data: Dict, message: str) -> str:
        """Customer wants to book - get their details"""
        missing = []
        if not data.get('firstName'):
            missing.append("name")
        if not data.get('phone'):
            missing.append("phone number")
        
        if missing:
            return f"Great! I'll need your {' and '.join(missing)} to proceed with the booking."
        
        return "Perfect! When would you like the skip delivered?"
    
    def _handle_supplier_call(self, data: Dict, message: str) -> str:
        """Call supplier to check availability before final booking"""
        extracted_info = f"""
Postcode: {data.get('postcode')}
Service: skip
Type: {data.get('size', '8yd')}
Customer: {data.get('firstName')}
Phone: {data.get('phone')}
Delivery Date: {data.get('delivery_date')}
Action: call_supplier
Stage: checking_supplier_availability
"""
        
        agent_input = {
            "input": message,
            "stage": "checking_supplier_availability", 
            "extracted_info": extracted_info,
            "action": "call_supplier",
            **data
        }
        
        response = self.executor.invoke(agent_input)
        return response["output"]
    
    def _handle_final_booking(self, data: Dict, message: str) -> str:
        """Create final booking after supplier confirms"""
        extracted_info = f"""
Postcode: {data.get('postcode')}
Service: skip
Type: {data.get('size', '8yd')}
Customer: {data.get('firstName')}
Phone: {data.get('phone')}
Delivery Date: {data.get('delivery_date')}
Action: create_booking_quote
Stage: creating_final_booking
"""
        
        # Generate booking ref
        import uuid
        data['booking_ref'] = str(uuid.uuid4())
        
        agent_input = {
            "input": message,
            "stage": "creating_final_booking",
            "extracted_info": extracted_info,
            "action": "create_booking_quote",
            **data
        }
        
        response = self.executor.invoke(agent_input)
        return response["output"]
    
    def _customer_wants_to_book(self, message: str) -> bool:
        """Check if customer expressed interest in booking"""
        interested_phrases = [
            'yes', 'yeah', 'ok', 'okay', 'sure', 'book it', 'go ahead', 
            'proceed', 'confirm', 'yes please', 'sounds good', 'lets do it'
        ]
        message_lower = message.lower()
        return any(phrase in message_lower for phrase in interested_phrases)
    
    def _check_office_hours(self, delivery_date: str) -> Dict[str, Any]:
        """Check if delivery date meets office time rules"""
        from datetime import datetime, timedelta
        
        try:
            # Parse delivery date (this is simplified - you'd want better date parsing)
            today = datetime.now()
            
            # Office rules
            rules = {
                "office_hours": "Monday-Friday 8AM-6PM, Saturday 8AM-4PM",
                "same_day_cutoff": "2PM weekdays only",
                "weekend_delivery": "Saturday only, book by Friday 4PM",
                "no_sunday_delivery": True
            }
            
            return {
                "valid": True,  # Simplified for now
                "rules": rules,
                "message": "Delivery available within office hours"
            }
        except:
            return {
                "valid": True,
                "rules": {},
                "message": "Standard delivery times apply"
            }
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Extract data without confusing cities with names"""
        data = {}
        
        # Check context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress', 'waste_type', 'size', 'delivery_date']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract postcode (be more specific)
        postcode_patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b'  # Proper UK postcode format
        ]
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean = match.strip().replace(' ', '')
                if len(clean) >= 5:  # Minimum UK postcode length
                    data['postcode'] = clean
                    break
        
        # Extract waste type
        waste_types = ['construction', 'building', 'garden', 'household', 'mixed', 'bricks', 'concrete', 'soil', 'rubble']
        found = []
        message_lower = message.lower()
        for waste in waste_types:
            if waste in message_lower:
                found.append(waste)
        if found:
            data['waste_type'] = ', '.join(found)
        
        # Extract skip size
        if re.search(r'eight|8\s*yard|8yd', message.lower()):
            data['size'] = '8yd'
        elif re.search(r'six|6\s*yard|6yd', message.lower()):
            data['size'] = '6yd'
        elif re.search(r'four|4\s*yard|4yd', message.lower()):
            data['size'] = '4yd'
        else:
            data['size'] = '8yd'  # Default
        
        # Extract name (only if clearly a name, not a city)
        name_patterns = [
            r'my name is (\w+)',
            r'i\'m (\w+)',
            r'call me (\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).title()
                # Don't confuse cities with names
                if name.lower() not in ['manchester', 'london', 'birmingham', 'liverpool', 'leeds']:
                    data['firstName'] = name
                break
        
        # Extract phone
        phone_match = re.search(r'\b(07\d{9}|\d{11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
        
        # Extract delivery timing
        date_patterns = [
            r'next (\w+)',  # next Tuesday
            r'tomorrow',
            r'today',
            r'(\w+day)',   # Tuesday, Wednesday, etc.
        ]
        for pattern in date_patterns:
            match = re.search(pattern, message.lower())
            if match:
                data['delivery_date'] = match.group(0)
                break
        
        data['service'] = 'skip'
        data['type'] = data.get('size', '8yd')
        
        return data
