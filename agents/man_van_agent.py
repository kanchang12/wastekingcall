# agents/man_van_agent.py - CORRECT PROCESS WITH OFFICE RULES
# CHANGES: Proper sales flow + office time rules + correct supplier call timing

import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Man & Van agent with STRICT RULES.

HEAVY ITEMS RULE - CANNOT HANDLE:
bricks, mortar, concrete, soil, tiles, construction waste, industrial waste, rubble, hardcore, sand, gravel, stone

If heavy items detected: "Sorry mate, bricks/concrete/soil are too heavy for Man & Van. You need Skip Hire or Grab Hire for that."

OFFICE TIME RULES:
- Office hours: Monday-Friday 8AM-6PM, Saturday 8AM-4PM, Sunday closed
- Same day collection: Only if booked before 2PM on weekdays
- Weekend collection: Only Saturday, must book by Friday 4PM
- No collection on Sundays or bank holidays

CORRECT SALES WORKFLOW:
1. Check for heavy items FIRST - refuse if found
2. Gather qualifying info: postcode, items, collection date
3. Call smp_api(action="get_pricing") - SHOW PRICE
4. Sales push: "That's £X. Shall I book this Man & Van for you?"
5. If customer says YES: Ask for name and phone
6. Discuss collection date/time (check office rules)
7. Call supplier to confirm availability (smp_api action="call_supplier")
8. ONLY AFTER supplier confirms: Create booking (action="create_booking_quote")

NEVER auto-book. Always: Price → Push → Confirm → Supplier call → Book

QUALIFYING QUESTIONS:
- "What's your postcode?"
- "What items need collecting?" (furniture, appliances, household goods)
- "When do you need collection?"

LIGHT ITEMS WE HANDLE: furniture, appliances, household goods, office items, bags, boxes

SUPPLIER CALL TIMING: After price discussion and before final booking."""),
            ("human", "Customer: {input}\n\nStage: {stage}\nData: {extracted_info}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=8)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Proper business process with heavy item checking"""
        
        # Extract data with context
        extracted_data = self._extract_data(message, context)
        
        print(f"🔧 MAV DATA: {json.dumps(extracted_data, indent=2)}")
        
        # FIRST - Check for heavy items (strict enforcement)
        heavy_items = extracted_data.get('heavy_items', [])
        if heavy_items:
            print(f"🔧 HEAVY ITEMS DETECTED: {heavy_items}")
            return f"Sorry mate, {', '.join(heavy_items)} are too heavy for our Man & Van service. You need Skip Hire or Grab Hire for that type of waste. Let me transfer you to the right team!"
        
        # Continue with normal sales process
        stage = self._determine_stage(extracted_data, message)
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
            return "What's your postcode for Man & Van collection?"
    
    def _determine_stage(self, data: Dict, message: str) -> str:
        """Determine what stage of sales process we're at"""
        
        has_postcode = bool(data.get('postcode'))
        has_items = bool(data.get('items'))
        customer_interested = self._customer_wants_to_book(message)
        has_contact = bool(data.get('firstName') and data.get('phone'))
        has_date = bool(data.get('collection_date'))
        
        if not has_postcode or not has_items:
            return "need_info"
        elif has_postcode and has_items and not customer_interested:
            return "ready_for_pricing"
        elif customer_interested and not has_contact:
            return "customer_wants_to_book"
        elif has_contact and not has_date:
            return "need_collection_date"
        elif has_contact and has_date:
            return "ready_for_supplier_call"
        else:
            return "need_info"
    
    def _handle_info_gathering(self, data: Dict) -> str:
        """Ask qualifying questions"""
        if not data.get('postcode'):
            return "What's your postcode for the Man & Van collection?"
        if not data.get('items'):
            return "What items need collecting? (furniture, appliances, household goods, etc.)"
        return "Let me get you a Man & Van quote."
    
    def _handle_pricing(self, data: Dict, message: str) -> str:
        """Show pricing and push for sale"""
        extracted_info = f"""
Postcode: {data.get('postcode')}
Items: {data.get('items')}
Service: mav
Type: 6yd
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
        
        return "Perfect! When would you like the Man & Van to come?"
    
    def _handle_supplier_call(self, data: Dict, message: str) -> str:
        """Call supplier to check availability before final booking"""
        extracted_info = f"""
Postcode: {data.get('postcode')}
Service: mav
Type: 6yd
Customer: {data.get('firstName')}
Phone: {data.get('phone')}
Collection Date: {data.get('collection_date')}
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
Service: mav
Type: 6yd
Customer: {data.get('firstName')}
Phone: {data.get('phone')}
Collection Date: {data.get('collection_date')}
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
        """Extract data and check for heavy items"""
        data = {}
        
        # Check context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress', 'items', 'collection_date']:
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
        
        # Extract items and check for heavy restrictions
        light_items = [
            'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 
            'appliances', 'fridge', 'freezer', 'bags', 'boxes', 
            'household', 'office', 'clothes', 'books'
        ]
        heavy_items = [
            'brick', 'bricks', 'concrete', 'soil', 'rubble', 'stone',
            'sand', 'gravel', 'construction', 'building', 'demolition',
            'mortar', 'cement', 'tiles', 'hardcore'
        ]
        
        found_light = []
        found_heavy = []
        message_lower = message.lower()
        
        for item in light_items:
            if item in message_lower:
                found_light.append(item)
                
        for item in heavy_items:
            if item in message_lower:
                found_heavy.append(item)
        
        if found_light:
            data['items'] = ', '.join(found_light)
        if found_heavy:
            data['heavy_items'] = found_heavy
        else:
            data['heavy_items'] = []
        
        # Extract collection timing
        date_patterns = [
            r'next (\w+)',
            r'tomorrow',
            r'today',
            r'(\w+day)'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, message.lower())
            if match:
                data['collection_date'] = match.group(0)
                break
        
        data['service'] = 'mav'
        data['type'] = '6yd'
        
        return data
