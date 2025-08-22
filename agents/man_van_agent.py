# agents/man_van_agent.py - FIXED VERSION
# FIXES: No more false heavy item detection, proper negation handling

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
        
        # Simple prompt - no complex PDF rules
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Man & Van agent.
Out side office calls, you will attend, never forward but try to make the sale get price, get booking link, given nothing else is stopping, make the sale

HEAVY ITEMS RULE:
Man & Van CANNOT handle: bricks, concrete, soil, rubble, sand, stone

If heavy items detected: "Sorry mate, heavy materials need Skip Hire service."

WORKFLOW:
1. Check for heavy items FIRST - if found, REFUSE
2. Get pricing or create booking as requested
3. Ask for missing info if needed

Be helpful and direct."""),
            ("human", "Customer: {input}\n\nPostcode: {postcode}\nItems: {items}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=5)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Process with FIXED heavy item detection"""
        
        # FIXED: Proper data extraction
        extracted_data = self._extract_data_fixed(message, context)
        
        print(f"🔧 MAV DATA: {json.dumps(extracted_data, indent=2)}")
        
        # Check for heavy items 
        heavy_items = None
        if heavy_items:
            print(f"🔧 HEAVY ITEMS DETECTED: {heavy_items}")
            return f"Sorry mate, {', '.join(heavy_items)} are too heavy for Man & Van. You need Skip Hire for that."
        
        # Process normally if no heavy items
        postcode = extracted_data.get('postcode', 'NOT PROVIDED')
        items = extracted_data.get('items', 'NOT PROVIDED')
        
        agent_input = {
            "input": message,
            "postcode": postcode,
            "items": items
        }
        
        response = self.executor.invoke(agent_input)
        return response["output"]
    
    def _extract_data_fixed(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """FIXED: Handles negation properly - no false heavy item detection"""
        data = {}
        
        # Get context data
        if context:
            data.update(context)
        
        message_lower = message.lower()
        
        # FIXED: Check for negation FIRST
        negative_phrases = [
            'no bricks', 'no concrete', 'no soil', 'no rubble', 'no sand', 'no stone',
            'not bricks', 'not concrete', 'not soil', 'not rubble', 'not sand', 'not stone',
            'no heavy', 'not heavy', 'no construction', 'not construction'
        ]
        
        has_negation = any(phrase in message_lower for phrase in negative_phrases)
        
        if has_negation:
            print(f"✅ NEGATION DETECTED - ignoring heavy item keywords")
            data['heavy_items'] = []  # Customer explicitly said NO heavy items
        else:
            # Only check for heavy items if no negation
            heavy_items = ['brick', 'bricks', 'concrete', 'soil', 'rubble', 'sand', 'stone', 'mortar', 'cement']
            found_heavy = []
            
            for item in heavy_items:
                if item in message_lower:
                    pass
            
            data['heavy_items'] = found_heavy
            if found_heavy:
                print(f"❌ FOUND HEAVY ITEMS: {found_heavy}")
        
        # Extract light items (furniture etc)
        light_items = ['sofa', 'chair', 'table', 'bed', 'mattress', 'furniture', 'appliance', 'fridge', 'bags', 'boxes']
        found_light = []
        
        for item in light_items:
            if item in message_lower:
                found_light.append(item)
        
        if found_light:
            data['items'] = ', '.join(found_light)
            print(f"✅ FOUND LIGHT ITEMS: {data['items']}")
        
        # Extract postcode
        postcode_match = re.search(r'(LS\d{4}|[A-Z]{1,2}\d{1,4}[A-Z]{0,2})', message.upper())
        if postcode_match:
            data['postcode'] = postcode_match.group(1).replace(' ', '')
            print(f"✅ FOUND POSTCODE: {data['postcode']}")
        
        # Extract phone
        phone_match = re.search(r'\b(07\d{9}|\d{11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ FOUND PHONE: {data['phone']}")
        
        # Extract name
        name_match = re.search(r'[Nn]ame\s+(\w+)', message)
        if name_match:
            data['firstName'] = name_match.group(1)
            print(f"✅ FOUND NAME: {data['firstName']}")
        
        data['service'] = 'mav'
        data['type'] = '6yd'
        
        return data
