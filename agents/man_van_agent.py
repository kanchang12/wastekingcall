# agents/man_van_agent.py - WORKING BOOKING VERSION
# CHANGES: Aggressive booking detection - if customer provides name/phone = BOOK

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

CRITICAL RULE: If customer provides NAME or PHONE + postcode + light items = THEY WANT TO BOOK

WORKFLOW:
1. Check heavy items FIRST - refuse if found
2. Customer provides personal info (name/phone) + postcode + light items → IMMEDIATELY call create_booking_quote
3. Customer just wants price → call get_pricing then ask to book
4. Missing data → Ask once

API CALLS:
- BOOKING: smp_api(action="create_booking_quote", postcode=X, service="mav", type="6yd", firstName=X, phone=X, booking_ref=X)
- PRICING: smp_api(action="get_pricing", postcode=X, service="mav", type="6yd")

LIGHT ITEMS: furniture, appliances, household goods, bags, boxes"""),
            ("human", "Customer: {input}\n\nData: {extracted_info}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=10)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Enhanced processing with heavy item checking and booking detection"""
        
        # Extract data
        extracted_data = self._extract_data(message, context)
        
        print(f"🔧 MAV DATA: {json.dumps(extracted_data, indent=2)}")
        
        # FIRST - Check for heavy items
        heavy_items = extracted_data.get('heavy_items', [])
        if heavy_items:
            print(f"🔧 HEAVY ITEMS DETECTED: {heavy_items}")
            return f"Sorry mate, {', '.join(heavy_items)} are too heavy for our Man & Van service. You need Skip Hire or Grab Hire for that type of waste."
        
        postcode = extracted_data.get('postcode')
        items = extracted_data.get('items')
        has_name = bool(extracted_data.get('firstName'))
        has_phone = bool(extracted_data.get('phone'))
        
        # SIMPLE RULE: Personal info + postcode + items = BOOK
        should_book = (has_name or has_phone) and postcode and items
        
        print(f"🎯 BOOKING DECISION:")
        print(f"   - Has name: {has_name} ({extracted_data.get('firstName')})")
        print(f"   - Has phone: {has_phone} ({extracted_data.get('phone')})")
        print(f"   - Has postcode: {bool(postcode)} ({postcode})")
        print(f"   - Has items: {bool(items)} ({items})")
        print(f"   - SHOULD BOOK: {should_book}")
        
        if postcode and items and not heavy_items:
            action = "create_booking_quote" if should_book else "get_pricing"
            
            print(f"🔧 READY FOR API - {'🎯 BOOKING' if should_book else 'PRICING'} (action: {action})")
            
            extracted_info = f"""
Postcode: {postcode}
Items: {items}
Service: mav
Type: 6yd
Heavy Items: {heavy_items}
Customer Name: {extracted_data.get('firstName', 'NOT PROVIDED')}
Customer Phone: {extracted_data.get('phone', 'NOT PROVIDED')}
Action: {action}
Should Book: {should_book}
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
        
        # Missing data
        if not postcode:
            return "What's your postcode?"
        if not items:
            return "What items need collecting? (furniture, appliances, household goods, etc.)"
        
        return "Let me get you a Man & Van quote."
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Extract all data and check for heavy items"""
        data = {}
        
        # Context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract postcode
        postcode_patterns = [
            r'\bat\s+([A-Z0-9]{4,8})',  # "at LS14ED"
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})\b',  # LS14ED
        ]
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean = match.strip().replace(' ', '')
                if len(clean) >= 5:
                    data['postcode'] = clean
                    break
        
        # Extract name
        name_patterns = [
            r'\bfor\s+(\w+)',  # "for John"
            r'\bname\s+(\w+)',  # "name John"  
            r'\bi\'?m\s+(\w+)'  # "I'm John"
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['firstName'] = match.group(1).title()
                break
        
        # Extract phone
        phone_patterns = [
            r'(?:to|link to|phone|number)\s+(\d{11})',  # "to 07823656762"
            r'\b(07\d{9})\b',  # Mobile
            r'\b(\d{11})\b'    # Any 11 digits
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                data['phone'] = match.group(1)
                break
        
        # Extract items and check for heavy restrictions
        light_items = [
            'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 
            'appliances', 'fridge', 'freezer', 'bags', 'boxes', 
            'household', 'office', 'clothes', 'books'
        ]
        heavy_items = [
            'brick', 'bricks', 'concrete', 'soil', 'rubble', 'stone',
            'sand', 'gravel', 'construction', 'building', 'demolition'
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
        
        # Always generate booking ref
        import uuid
        data['booking_ref'] = str(uuid.uuid4())
        data['service'] = 'mav'
        data['type'] = '6yd'
        
        return data
