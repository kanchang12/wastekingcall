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
        
        # Load rules from PDF
        try:
            self.rules_processor = RulesProcessor()
            skip_rules = self.rules_processor.get_rules_for_agent("skip_hire")
            rule_text = json.dumps(skip_rules, indent=2)
            rule_text = rule_text.replace("{", "{{").replace("}", "}}")
        except Exception as e:
            rule_text = "Skip hire rules loaded."
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a Skip Hire pricing agent. 

RULES: {rule_text}

CRITICAL INSTRUCTIONS:
1. If Ready for Pricing = True: IMMEDIATELY call smp_api with extracted data
2. If Ready for Pricing = False: Ask for missing postcode or waste type
3. NO phone number needed for pricing
4. Just get the price and give it to customer

SIMPLE WORKFLOW:
Ready for Pricing = True → Call smp_api(action="get_pricing", postcode=X, service="skip", type=Y)
Ready for Pricing = False → Ask what's missing

Be direct and helpful."""),
            ("human", "Customer: {input}\n\nExtracted info:\nPostcode: {postcode}\nWaste Type: {waste_type}\nSize: {type}\nReady for Pricing: {ready_for_pricing}\nMissing: {missing_info}"),
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
    
    def extract_and_validate_data(self, message: str) -> Dict[str, Any]:
        """Extract customer data - SIMPLE VERSION"""
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
        
        # Extract waste type
        waste_types = ['construction', 'building', 'renovation', 'garden', 'household', 'mixed', 'bricks', 'concrete', 'soil', 'rubble']
        found_waste = []
        for waste_type in waste_types:
            if waste_type in message_lower:
                found_waste.append(waste_type)
        
        if found_waste:
            data['waste_type'] = ', '.join(found_waste)
        else:
            missing.append('waste_type')
        
        # Extract skip size
        size_patterns = [r'(\d+)\s*(?:yard|yd)', r'(\d+)yd']
        size_found = False
        for pattern in size_patterns:
            match = re.search(pattern, message_lower)
            if match:
                data['type'] = f"{match.group(1)}yd"
                size_found = True
                break
        
        if not size_found:
            data['type'] = '8yd'  # default
        
        data['service'] = 'skip'
        data['missing_info'] = missing
        data['ready_for_pricing'] = len(missing) == 0
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        agent_input = {
            "input": message,
            "postcode": extracted.get('postcode', 'NOT PROVIDED'),
            "waste_type": extracted.get('waste_type', 'NOT PROVIDED'),
            "type": extracted.get('type', '8yd'),
            "ready_for_pricing": extracted.get('ready_for_pricing', False),
            "missing_info": extracted.get('missing_info', [])
        }
        
        if context:
            agent_input.update(context)
        agent_input.update(extracted)
        
        response = self.executor.invoke(agent_input)
        return response["output"]
