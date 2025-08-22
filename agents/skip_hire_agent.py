# agents/skip_hire_agent.py - WORKING BOOKING VERSION
# CHANGES: Aggressive booking detection - if customer provides name/phone = BOOK

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

CRITICAL RULE: If customer provides NAME or PHONE + postcode + waste = THEY WANT TO BOOK

WORKFLOW:
1. Customer provides personal info (name/phone) + postcode + waste → IMMEDIATELY call create_booking_quote
2. Customer just wants price → call get_pricing then ask to book
3. Missing data → Ask once

API CALLS:
- BOOKING: smp_api(action="create_booking_quote", postcode=X, service="skip", type="8yd", firstName=X, phone=X, booking_ref=X)
- PRICING: smp_api(action="get_pricing", postcode=X, service="skip", type="8yd")

IMPORTANT: Name/phone + postcode + waste = AUTOMATIC BOOKING"""),
            ("human", "Customer: {input}\n\nData: {extracted_info}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=10)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """SIMPLE booking detection - if they give personal info, they want to book"""
        
        # Extract data
        extracted_data = self._extract_data(message, context)
        
        print(f"🔧 SKIP DATA: {json.dumps(extracted_data, indent=2)}")
        
        postcode = extracted_data.get('postcode')
        waste_type = extracted_data.get('waste_type')
        has_name = bool(extracted_data.get('firstName'))
        has_phone = bool(extracted_data.get('phone'))
        
        # SIMPLE RULE: Personal info + postcode + waste = BOOK
        should_book = (has_name or has_phone) and postcode and waste_type
        
        print(f"🎯 BOOKING DECISION:")
        print(f"   - Has name: {has_name} ({extracted_data.get('firstName')})")
        print(f"   - Has phone: {has_phone} ({extracted_data.get('phone')})")
        print(f"   - Has postcode: {bool(postcode)} ({postcode})")
        print(f"   - Has waste: {bool(waste_type)} ({waste_type})")
        print(f"   - SHOULD BOOK: {should_book}")
        
        if postcode and waste_type:
            action = "create_booking_quote" if should_book else "get_pricing"
            
            print(f"🔧 READY FOR API - {'🎯 BOOKING' if should_book else 'PRICING'} (action: {action})")
            
            extracted_info = f"""
Postcode: {postcode}
Waste Type: {waste_type}
Service: skip
Type: {extracted_data.get('size', '8yd')}
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
        if not waste_type:
            return "What type of waste?"
        
        return "Let me get you a quote."
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Extract all data from message"""
        data = {}
        
        # Context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress', 'waste_type']:
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
        
        # Extract name - BETTER PATTERNS
        name_patterns = [
            r'\bfor\s+(\w+)',  # "for Kanchan"
            r'\bname\s+(\w+)',  # "name Kanchan"  
            r'\bi\'?m\s+(\w+)'  # "I'm John"
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['firstName'] = match.group(1).title()
                break
        
        # Extract phone - BETTER PATTERNS
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
        
        # Extract waste type
        waste_types = ['construction', 'bricks', 'rubble', 'concrete', 'soil', 'garden', 'household', 'mixed']
        found_waste = []
        for waste in waste_types:
            if waste in message.lower():
                found_waste.append(waste)
        if found_waste:
            data['waste_type'] = ', '.join(found_waste)
        
        # Extract size
        if '8yd' in message or 'eight' in message.lower():
            data['size'] = '8yd'
        elif '6yd' in message or 'six' in message.lower():
            data['size'] = '6yd'
        else:
            data['size'] = '8yd'  # Default
        
        # Always generate booking ref
        import uuid
        data['booking_ref'] = str(uuid.uuid4())
        data['service'] = 'skip'
        data['type'] = data['size']
        
        return data
