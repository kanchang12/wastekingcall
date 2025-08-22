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
        self.rules_processor = RulesProcessor()
        rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        rule_text = rule_text.replace("{", "{{").replace("}", "}}")
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Man and Van specialist - friendly, British, and GET PRICING NOW!

CRITICAL API PARAMETERS:
- service: "mav"
- type: "4yd" or "6yd" or "8yd" or "12yd"
- postcode: "LS14ED" (no spaces)

MANDATORY API CALL:
smp_api(action="get_pricing", postcode="LS14ED", service="mav", type="6yd")

IMMEDIATE ACTION:
- If you have postcode + items: CALL smp_api IMMEDIATELY
- Use service="mav" ALWAYS

PERSONALITY:
- Start with: "Alright love!" or "Right then!"
- Get pricing first, chat later

WORKFLOW:
1. Extract postcode, items from message
2. Estimate size based on items
3. CALL smp_api with service="mav" immediately
4. Give price

VOLUME ESTIMATION:
- Few items (1-3 bags) = 4yd
- Medium load (3-6 bags) = 6yd  
- Large load (6+ bags) = 8yd
- House clearance = 12yd

Follow team rules:
""" + rule_text + """

CRITICAL: Call smp_api with service="mav" when you have postcode + items.
"""),
            ("human", """Customer: {input}

Extracted data: {extracted_info}

INSTRUCTION: If Ready for Pricing = True, CALL smp_api with service="mav"."""),
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
        
        # Extract items
        common_items = [
            'bags', 'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 
            'books', 'clothes', 'dumbbells', 'kettlebell', 'boxes', 'appliances',
            'fridge', 'freezer'
        ]
        
        found_items = []
        message_lower = message.lower()
        
        for item in common_items:
            if item in message_lower:
                found_items.append(item)
        
        # Extract quantity indicators
        quantity_indicators = []
        quantity_patterns = [
            r'(\d+)\s*(?:bags?|boxes?|items?)',
            r'(few|several|many)\s*(?:bags?|boxes?|items?)',
        ]
        
        for pattern in quantity_patterns:
            matches = re.findall(pattern, message_lower)
            quantity_indicators.extend(matches)
        
        if found_items or quantity_indicators:
            items_desc = []
            if quantity_indicators:
                items_desc.extend(quantity_indicators)
            if found_items:
                items_desc.extend(found_items)
            data['items'] = ', '.join(items_desc)
        else:
            missing.append('items')
        
        # Estimate volume
        volume_score = 0
        if 'items' in data:
            items_text = data['items'].lower()
            bag_matches = re.findall(r'(\d+)', items_text)
            for match in bag_matches:
                volume_score += int(match) if match.isdigit() else 3
            
            furniture_items = ['sofa', 'chair', 'table', 'bed', 'mattress']
            for item in furniture_items:
                if item in items_text:
                    volume_score += 5
        
        # Convert to size
        if volume_score <= 3:
            data['type'] = '4yd'
        elif volume_score <= 8:
            data['type'] = '6yd'
        elif volume_score <= 15:
            data['type'] = '8yd'
        else:
            data['type'] = '12yd'
        
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
        
        data['service'] = 'mav'  # CORRECT SERVICE
        data['missing_info'] = missing
        
        # Ready for pricing check
        has_postcode = 'postcode' in data
        has_items = 'items' in data
        data['ready_for_pricing'] = has_postcode and has_items
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        extracted_info = f"""
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Items: {extracted.get('items', 'NOT PROVIDED')}
Estimated Size: {extracted.get('type', '6yd')}
Service: mav
Ready for Pricing: {extracted.get('ready_for_pricing', False)}
Missing: {[x for x in extracted.get('missing_info', []) if x in ['postcode', 'items']]}

*** API Parameters: postcode={extracted.get('postcode', 'NOT PROVIDED')}, service=mav, type={extracted.get('type', '6yd')} ***
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
