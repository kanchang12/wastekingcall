import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.rules_processor = RulesProcessor()
        rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        rule_text = rule_text.replace("{", "{{").replace("}", "}}")

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Grab Hire specialist - friendly, British, and GET PRICING NOW!

CRITICAL: NEVER ASK FOR DATA ALREADY PROVIDED IN CONTEXT

IMMEDIATE ACTION:
- If you have postcode + material type: CALL smp_api IMMEDIATELY
- Use service="grab" ALWAYS

PERSONALITY:
- Start with: "Alright love!" or "Right then!"
- Get pricing first

WORKFLOW:
1. Check context for postcode, material type 
2. CALL smp_api with service="grab" immediately if you have data
3. Give price
4. ONLY ask for missing data if not in context

MATERIAL RULES:
- Heavy materials (soil, muck, rubble) = grab lorry ideal
- Light materials = suggest skip or MAV instead

Follow team rules:
""" + rule_text + """

NEVER GIVE FAKE PRICES - only API prices!"""),
            ("human", """Customer: {input}

CONTEXT DATA (DON'T ASK FOR THIS AGAIN):
Postcode: {postcode}
Material type: {material_type}
Name: {name}
Phone: {phone}

INSTRUCTION: Use context data. Call smp_api if you have postcode + material. Don't repeat questions!"""),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=5)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        # Get data from context first, then message
        extracted = context.get('extracted_info', {}) if context else {}
        
        postcode = (context.get('postcode') if context else None) or extracted.get('postcode') or self._extract_postcode(message) or 'NOT PROVIDED'
        material_type = (context.get('waste_type') if context else None) or extracted.get('waste_type') or self._extract_material(message) or 'NOT PROVIDED'
        name = (context.get('name') if context else None) or extracted.get('name') or self._extract_name(message) or 'NOT PROVIDED'
        phone = (context.get('phone') if context else None) or extracted.get('phone') or self._extract_phone(message) or 'NOT PROVIDED'
        
        print(f"🔧 GRAB HIRE AGENT:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   🗑️ Material: {material_type}")
        print(f"   👤 Name: {name}")
        print(f"   📞 Phone: {phone}")
        
        agent_input = {
            "input": message,
            "postcode": postcode,
            "material_type": material_type,
            "name": name,
            "phone": phone
        }
        
        if context:
            agent_input.update(context)
        
        response = self.executor.invoke(agent_input)
        return response["output"]
    
    def _extract_postcode(self, message: str) -> str:
        patterns = [r'([A-Z]{1,2}\d{1,4}[A-Z]?\d?[A-Z]{0,2})']
        for pattern in patterns:
            match = re.search(pattern, message.upper())
            if match:
                return match.group(1).replace(' ', '')
        return ""
    
    def _extract_material(self, message: str) -> str:
        materials = ['soil', 'muck', 'rubble', 'concrete', 'brick', 'sand', 'gravel', 'furniture', 'household', 'general']
        found = [mat for mat in materials if mat in message.lower()]
        return ', '.join(found) if found else ""
    
    def _extract_name(self, message: str) -> str:
        patterns = [r'\bname\s+is\s+([A-Z][a-z]+)\b', r'\bi\s+am\s+([A-Z][a-z]+)\b']
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)
        return ""
    
    def _extract_phone(self, message: str) -> str:
        pattern = r'\b(07\d{9})\b'
        match = re.search(pattern, message)
        return match.group(1) if match else ""
