import json 
import re
import os
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
import PyPDF2

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        # Direct PDF import from data/rules/all rules.pdf
        pdf_rules = self._load_pdf_rules()
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a Man & Van agent with STRICT RULES.

RULES FROM PDF KNOWLEDGE BASE:
{pdf_rules}

HEAVY ITEMS RULE:
Man & Van CANNOT handle: bricks, mortar, concrete, soil, tiles, construction waste, industrial waste

YOU DECIDE: Based on customer's items, determine if they're suitable for Man & Van or too heavy.
If heavy items: "Sorry mate, [items] are too heavy for Man & Van. You need Skip Hire for that."

CRITICAL: NEVER ASK FOR DATA ALREADY PROVIDED IN CONTEXT

WORKFLOW:
Heavy items → DECLINE and suggest Skip Hire  
Light items + postcode → Call smp_api(action="get_pricing", postcode=X, service="mav", type="6yd")
Missing data → Ask once

Be direct. YOU decide based on rules. NEVER GIVE FAKE PRICES!

CRITICAL: Call smp_api with service="mav" when you have postcode + suitable items."""),
            ("human", """Customer: {input}

CONTEXT DATA (DON'T ASK FOR THIS AGAIN):
Postcode: {postcode}
Items: {items}
Name: {name}
Phone: {phone}

Don't ask for data you already have!"""),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=2)
    
    def _load_pdf_rules(self) -> str:
        """Load rules directly from data/rules/all rules.pdf"""
        try:
            pdf_path = "data/rules/all rules.pdf"
            print(f"🔧 MAN & VAN AGENT: Loading PDF rules from: {pdf_path}")
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                print(f"🔧 MAN & VAN AGENT: PDF rules loaded successfully ({len(text)} characters)")
                return text
            else:
                print(f"❌ MAN & VAN AGENT: PDF rules not found at {pdf_path}")
                return "PDF rules not found - using basic man & van rules"
        except Exception as e:
            print(f"❌ MAN & VAN AGENT: Error loading PDF rules: {e}")
            return "PDF rules not available - using basic man & van rules"
    
    def process_message(self, message: str, context: Dict = None) -> str:
        # Get data from context first, then message
        extracted = context.get('extracted_info', {}) if context else {}
        
        postcode = (context.get('postcode') if context else None) or extracted.get('postcode') or self._get_postcode(message) or "NOT PROVIDED"
        items = (context.get('waste_type') if context else None) or extracted.get('waste_type') or self._get_items(message) or "NOT PROVIDED"
        name = (context.get('name') if context else None) or extracted.get('name') or "NOT PROVIDED"
        phone = (context.get('phone') if context else None) or extracted.get('phone') or "NOT PROVIDED"
        
        print(f"🔧 MAN & VAN AGENT:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   📦 Items: {items}")
        print(f"🔧 MAN & VAN AGENT: Tools available: {[tool.name for tool in self.tools]}")
        
        # Let AI agent decide about heavy items based on rules, no hardcoded checks
        agent_input = {
            "input": message,
            "postcode": postcode.replace(' ', '') if postcode != "NOT PROVIDED" else postcode,
            "items": items,
            "name": name,
            "phone": phone
        }
        
        print(f"🔧 MAN & VAN AGENT: Executing agent")
        response = self.executor.invoke(agent_input)
        print(f"🔧 MAN & VAN AGENT: Agent execution completed successfully")
        return response["output"]
    
    def _get_postcode(self, message: str) -> str:
        patterns = [r'([A-Z]{1,2}\d{1,4}[A-Z]?\d?[A-Z]{0,2})']
        for pattern in patterns:
            match = re.search(pattern, message.upper())
            if match:
                return match.group(1).replace(' ', '')
        return ""
    
    def _get_items(self, message: str) -> str:
        mav_items = ['bags', 'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 'books', 'clothes', 'boxes', 'appliances', 'fridge', 'freezer', 'brick', 'bricks', 'mortar', 'concrete', 'soil', 'tiles']
        found = [item for item in mav_items if item in message.lower()]
        return ', '.join(found) if found else ""
