# grab_hire_agent.py - REPLACEMENT FILE
# CHANGES: Fixed routing (handles ALL except mav/skip), better data extraction, fixed booking flow

import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.rules_processor = RulesProcessor()
        
        # CHANGE: Updated routing - grab handles ALL services except mav and skip
        rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        rule_text = rule_text.replace("{", "{{").replace("}", "}}")

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Grab Hire specialist - friendly, British, and GET PRICING NOW!

IMPORTANT ROUTING: You handle ALL waste services EXCEPT "mav" (man and van) and "skip" (skip hire).
This includes: grab hire, general waste, large items, heavy materials, construction waste, garden waste, office clearance, etc.

CRITICAL API PARAMETERS:
- service: "grab" (for grab hire) or determine appropriate service
- type: "8yd" (default for grab)
- postcode: Clean format like "LS14ED" (no spaces for API)

MANDATORY WORKFLOW:
1. Extract postcode + material type from message
2. If you have both: CALL smp_api IMMEDIATELY with service="grab"
3. Show price to customer
4. If customer wants to book: CALL smp_api to create_booking_quote
5. Booking will automatically call supplier

PERSONALITY:
- Start with: "Alright love!" or "Right then!"
- Get pricing first, then book if customer wants

MATERIAL GUIDANCE:
- Heavy materials (soil, rubble, concrete) = grab lorry ideal
- Large volumes = grab lorry
- Light materials = can still use grab if customer prefers

Follow team rules:
""" + rule_text + """

CRITICAL: Always call smp_api with correct service type when you have postcode + material."""),
            ("human", """Customer: {input}

Extracted data: {extracted_info}

INSTRUCTION: If Ready for Pricing = True, CALL smp_api immediately."""),
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
            max_iterations=10  # CHANGE: Increased for booking flow
        )
    
    def extract_and_validate_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """CHANGE: Enhanced data extraction with context handling"""
        data = {}
        missing = []
        
        # CHANGE: Check context first to prevent data loss
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract name
        name_patterns = [
            r'name\s+(?:is\s+)?(\w+)',
            r'i\'?m\s+(\w+)',
            r'my\s+name\s+is\s+(\w+)',
            r'this\s+is\s+(\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['firstName'] = match.group(1).title()
                break
        
        # CHANGE: Improved postcode extraction
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
        
        # CHANGE: Enhanced material detection for all waste types
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
            r'\b(\d{11})\b',
            r'phone\s+(?:is\s+)?(\d{10,11})',
            r'mobile\s+(?:is\s+)?(\d{10,11})',
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
        
        # CHANGE: Service determination based on materials and context
        service_type = 'grab'  # Default for grab agent
        
        # Check if specific service mentioned
        if 'grab' in message_lower or 'lorry' in message_lower:
            service_type = 'grab'
        elif found_material and material_category == 'heavy':
            service_type = 'grab'
        
        data['service'] = service_type
        data['type'] = '8yd'  # Default size
        
        # Check what's missing for pricing
        if 'postcode' not in data:
            missing.append('postcode')
        if not found_material and 'material_type' not in data:
            missing.append('material_type')
        
        data['missing_info'] = missing
        data['ready_for_pricing'] = len(missing) == 0
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """CHANGE: Enhanced message processing with better context handling"""
        
        # CHANGE: Clear old data if new postcode detected
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
        
        extracted_info = f"""
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Material Type: {extracted.get('material_type', 'NOT PROVIDED')}
Material Category: {extracted.get('material_category', 'unknown')}
Service: {extracted.get('service', 'grab')}
Type: {extracted.get('type', '8yd')}
Ready for Pricing: {extracted.get('ready_for_pricing', False)}
Missing: {extracted.get('missing_info', [])}
Customer Name: {extracted.get('firstName', 'NOT PROVIDED')}
Customer Phone: {extracted.get('phone', 'NOT PROVIDED')}

*** API Parameters: postcode={extracted.get('postcode', 'NOT PROVIDED')}, service={extracted.get('service', 'grab')}, type={extracted.get('type', '8yd')} ***
"""
        
        agent_input = {
            "input": message,
            "extracted_info": extracted_info
        }
        
        # Add all extracted data to agent input
        agent_input.update(extracted)
        
        try:
            response = self.executor.invoke(agent_input)
            return response["output"]
        except Exception as e:
            print(f"❌ Grab Agent Error: {str(e)}")
            return "Right then! I need your postcode and what type of waste you have to get you a quote. What's your postcode?"
