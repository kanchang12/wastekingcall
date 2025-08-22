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
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Man & Van agent with STRICT RULES.

HEAVY ITEMS RULE:
Man & Van CANNOT handle: bricks, mortar, concrete, soil, tiles, construction waste, industrial waste

If heavy items detected: "Sorry mate, bricks/concrete/soil are too heavy for Man & Van. You need Skip Hire for that."

WORKFLOW:
Heavy items → DECLINE and suggest Skip Hire
Light items + postcode → Call smp_api(action="get_pricing", postcode=X, service="mav", type="6yd")
Missing data → Ask once

Be direct. Follow rules strictly."""),
            ("human", "Customer: {input}\n\nI have:\nPostcode: {postcode}\nItems: {items}\nSuitable: {suitable}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=2)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        # Get data from message and context
        postcode = self._get_postcode(message, context)
        items = self._get_items(message, context)
        
        print(f"🔧 MAV DATA: postcode={postcode}, items={items}")
        
        # CHECK HEAVY ITEMS FIRST - ENFORCE RULES
        if items and items != "NOT PROVIDED":
            heavy_items = self._check_heavy_items(items)
            if heavy_items:
                print(f"🔧 HEAVY ITEMS DETECTED: {heavy_items}")
                return f"Sorry mate, {', '.join(heavy_items)} are too heavy for our Man & Van service. You need Skip Hire for that type of waste. Let me connect you with our skip team!"
        
        # Check if ready for API call (suitable items + postcode)
        if postcode and postcode != "NOT PROVIDED" and items and items != "NOT PROVIDED":
            print(f"🔧 READY FOR API - calling immediately")
            
            agent_input = {
                "input": message,
                "postcode": postcode.replace(' ', ''),  # Remove spaces for API
                "items": items,
                "suitable": True,
                "action": "get_pricing",
                "service": "mav",
                "type": "6yd"
            }
            
            response = self.executor.invoke(agent_input)
            return response["output"]
        
        # Missing data - ask directly
        if not postcode or postcode == "NOT PROVIDED":
            return "I need your postcode to get Man & Van pricing. What's your postcode?"
        
        if not items or items == "NOT PROVIDED":
            return "What items do you need collected? (furniture, bags, appliances, etc.)"
        
        return "Let me get you a Man & Van quote."
    
    def _check_heavy_items(self, items: str) -> List[str]:
        """Check for heavy items that Man & Van cannot handle"""
        items_lower = items.lower()
        restricted = ['brick', 'bricks', 'mortar', 'concrete', 'cement', 'soil', 'dirt', 'tile', 'tiles', 'stone', 'stones', 'rubble', 'sand', 'gravel', 'industrial waste', 'construction waste', 'building waste']
        
        found_restricted = []
        for item in restricted:
            if item in items_lower:
                found_restricted.append(item)
        
        return found_restricted
    
    def _get_postcode(self, message: str, context: Dict) -> str:
        # Check context first
        if context and context.get('postcode'):
            return context['postcode']
        
        # Extract from message
        patterns = [r'([A-Z]{1,2}\d{1,4}[A-Z]?\d?[A-Z]{0,2})', r'postcode\s*:?\s*([A-Z0-9\s]+)']
        for pattern in patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean = match.strip().replace(' ', '')
                if len(clean) >= 4 and any(c.isdigit() for c in clean) and any(c.isalpha() for c in clean):
                    return clean
        
        return "NOT PROVIDED"
    
    def _get_items(self, message: str, context: Dict) -> str:
        # Check context first
        if context and context.get('items'):
            return context['items']
        
        # Extract from message
        mav_items = ['bags', 'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 'books', 'clothes', 'boxes', 'appliances', 'fridge', 'freezer', 'brick', 'bricks', 'mortar', 'concrete', 'soil', 'tiles', 'industrial']
        found = []
        message_lower = message.lower()
        for item in mav_items:
            if item in message_lower:
                found.append(item)
        
        return ', '.join(found) if found else "NOT PROVIDED"
