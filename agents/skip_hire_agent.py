import json 
import re
import os
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        # Load rules from PDF properly
        try:
            self.rules_processor = RulesProcessor()
            # Get rules specifically for skip_hire
            skip_rules = self.rules_processor.get_rules_for_agent("skip_hire")
            rule_text = json.dumps(skip_rules, indent=2)
            rule_text = rule_text.replace("{", "{{").replace("}", "}}")
        except Exception as e:
            print(f"Warning: Could not load rules from PDF: {e}")
            # Fallback rules if PDF loading fails
            rule_text = """
            SKIP HIRE RULES:
            - CAN handle: construction waste, bricks, concrete, soil, garden waste, household waste
            - CANNOT handle: hazardous materials, asbestos, chemicals, paint, batteries
            - Sizes available: 4yd, 6yd, 8yd, 12yd, 16yd, 20yd
            - Placement: drive, road (permit may be required)
            """
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are the WasteKing Skip Hire specialist - friendly, British, and NO HARDCODED DATA!

RULES FROM PDF - MUST FOLLOW:
{rule_text}

CRITICAL API PARAMETERS:
- service: "skip" (NOT "skip-hire")
- type: "4yd", "6yd", "8yd", "12yd", "16yd", "20yd" 
- postcode: NO SPACES (e.g., "LS14ED")

MANDATORY RULE - NO HARDCODED DATA:
- ONLY use data from customer message
- NEVER use example postcodes like "LS14ED"
- NEVER use fallback data
- IF missing postcode: ASK FOR IT
- IF missing waste type: ASK FOR IT

API CALL RULE:
- ONLY call smp_api if Ready for Pricing = True
- Ready for Pricing = REAL postcode + REAL waste type from user
- NO API calls with missing or fake data

PERSONALITY:
- Start with: "Right then!" or "Alright!"
- Ask for missing info politely

WORKFLOW:
1. Check extracted data
2. If Ready for Pricing = True: CALL smp_api immediately
3. If Ready for Pricing = False: ASK for missing info

NO EXAMPLES IN PROMPTS - USE ONLY REAL USER DATA!
"""),
            ("human", """Customer: {{input}}

Extracted data: {{extracted_info}}

CRITICAL: Only call smp_api if Ready for Pricing = True with REAL user data!
"""),
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
        """Extract customer data for skip hire"""
        data = {}
        missing = []
        
        # Extract postcode - FORCE NO SPACES
        postcode_found = False
        postcode_patterns = [
            r'([A-Z]{1,2}\d{1,4}[A-Z]?\d?[A-Z]{0,2})',
            r'postcode\s*:?\s*([A-Z0-9\s]+)',
            r'at\s+([A-Z0-9\s]{4,8})',
            r'in\s+([A-Z0-9\s]{4,8})',
        ]
        
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                # FORCE remove ALL spaces and clean
                clean_match = match.strip().replace(' ', '').replace('\t', '')
                if len(clean_match) >= 4 and any(c.isdigit() for c in clean_match) and any(c.isalpha() for c in clean_match):
                    data['postcode'] = clean_match  # LS14ED (no spaces!)
                    postcode_found = True
                    print(f"🔧 POSTCODE EXTRACTED: '{match}' → '{clean_match}'")
                    break
            if postcode_found:
                break
        
        if not postcode_found:
            missing.append('postcode')
        
        # Extract waste type and items
        waste_types = [
            'construction', 'building', 'renovation', 'garden', 'household', 'mixed',
            'bricks', 'concrete', 'soil', 'rubble', 'furniture', 'general', 'industrial'
        ]
        
        found_waste_types = []
        message_lower = message.lower()
        
        for waste_type in waste_types:
            if waste_type in message_lower:
                found_waste_types.append(waste_type)
        
        # Extract specific items
        specific_items = [
            'bags', 'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress',
            'brick', 'bricks', 'concrete', 'soil', 'tiles', 'plaster', 'wood',
            'metal', 'plastic', 'cardboard', 'books', 'clothes'
        ]
        
        found_items = []
        for item in specific_items:
            if item in message_lower:
                found_items.append(item)
        
        if found_waste_types or found_items:
            all_waste = found_waste_types + found_items
            data['waste_type'] = ', '.join(set(all_waste))  # Remove duplicates
        else:
            missing.append('waste_type')
        
        # Estimate skip size based on waste description
        size_score = 0
        if 'waste_type' in data:
            waste_text = data['waste_type'].lower()
            
            # Extract quantities
            quantity_matches = re.findall(r'(\d+)', message_lower)
            for match in quantity_matches:
                if match.isdigit():
                    size_score += int(match)
            
            # Size indicators from text
            if any(word in message_lower for word in ['small', 'few', 'little']):
                size_score += 2
            elif any(word in message_lower for word in ['medium', 'moderate']):
                size_score += 5
            elif any(word in message_lower for word in ['large', 'big', 'major', 'full']):
                size_score += 10
            elif any(word in message_lower for word in ['huge', 'massive', 'entire']):
                size_score += 15
            
            # Item-based scoring
            heavy_items = ['brick', 'concrete', 'soil', 'rubble']
            for item in heavy_items:
                if item in waste_text:
                    size_score += 3
            
            furniture_items = ['sofa', 'bed', 'table', 'furniture']
            for item in furniture_items:
                if item in waste_text:
                    size_score += 2
        
        # Convert score to skip size
        if size_score <= 3:
            data['type'] = '4yd'
        elif size_score <= 6:
            data['type'] = '6yd'
        elif size_score <= 10:
            data['type'] = '8yd'
        elif size_score <= 15:
            data['type'] = '12yd'
        elif size_score <= 20:
            data['type'] = '16yd'
        else:
            data['type'] = '20yd'
        
        # Extract other details
        # Name
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
        
        # Phone
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
        
        # Email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, message)
        if email_match:
            data['emailAddress'] = email_match.group()
        
        # FORCE CORRECT SERVICE NAME
        data['service'] = 'skip'  # NEVER "skip-hire"!
        data['missing_info'] = missing
        
        # Ready for pricing check
        has_postcode = 'postcode' in data
        has_waste_type = 'waste_type' in data
        data['ready_for_pricing'] = has_postcode and has_waste_type
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        extracted_info = f"""
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Waste Type: {extracted.get('waste_type', 'NOT PROVIDED')}
Estimated Skip Size: {extracted.get('type', '8yd')}
Service: skip (NEVER skip-hire!)
Ready for Pricing: {extracted.get('ready_for_pricing', False)}
Missing: {[x for x in extracted.get('missing_info', []) if x in ['postcode', 'waste_type']]}

*** CRITICAL: Use service="skip" with postcode="{extracted.get('postcode', 'MISSING')}" ***
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
