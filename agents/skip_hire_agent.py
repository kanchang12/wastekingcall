import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.rules_processor = RulesProcessor()
        
        # Get rules and escape curly braces for template
        raw_rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        rule_text = raw_rule_text.replace("{", "{{").replace("}", "}}")

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Skip Hire specialist - friendly, British, and GET PRICING NOW!

IMMEDIATE ACTION REQUIRED:
- If you have postcode + waste type + size: CALL smp_api IMMEDIATELY
- Use service="skip-hire" (NOT "skip")
- Use postcode without spaces (LS14ED not LS14 ED)
- NEVER ask questions if you have enough info for pricing

MANDATORY API CALL FORMAT:
smp_api(action="get_pricing", postcode="LS14ED", service="skip-hire", type="8yd")

STEP-BY-STEP PROCESS:
1. Extract postcode, waste type, size from message
2. If you have all three: IMMEDIATELY call smp_api with service="skip-hire"
3. Give price to customer
4. Ask for name only if they want to book

PERSONALITY:
- Start with: "Right then!" or "Alright love!"
- Be friendly but GET THE PRICE FIRST

WASTE CATEGORIES:
- construction, building, rubble, concrete, soil, bricks = HEAVY = max 8yd
- household, general, garden, furniture = LIGHT = any size

CRITICAL RULES:
1. ALWAYS use service="skip-hire" in API calls
2. ALWAYS use postcode without spaces (LS14ED not LS14 ED)
3. NEVER refuse pricing due to time/office hours
4. CALL smp_api IMMEDIATELY when you have postcode + waste + size

Follow team rules:
""" + rule_text + """

MANDATORY: Call smp_api with service="skip-hire" immediately when you have the data.
"""),
            ("human", """Customer: {input}

Extracted data: {extracted_info}

INSTRUCTION: If Ready for Pricing = True, IMMEDIATELY call smp_api with service="skip-hire"."""),
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
            r'my\s+name\s+is\s+(\w+)',
            r'call\s+me\s+(\w+)',
            r'this\s+is\s+(\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['firstName'] = match.group(1).title()
                break
        if 'firstName' not in data:
            missing.append('name')
        
        # Extract postcode - KEEP ORIGINAL FORMAT WITHOUT SPACES
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
                    data['postcode'] = clean_match  # Keep without spaces: LS14ED
                    postcode_found = True
                    break
            if postcode_found:
                break
        
        if not postcode_found:
            missing.append('postcode')
        
        # Extract waste type
        waste_keywords = {
            'construction': 'heavy',
            'building': 'heavy', 
            'concrete': 'heavy',
            'rubble': 'heavy',
            'soil': 'heavy',
            'bricks': 'heavy',
            'demolition': 'heavy',
            'household': 'light',
            'general': 'light',
            'garden': 'light',
            'furniture': 'light',
            'office': 'light',
            'waste': 'general'  # Generic fallback
        }
        
        message_lower = message.lower()
        found_waste = None
        waste_category = None
        
        for keyword, category in waste_keywords.items():
            if keyword in message_lower:
                found_waste = keyword
                waste_category = category
                break
        
        if found_waste:
            data['waste_type'] = found_waste
            data['waste_category'] = waste_category
        else:
            missing.append('waste_type')
        
        # Extract size
        size_patterns = [
            r'(\d+)\s*(?:yard|yd|y)',
            r'(four|six|eight|ten|twelve|fourteen)',
            r'an?\s+(4|6|8|10|12|14)',
        ]
        
        size_map = {'four': '4', 'six': '6', 'eight': '8', 'ten': '10', 'twelve': '12', 'fourteen': '14'}
        
        size_found = False
        for pattern in size_patterns:
            match = re.search(pattern, message_lower)
            if match:
                size_word = match.group(1)
                size_num = size_map.get(size_word, size_word)
                data['type'] = f"{size_num}yd"
                size_found = True
                break
        
        if not size_found:
            # Default based on waste type
            if waste_category == 'heavy':
                data['type'] = '8yd'  # Max for heavy
            else:
                data['type'] = '8yd'  # Default
        
        # Extract additional details
        if 'driveway' in message_lower:
            data['placement'] = 'driveway'
        elif 'road' in message_lower:
            data['placement'] = 'road'
            
        if 'monday' in message_lower:
            data['requested_day'] = 'monday'
        
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
        
        # CRITICAL SETTINGS
        data['service'] = 'skip-hire'  # CORRECT SERVICE NAME
        data['missing_info'] = missing
        
        # Check if ready for pricing (name NOT required)
        has_postcode = 'postcode' in data
        has_waste = 'waste_type' in data  
        has_size = 'type' in data
        
        data['ready_for_pricing'] = has_postcode and has_waste and has_size
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        # Create extracted info summary
        extracted_info = f"""
Postcode: {extracted.get('postcode', 'NOT PROVIDED')} (NO SPACES FORMAT)
Waste Type: {extracted.get('waste_type', 'NOT PROVIDED')}
Waste Category: {extracted.get('waste_category', 'unknown')}
Skip Size: {extracted.get('type', '8yd')}
Service: skip-hire
Placement: {extracted.get('placement', 'not specified')}
Requested Day: {extracted.get('requested_day', 'not specified')}
Ready for Pricing: {extracted.get('ready_for_pricing', False)}
Missing for Pricing: {[x for x in extracted.get('missing_info', []) if x in ['postcode', 'waste_type']]}

*** IF Ready for Pricing = True, CALL smp_api WITH service="skip-hire" IMMEDIATELY ***
*** USE POSTCODE WITHOUT SPACES: {extracted.get('postcode', 'NOT PROVIDED')} ***
"""
        
        agent_input = {
            "input": message,
            "extracted_info": extracted_info
        }
        
        if context:
            for k, v in context.items():
                agent_input[k] = v
                
        # Add extracted data for tools
        agent_input.update(extracted)

        response = self.executor.invoke(agent_input)
        return response["output"]
