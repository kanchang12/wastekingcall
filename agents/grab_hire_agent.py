# agents/grab_hire_agent.py - WORKING BOOKING VERSION  
# CHANGES: Aggressive booking detection - if customer provides name/phone = BOOK

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

CRITICAL RULE: If customer provides NAME or PHONE + postcode + materials = THEY WANT TO BOOK

WORKFLOW:
1. Customer provides personal info (name/phone) + postcode + materials → IMMEDIATELY call create_booking_quote
2. Customer just wants price → call get_pricing then ask to book  
3. Missing data → Ask once

API CALLS:
- BOOKING: smp_api(action="create_booking_quote", postcode=X, service="grab", type="8yd", firstName=X, phone=X, booking_ref=X)
- PRICING: smp_api(action="get_pricing", postcode=X, service="grab", type="8yd")

IMPORTANT: Name/phone + postcode + materials = AUTOMATIC BOOKING"""),
            ("human", """Customer: {input}

Data: {extracted_info}"""),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=10)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """SIMPLE booking detection - if they give personal info, they want to book"""
        
        # Extract data
        extracted_data = self._extract_data(message, context)
        
        print(f"🔧 GRAB DATA: {json.dumps(extracted_data, indent=2)}")
        
        postcode = extracted_data.get('postcode')
        materials = extracted_data.get('material_type')
        has_name = bool(extracted_data.get('firstName'))
        has_phone = bool(extracted_data.get('phone'))
        
        # SIMPLE RULE: Personal info + postcode + materials = BOOK
        should_book = (has_name or has_phone) and postcode and materials
        
        print(f"🎯 BOOKING DECISION:")
        print(f"   - Has name: {has_name} ({extracted_data.get('firstName')})")
        print(f"   - Has phone: {has_phone} ({extracted_data.get('phone')})")
        print(f"   - Has postcode: {bool(postcode)} ({postcode})")
        print(f"   - Has materials: {bool(materials)} ({materials})")
        print(f"   - SHOULD BOOK: {should_book}")
        
        if postcode and materials:
            action = "create_booking_quote" if should_book else "get_pricing"
            
            print(f"🔧 READY FOR API - {'🎯 BOOKING' if should_book else 'PRICING'} (action: {action})")
            
            extracted_info = f"""
Postcode: {postcode}
Material Type: {materials}
Service: grab
Type: {extracted_data.get('type', '8yd')}
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
        if not materials:
            return "What type of waste/materials?"
        
        return "Let me get you a quote."
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Extract all data from message"""
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
        
        # Extract name - BETTER PATTERNS
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
        
        # Extract materials
        materials = [
            'soil', 'muck', 'rubble', 'concrete', 'brick', 'sand', 'gravel',
            'construction', 'building', 'demolition', 'household', 'office', 
            'garden', 'wood', 'metal', 'general'
        ]
        found_materials = []
        for material in materials:
            if material in message.lower():
                found_materials.append(material)
        if found_materials:
            data['material_type'] = ', '.join(found_materials)
        
        # Always generate booking ref
        import uuid
        data['booking_ref'] = str(uuid.uuid4())
        data['service'] = 'grab'
        data['type'] = '8yd'
        
        return data
