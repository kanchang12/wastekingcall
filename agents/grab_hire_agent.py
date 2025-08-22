# agents/grab_hire_agent.py - CORRECT PROCESS WITH OFFICE RULES
# CHANGES: Proper sales flow + office time rules + correct supplier call timing

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
            ("system", """You are the WasteKing Grab Hire specialist - friendly, British!

HANDLES: ALL services EXCEPT "mav" and "skip" - grab hire, general waste, heavy materials, office clearance, etc.

OFFICE TIME RULES:
- Office hours: Monday-Friday 8AM-6PM, Saturday 8AM-4PM, Sunday closed
- Same day delivery: Only if booked before 2PM on weekdays
- Weekend delivery: Only Saturday, must book by Friday 4PM
- No delivery on Sundays or bank holidays

CORRECT SALES WORKFLOW:
1. Gather qualifying info: postcode, material type, grab size, delivery date
2. Call smp_api(action="get_pricing") - SHOW PRICE
3. Sales push: "Right then! That's £X. Shall I book this grab hire for you?"
4. If customer says YES: Ask for name and phone
5. Discuss delivery date/time (check office rules)
6. Call supplier to confirm availability (smp_api action="call_supplier")
7. ONLY AFTER supplier confirms: Create booking (action="create_booking_quote")

NEVER auto-book. Always: Price → Push → Confirm → Supplier call → Book

QUALIFYING QUESTIONS:
- "What's your postcode?"
- "What materials need collecting?" (soil, rubble, office waste, etc.)
- "What size grab lorry?" (8yd standard)
- "When do you need collection?"

SUPPLIER CALL TIMING: After price discussion and before final booking.

PERSONALITY: "Alright love!", "Right then!", friendly British style."""),
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
        
        print(f"🔧 GRAB DATA: {json.dumps(extracted_data, indent=2)}")
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
            return "Alright love! Let me help you with grab hire. What's your postcode?"
    
    def _determine_stage(self, data: Dict, message: str) -> str:
        """Determine what stage of sales process we're at"""
        
        has_postcode = bool(data.get('postcode'))
        has_materials = bool(data.get('material_type'))
        customer_interested = self._customer_wants_to_book(message)
        has_contact = bool(data.get('firstName') and data.get('phone'))
        has_date = bool(data.get('delivery_date'))
        
        if not has_postcode or not has_materials:
            return "need_info"
        elif has_postcode and has_materials and not customer_interested:
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
            return "Right then! What's your postcode for the grab hire collection?"
        if not data.get('material_type'):
            return "What materials need collecting? (soil, rubble, office waste, household, etc.)"
        return "Let me get you a grab hire quote."
    
    def _handle_pricing(self, data: Dict, message: str) -> str:
        """Show pricing and push for sale"""
        extracted_info = f"""
Postcode: {data.get('postcode')}
Material Type: {data.get('material_type')}
Service: grab
Type: {data.get('type', '8yd')}
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
            return f"Brilliant! I'll need your {' and '.join(missing)} to proceed with the booking."
        
        return "Perfect! When would you like the grab lorry to come?"
    
    def _handle_supplier_call(self, data: Dict, message: str) -> str:
        """Call supplier to check availability before final booking"""
        extracted_info = f"""
Postcode: {data.get('postcode')}
Service: grab
Type: {data.get('type', '8yd')}
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
Service: grab
Type: {data.get('type', '8yd')}
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
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Extract data properly"""
        data = {}
        
        # Check context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress', 'material_type', 'delivery_date']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract postcode
        postcode_patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b'
        ]
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean = match.strip().replace(' ', '')
                if len(clean) >= 5:
                    data['postcode'] = clean
                    break
        
        # Extract materials
        materials = [
            'soil', 'muck', 'rubble', 'concrete', 'brick', 'sand', 'gravel',
            'construction', 'building', 'demolition', 'household', 'office', 
            'garden', 'wood', 'metal', 'general', 'clearance'
        ]
        found = []
        message_lower = message.lower()
        for material in materials:
            if material in message_lower:
                found.append(material)
        if found:
            data['material_type'] = ', '.join(found)
        
        # Extract name (avoid cities)
        name_patterns = [
            r'my name is (\w+)',
            r'i\'m (\w+)',
            r'call me (\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).title()
                if name.lower() not in ['manchester', 'london', 'birmingham', 'liverpool', 'leeds']:
                    data['firstName'] = name
                break
        
        # Extract phone
        phone_match = re.search(r'\b(07\d{9}|\d{11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
        
        # Extract delivery timing
        date_patterns = [
            r'next (\w+)',
            r'tomorrow',
            r'today',
            r'(\w+day)'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, message.lower())
            if match:
                data['delivery_date'] = match.group(0)
                break
        
        data['service'] = 'grab'
        data['type'] = '8yd'
        
        return data
