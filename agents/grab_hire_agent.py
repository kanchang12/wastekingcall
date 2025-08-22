import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

# FIXED GrabHireAgent
class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.rules_processor = RulesProcessor()
        rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        rule_text = rule_text.replace("{", "{{").replace("}", "}}")

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Grab Hire specialist - friendly, British, and GET PRICING NOW!

CRITICAL API PARAMETERS:
- service: "grab"
- type: "8yd" (default for grab)
- postcode: "LS14ED" (no spaces)

MANDATORY API CALL:
smp_api(action="get_pricing", postcode="LS14ED", service="grab", type="8yd")

IMMEDIATE ACTION:
- If you have postcode + material type: CALL smp_api IMMEDIATELY
- Use service="grab" ALWAYS

PERSONALITY:
- Start with: "Alright love!" or "Right then!"
- Get pricing first

WORKFLOW:
1. Extract postcode, material type from message
2. CALL smp_api with service="grab" immediately
3. Give price

MATERIAL RULES:
- Heavy materials (soil, muck, rubble) = grab lorry ideal
- Light materials = suggest skip or MAV instead

Follow team rules:
""" + rule_text + """

CRITICAL: Call smp_api with service="grab" when you have postcode + material.
"""),
            ("human", """Customer: {input}

Extracted data: {extracted_info}

INSTRUCTION: If Ready for Pricing = True, CALL smp_api with service="grab"."""),
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
            max_iterations=5
        )
    
    def extract_and_validate_data(self, message: str) -> Dict[str, Any]:
        """Extract customer data and check what's missing"""
        data = {}
        missing = []
        
        # Extract name
        name_patterns = [
            r'name\s+(?:is\s+)?(\w+)',
            r'i\'?m\s+(\w+)',
            r'my\s+name\s+is\s+(\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['firstName'] = match.group(1).title()
                break
        if 'firstName' not in data:
            missing.append('name')
        
        # Extract postcode - NO SPACES
        postcode_found = False
        postcode_patterns = [
            r'([A-Z]{1,2}\d{1,4}[A-Z]?\d?[A-Z]{0,2})',
            r'postcode\s*:?\s*([A-Z0-9]+)',
            r'at\s+([A-Z0-9]{4,8})',
            r'in\s+([A-Z0-9]{4,8})',
        ]
        
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean_match = match.strip().replace(' ', '')
                if len(clean_match) >= 4 and any(c.isdigit() for c in clean_match) and any(c.isalpha() for c in clean_match):
                    data['postcode'] = clean_match  # LS14ED
                    postcode_found = True
                    break
            if postcode_found:
                break
        
        if not postcode_found:
            missing.append('postcode')
        
        # Extract material type
        material_keywords = {
            'soil': 'heavy',
            'muck': 'heavy',
            'rubble': 'heavy',
            'hardcore': 'heavy',
            'sand': 'heavy',
            'gravel': 'heavy',
            'concrete': 'heavy',
            'stone': 'heavy',
            'household': 'light',
            'general': 'light',
            'office': 'light'
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
        else:
            missing.append('material_type')
        
        # Extract phone
        phone_patterns = [
            r'phone\s+(?:is\s+)?(\d{11})',
            r'mobile\s+(?:is\s+)?(\d{11})',
            r'\b(\d{11})\b'
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
        
        data['type'] = '8yd'  # Default for grab
        data['service'] = 'grab'  # CORRECT SERVICE
        data['missing_info'] = missing
        
        # Ready for pricing check
        has_postcode = 'postcode' in data
        has_material = 'material_type' in data
        data['ready_for_pricing'] = has_postcode and has_material
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        extracted_info = f"""
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Material Type: {extracted.get('material_type', 'NOT PROVIDED')}
Material Category: {extracted.get('material_category', 'unknown')}
Service: grab
Type: 8yd
Ready for Pricing: {extracted.get('ready_for_pricing', False)}
Missing: {[x for x in extracted.get('missing_info', []) if x in ['postcode', 'material_type']]}

*** API Parameters: postcode={extracted.get('postcode', 'NOT PROVIDED')}, service=grab, type=8yd ***
"""
        
        agent_input = {
            "input": message,
            "extracted_info": extracted_info
        }
        
        if context:
            for k, v in context.items():
                agent_input[k] = v
                
        agent_input.update(extracted)
        response = self.executor.invoke(agent_input)
        return response["output"]
