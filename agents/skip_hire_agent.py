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
        rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        rule_text = rule_text.replace("{", "{{").replace("}", "}}")
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Skip Hire agent. Be FAST and DIRECT.

CRITICAL: NEVER ASK FOR DATA ALREADY PROVIDED IN CONTEXT

RULES:
- If you have postcode + waste type: IMMEDIATELY call smp_api
- service="skip" ALWAYS  
- Never ask for data already provided
- Get price fast

WORKFLOW:
Has postcode + waste → Call smp_api(action="get_pricing", postcode=X, service="skip", type="8yd")
Missing postcode → "I need your postcode for pricing"
Missing waste type → "What type of waste do you have?"

Be direct. Get price. No chat. NEVER GIVE FAKE PRICES!

Follow team rules:
""" + rule_text + """

CRITICAL: Call smp_api with service="skip" when you have postcode + waste."""),
            ("human", """Customer: {input}

CONTEXT DATA (DON'T ASK FOR THIS AGAIN):
Postcode: {postcode}
Waste: {waste_type}
Size: {size}
Name: {name}
Phone: {phone}

Don't ask for data you already have!"""),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=2)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        # Get data from context first, then message
        extracted = context.get('extracted_info', {}) if context else {}
        
        postcode = (context.get('postcode') if context else None) or extracted.get('postcode') or self._get_postcode(message) or "NOT PROVIDED"
        waste_type = (context.get('waste_type') if context else None) or extracted.get('waste_type') or self._get_waste_type(message) or "NOT PROVIDED"
        size = (context.get('size') if context else None) or extracted.get('size') or self._get_size(message) or "8yd"
        name = (context.get('name') if context else None) or extracted.get('name') or "NOT PROVIDED"
        phone = (context.get('phone') if context else None) or extracted.get('phone') or "NOT PROVIDED"
        
        print(f"🔧 SKIP HIRE AGENT:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   🗑️ Waste: {waste_type}")
        print(f"   📦 Size: {size}")
        
        # Check if ready for API call
        if postcode != "NOT PROVIDED" and waste_type != "NOT PROVIDED":
            print(f"🔧 READY FOR API - calling immediately")
            
            agent_input = {
                "input": message,
                "postcode": postcode.replace(' ', ''),
                "waste_type": waste_type,
                "size": size,
                "name": name,
                "phone": phone
            }
            
            response = self.executor.invoke(agent_input)
            return response["output"]
        
        # Missing data - ask directly
        if postcode == "NOT PROVIDED":
            return "I need your postcode to get skip hire pricing. What's your postcode?"
        
        if waste_type == "NOT PROVIDED":
            return "What type of waste do you have? (construction, garden, household, etc.)"
        
        return "Let me get you a skip hire quote."
    
    def _get_postcode(self, message: str) -> str:
        patterns = [r'([A-Z]{1,2}\d{1,4}[A-Z]?\d?[A-Z]{0,2})']
        for pattern in patterns:
            match = re.search(pattern, message.upper())
            if match:
                return match.group(1).replace(' ', '')
        return ""
    
    def _get_waste_type(self, message: str) -> str:
        waste_types = ['construction', 'building', 'garden', 'household', 'mixed', 'bricks', 'concrete', 'soil', 'rubble', 'mortar']
        found = [waste for waste in waste_types if waste in message.lower()]
        return ', '.join(found) if found else ""
    
    def _get_size(self, message: str) -> str:
        pattern = r'(\d+)\s*(?:yard|yd)'
        match = re.search(pattern, message.lower())
        return f"{match.group(1)}yd" if match else "8yd"
