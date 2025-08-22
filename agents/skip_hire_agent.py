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
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Skip Hire agent. Be FAST and DIRECT.

RULES:
- If you have postcode + waste type: IMMEDIATELY call smp_api
- service="skip" ALWAYS  
- Never ask for data already provided
- Get price fast

WORKFLOW:
Has postcode + waste → Call smp_api(action="get_pricing", postcode=X, service="skip", type="8yd")
Missing postcode → "I need your postcode for pricing"
Missing waste type → "What type of waste do you have?"

Be direct. Get price. No chat."""),
            ("human", "Customer: {input}\n\nI have:\nPostcode: {postcode}\nWaste: {waste_type}\nSize: {size}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=2)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        # Get data from message and context
        postcode = self._get_postcode(message, context)
        waste_type = self._get_waste_type(message, context)
        size = self._get_size(message, context)
        
        print(f"🔧 SKIP DATA: postcode={postcode}, waste={waste_type}, size={size}")
        
        # Check if ready for API call
        if postcode and postcode != "NOT PROVIDED" and waste_type and waste_type != "NOT PROVIDED":
            print(f"🔧 READY FOR API - calling immediately")
            
            agent_input = {
                "input": message,
                "postcode": postcode.replace(' ', ''),  # Remove spaces for API
                "waste_type": waste_type,
                "size": size,
                "action": "get_pricing",
                "service": "skip"
            }
            
            response = self.executor.invoke(agent_input)
            return response["output"]
        
        # Missing data - ask directly
        if not postcode or postcode == "NOT PROVIDED":
            return "I need your postcode to get skip hire pricing. What's your postcode?"
        
        if not waste_type or waste_type == "NOT PROVIDED":
            return "What type of waste do you have? (construction, garden, household, etc.)"
        
        return "Let me get you a skip hire quote."
    
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
    
    def _get_waste_type(self, message: str, context: Dict) -> str:
        # Check context first
        if context and context.get('waste_type'):
            return context['waste_type']
        
        # Extract from message
        waste_types = ['construction', 'building', 'garden', 'household', 'mixed', 'bricks', 'concrete', 'soil', 'rubble', 'mortar']
        found = []
        message_lower = message.lower()
        for waste in waste_types:
            if waste in message_lower:
                found.append(waste)
        
        return ', '.join(found) if found else "NOT PROVIDED"
    
    def _get_size(self, message: str, context: Dict) -> str:
        # Check context first
        if context and context.get('size'):
            return context['size']
        
        # Extract from message
        size_patterns = [r'(\d+)\s*(?:yard|yd)', r'(\d+)yd']
        for pattern in size_patterns:
            match = re.search(pattern, message.lower())
            if match:
                return f"{match.group(1)}yd"
        
        return "8yd"  # Default
