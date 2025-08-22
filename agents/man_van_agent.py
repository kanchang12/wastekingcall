# man_van_agent.py - REPLACEMENT FILE
# CHANGES: Minimal changes, enhanced data extraction, strict heavy item restrictions maintained

import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Man & Van agent with STRICT RULES.

HEAVY ITEMS RULE - CANNOT HANDLE:
bricks, mortar, concrete, soil, tiles, construction waste, industrial waste, rubble, hardcore, sand, gravel, stone, demolition waste

If heavy items detected: "Sorry mate, bricks/concrete/soil are too heavy for Man & Van. You need Skip Hire or Grab Hire for that."

WORKFLOW:
1. Check for heavy items FIRST - if found, REFUSE and suggest other services
2. Light items + postcode → Call smp_api(action="get_pricing", postcode=X, service="mav", type="6yd")
3. If customer wants to book → Call smp_api(action="create_booking_quote") 
4. Missing data → Ask once

LIGHT ITEMS WE HANDLE: furniture, appliances, household goods, office items, bags, boxes, garden waste (leaves/grass only)

Be direct. Follow rules strictly."""),
            ("human", "Customer: {input}\n\nData: {extracted_info}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=8)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """CHANGE: Enhanced processing with context handling"""
        
        # CHANGE: Extract data with context
        extracted_data = self._extract_data(message, context)
        
        print(f"🔧 MAV DATA: {json.dumps(extracted_data, indent=2)}")
        
        # CHANGE: FIRST - Check for heavy items (strict enforcement)
        heavy_items = extracted_data.get('heavy_items', [])
        if heavy_items:
            print(f"🔧 HEAVY ITEMS DETECTED: {heavy_items}")
            return f"Sorry mate, {', '.join(heavy_items)} are too heavy for our Man & Van service. You need Skip Hire or Grab Hire for that type of waste. Let me transfer you to the right team!"
        
        # Check if ready for API call (suitable items + postcode)
        postcode = extracted_data.get('postcode')
        items = extracted_data.get('items')
        
        if postcode and items and not heavy_items:
            print(f"🔧 READY FOR API - calling immediately")
            
            extracted_info = f"""
Postcode: {postcode}
Items: {items}
Service: mav
Type: 6yd
Heavy Items: {heavy_items}
Customer Name: {extracted_data.get('firstName', 'NOT PROVIDED')}
Customer Phone: {extracted_data.get('phone', 'NOT PROVIDED')}
Ready for API: True
"""
            
            agent_input = {
                "input": message,
                "extracted_info": extracted_info,
                **extracted_data
            }
            
            response = self.executor.invoke(agent_input)
            return response["output"]
        
        # Missing data - ask directly
        if not postcode:
            return "I need your postcode to get Man & Van pricing. What's your postcode?"
        
        if not items:
            return "What items do you need collected? (furniture, appliances, household goods, etc.)"
        
        return "Let me get you a Man & Van quote."
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """CHANGE: Enhanced data extraction with context handling"""
        data = {}
        
        # Check context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract postcode
        postcode = self._get_postcode(message, context)
        if postcode:
            data['postcode'] = postcode
        
        # Extract items and check for heavy restrictions
        items = self._get_items(message, context)
        if items:
            data['items'] = items
        
        # CHANGE: Enhanced heavy item detection
        heavy_items = self._check_heavy_items(items or "")
        data['heavy_items'] = heavy_items
        
        # Extract customer info
        name_match = re.search(r'(?:name is|i\'m|call me)\s+(\w+)', message, re.IGNORECASE)
        if name_match:
            data['firstName'] = name_match.group(1).title()
        
        phone_match = re.search(r'\b(\d{11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
        
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
        if email_match:
            data['emailAddress'] = email_match.group()
        
        data['service'] = 'mav'
        data['type'] = '6yd'
        
        return data
    
    def _check_heavy_items(self, items: str) -> List[str]:
        """CHANGE: Enhanced heavy item detection with more items"""
        if not items:
            return []
            
        items_lower = items.lower()
        restricted = [
            'brick', 'bricks', 'mortar', 'concrete', 'cement', 'soil', 'dirt', 'muck',
            'tile', 'tiles', 'stone', 'stones', 'rubble', 'sand', 'gravel', 'hardcore',
            'industrial waste', 'construction waste', 'building waste', 'demolition',
            'plaster', 'asbestos', 'metal waste'
        ]
        
        found_restricted = []
        for item in restricted:
            if item in items_lower:
                found_restricted.append(item)
        
        return found_restricted
    
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
    
    def _get_items(self, message: str, context: Dict) -> str:
        """Extract items with context priority"""
        # Check context first
        if context and context.get('items'):
            return context['items']
        
        # Extract from message
        mav_items = [
            'bags', 'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 
            'books', 'clothes', 'boxes', 'appliances', 'fridge', 'freezer',
            'washing machine', 'dishwasher', 'office', 'desk', 'cabinet',
            'garden waste', 'leaves', 'grass', 'household', 'general',
            # Also include restricted items for detection
            'brick', 'bricks', 'mortar', 'concrete', 'soil', 'tiles', 'industrial'
        ]
        found = []
        message_lower = message.lower()
        for item in mav_items:
            if item in message_lower:
                found.append(item)
        
        return ', '.join(found) if found else None
