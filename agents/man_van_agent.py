# agents/man_van_agent.py - ORIGINAL PDF RULES RESTORED
# CHANGES: Restored your original PDF rule book integration + fixed data extraction

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
        
        # RESTORED: Your original PDF rule book integration
        self.rules_processor = RulesProcessor()
        rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        rule_text = rule_text.replace("{", "{{").replace("}", "}}")
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Man & Van agent with STRICT RULES.

HEAVY ITEMS RULE:
Man & Van CANNOT handle: bricks, mortar, concrete, soil, tiles, construction waste, industrial waste

If heavy items detected: "Sorry mate, bricks/concrete/soil are too heavy for Man & Van. You need Skip Hire for that."

RULES FROM PDF KNOWLEDGE BASE:
""" + rule_text + """

WORKFLOW:
1. Check for heavy items FIRST - if found, REFUSE and suggest Skip Hire
2. If customer provides name + phone + says "book": Call create_booking_quote
3. If just pricing info: Call get_pricing then ask to book
4. Missing data → Ask once

Be direct. Follow PDF rules above."""),
            ("human", "Customer: {input}\n\nI have:\nPostcode: {postcode}\nItems: {items}\nSuitable: {suitable}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=8)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Process with heavy item checking and proper data extraction"""
        
        # FIXED: Proper data extraction
        extracted_data = self._extract_data_properly(message, context)
        
        print(f"🔧 MAV DATA: {json.dumps(extracted_data, indent=2)}")
        
        # FIRST - Check for heavy items (strict enforcement)
        heavy_items = extracted_data.get('heavy_items', [])
        if heavy_items:
            print(f"🔧 HEAVY ITEMS DETECTED: {heavy_items}")
            return f"Sorry mate, {', '.join(heavy_items)} are too heavy for our Man & Van service. You need Skip Hire or Grab Hire for that type of waste. Let me transfer you to the right team!"
        
        postcode = extracted_data.get('postcode')
        items = extracted_data.get('items')
        has_name = bool(extracted_data.get('firstName'))
        has_phone = bool(extracted_data.get('phone'))
        
        # SIMPLE RULE: If they have all info and said "book" = CREATE BOOKING
        wants_booking = 'book' in message.lower()
        has_all_info = postcode and items and has_name and has_phone
        
        print(f"🎯 DECISION:")
        print(f"   - Wants booking: {wants_booking}")
        print(f"   - Has all info: {has_all_info}")
        print(f"   - Name: {extracted_data.get('firstName')}")
        print(f"   - Phone: {extracted_data.get('phone')}")
        
        if wants_booking and has_all_info:
            action = "create_booking_quote"
            print(f"🔧 CREATING BOOKING IMMEDIATELY")
        elif postcode and items:
            action = "get_pricing"
            print(f"🔧 GETTING PRICING FIRST")
        else:
            # Missing data
            if not postcode:
                return "What's your postcode for Man & Van?"
            if not items:
                return "What items need collecting?"
            return "Let me get you a Man & Van quote."
        
        # Generate booking ref if booking
        if action == "create_booking_quote":
            import uuid
            extracted_data['booking_ref'] = str(uuid.uuid4())
        
        agent_input = {
            "input": message,
            "postcode": postcode or "NOT PROVIDED",
            "items": items or "NOT PROVIDED",
            "suitable": not bool(heavy_items),
            "action": action,
            **extracted_data
        }
        
        response = self.executor.invoke(agent_input)
        return response["output"]
    
    def _extract_data_properly(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """FIXED: Proper data extraction that actually works"""
        data = {}
        
        # Context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract postcode - FIXED patterns
        postcode_patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b',  # M1 1AB
            r'M1\s*1AB|M11AB',  # Specific patterns
        ]
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean = match.strip().replace(' ', '')
                if len(clean) >= 5:
                    data['postcode'] = clean
                    print(f"✅ FOUND POSTCODE: {clean}")
                    break
        
        # Extract name - FIXED patterns
        name_patterns = [
            r'[Nn]ame\s+(\w+\s+\w+)',  # "Name Kanchen Khosh"
            r'[Nn]ame\s+(\w+)',        # "Name Kanchen"
            r'my name is (\w+)',
            r'i\'m (\w+)',
            r'call me (\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip().title()
                data['firstName'] = name
                print(f"✅ FOUND NAME: {name}")
                break
        
        # Extract phone - FIXED patterns
        phone_patterns = [
            r'payment link to (\d{11})',  # "payment link to 07823656762"
            r'link to (\d{11})',          # "link to 07823656762"
            r'to (\d{11})',               # "to 07823656762"
            r'\b(07\d{9})\b',             # Any UK mobile
            r'\b(\d{11})\b'               # Any 11 digits
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                phone = match.group(1)
                data['phone'] = phone
                print(f"✅ FOUND PHONE: {phone}")
                break
        
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
            print(f"✅ FOUND LIGHT ITEMS: {data['items']}")
        
        if found_heavy:
            data['heavy_items'] = found_heavy
            print(f"❌ FOUND HEAVY ITEMS: {found_heavy}")
        else:
            data['heavy_items'] = []
        
        data['service'] = 'mav'
        data['type'] = '6yd'
        
        return data
