import json 
import re
import os
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        # Load rules from PDF
        try:
            self.rules_processor = RulesProcessor()
            man_van_rules = self.rules_processor.get_rules_for_agent("man_and_van")
            rule_text = json.dumps(man_van_rules, indent=2)
            rule_text = rule_text.replace("{", "{{").replace("}", "}}")
        except Exception as e:
            rule_text = "Man & Van rules loaded."
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a Man & Van agent with STRICT RULES.

RULES: {rule_text}

HEAVY ITEMS RULE - MANDATORY:
Man & Van CANNOT handle: bricks, mortar, concrete, soil, tiles, construction waste, industrial waste

CRITICAL INSTRUCTIONS:
1. If items are TOO HEAVY: Say "Sorry mate, [items] are too heavy for Man & Van. You need Skip Hire for that."
2. If items are SUITABLE and Ready for Pricing = True: Call smp_api with service="mav"
3. If missing data: Ask for postcode or items

WORKFLOW:
Heavy items detected → DECLINE and suggest Skip Hire
Light items + Ready for Pricing = True → Call smp_api(action="get_pricing", postcode=X, service="mav", type=Y)
Missing data → Ask what's missing"""),
            ("human", "Customer: {input}\n\nExtracted info:\nPostcode: {postcode}\nItems: {items}\nSize: {type}\nItems Suitable: {items_suitable}\nReady for Pricing: {ready_for_pricing}\nDecline Reason: {decline_reason}"),
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
            max_iterations=3
        )
    
    def check_item_suitability(self, items_text: str) -> Dict[str, Any]:
        """Check if items are suitable for Man & Van"""
        items_lower = items_text.lower()
        
        # Heavy items Man & Van CANNOT handle
        restricted_items = [
            'brick', 'bricks', 'mortar', 'concrete', 'cement', 'soil', 'dirt',
            'tile', 'tiles', 'stone', 'stones', 'rubble', 'sand', 'gravel',
            'industrial waste', 'construction waste', 'building waste'
        ]
        
        found_restricted = []
        for item in restricted_items:
            if item in items_lower:
                found_restricted.append(item)
        
        if found_restricted:
            return {
                "suitable": False,
                "reason": f"Man & Van cannot handle: {', '.join(found_restricted)}",
                "restricted_items": found_restricted
            }
        
        return {"suitable": True, "reason": "Items are suitable for Man & Van"}
    
    def extract_and_validate_data(self, message: str) -> Dict[str, Any]:
        """Extract customer data and check suitability"""
        data = {}
        missing = []
        message_lower = message.lower()
        
        # Extract postcode
        postcode_patterns = [
            r'([A-Z]{1,2}\d{1,4}[A-Z]?\d?[A-Z]{0,2})',
            r'postcode\s*:?\s*([A-Z0-9\s]+)',
        ]
        
        postcode_found = False
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean_match = match.strip().replace(' ', '')
                if len(clean_match) >= 4 and any(c.isdigit() for c in clean_match) and any(c.isalpha() for c in clean_match):
                    data['postcode'] = clean_match
                    postcode_found = True
                    break
            if postcode_found:
                break
        
        if not postcode_found:
            missing.append('postcode')
        
        # Extract items
        common_items = [
            'bags', 'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress',
            'books', 'clothes', 'boxes', 'appliances', 'fridge', 'freezer',
            'brick', 'bricks', 'mortar', 'concrete', 'soil', 'tiles', 'industrial'
        ]
        
        found_items = []
        for item in common_items:
            if item in message_lower:
                found_items.append(item)
        
        if found_items:
            data['items'] = ', '.join(found_items)
            
            # Check if items are suitable
            suitability = self.check_item_suitability(data['items'])
            data['items_suitable'] = suitability['suitable']
            data['decline_reason'] = suitability['reason'] if not suitability['suitable'] else ""
            
            if not suitability['suitable']:
                data['service_declined'] = True
                return data
        else:
            missing.append('items')
        
        # Estimate size for suitable items
        if data.get('items_suitable', False):
            # Simple size estimation
            if 'few' in message_lower or len(found_items) <= 2:
                data['type'] = '4yd'
            elif 'large' in message_lower or len(found_items) >= 5:
                data['type'] = '8yd'
            else:
                data['type'] = '6yd'
        
        data['service'] = 'mav'
        data['missing_info'] = missing
        data['ready_for_pricing'] = (len(missing) == 0 and data.get('items_suitable', False) and not data.get('service_declined', False))
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        agent_input = {
            "input": message,
            "postcode": extracted.get('postcode', 'NOT PROVIDED'),
            "items": extracted.get('items', 'NOT PROVIDED'),
            "type": extracted.get('type', '6yd'),
            "items_suitable": extracted.get('items_suitable', True),
            "ready_for_pricing": extracted.get('ready_for_pricing', False),
            "decline_reason": extracted.get('decline_reason', '')
        }
        
        if context:
            agent_input.update(context)
        agent_input.update(extracted)
        
        response = self.executor.invoke(agent_input)
        return response["output"]
