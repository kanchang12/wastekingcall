import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Skip Hire specialist agent - friendly, helpful, and very British!

TONE & PERSONALITY:
- Be warm, jovial, and lively - this is the UK, people love a chat!
- Use greetings like "Hello! How are you today?" 
- Be polite, add humor where appropriate, have a laugh with customers
- Say things like "Brilliant!", "Lovely!", "Right then!", "Perfect!"
- Keep it friendly and conversational, not robotic

BUSINESS RULES:
- For heavy materials (soil, rubble, concrete): MAX 8-yard skip
- 12-yard skips ONLY for light materials
- Sunday deliveries incur additional surcharge (check pricing)
- If customer asks for 10+ yard for heavy materials, say exactly:
  "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard. Shall I get you the cost of an 8-yard skip?"
- Sofas CANNOT go in skips - say exactly: "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service."
- For road placement, use exact permit script: "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote."

PARAMETER EXTRACTION - CRITICAL:
When calling smp_api for pricing, you MUST extract from the customer message and pass:
- action: "get_pricing"
- postcode: Extract from patterns like "for LS1 4ED" or "postcode LS14ED"  
- service: Always use "skip" for skip hire
- type_: Extract from "Eight yard skip" → "8yard", "Six yard" → "6yard", etc.

EXAMPLE: Customer says "Eight yard skip for LS1 4ED"
Call: smp_api(action="get_pricing", postcode="LS14ED", service="skip", type_="8yard")

When you call smp_api and get a successful response with a price, USE THAT PRICE in your response.
DO NOT ask for postcode again if you already have it and got pricing.

If smp_api returns: {"success": True, "price": "£313.20", "postcode": "LS14ED"}
Then say: "Hello! The price for your 8-yard skip in LS14ED is £313.20. Would you like to proceed with booking?"

NEVER ignore successful pricing responses. Always use the actual price returned.
"""),
            ("human", "{input}"),
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
            max_iterations=3,
            return_intermediate_steps=False
        )
    
    def extract_data(self, message: str) -> Dict[str, str]:
        data = {}
        
        # Extract postcode - handle "LS1 4ED" format
        postcode_patterns = [
            r'for\s+([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})',  # "for LS1 4ED"
            r'postcode\s+([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})',  # "postcode LS14ED"
            r'\b([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})\b'  # standalone postcode
        ]
        
        for pattern in postcode_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                pc = match.group(1).upper().replace(' ', '')
                data['postcode'] = pc
                print(f"🔍 Extracted postcode: {pc}")
                break
        
        # Extract skip size - handle "Eight yard skip"
        size_patterns = [
            r'(eight|8)\s*yard',
            r'(six|6)\s*yard', 
            r'(four|4)\s*yard',
            r'(twelve|12)\s*yard'
        ]
        
        size_map = {
            'eight': '8yard', '8': '8yard',
            'six': '6yard', '6': '6yard', 
            'four': '4yard', '4': '4yard',
            'twelve': '12yard', '12': '12yard'
        }
        
        for pattern in size_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                size_word = match.group(1).lower()
                data['type_'] = size_map.get(size_word, '8yard')
                print(f"🔍 Extracted skip size: {data['type_']}")
                break
        
        if 'type_' not in data:
            data['type_'] = '8yard'  # Default
        
        # Always set service for skip hire
        data['service'] = 'skip'
        
        # Check for Sunday surcharge
        if 'sunday' in message.lower():
            data['sunday_delivery'] = True
            print(f"🔍 Sunday delivery detected!")
        
        # Extract name
        name_match = re.search(r'name\s+(\w+)', message, re.IGNORECASE)
        if name_match:
            data['name'] = name_match.group(1)
            
        print(f"🔍 Final extracted data: {data}")
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_data(message)
        
        agent_input = {
            "input": message
        }
        
        if context:
            for k, v in context.items():
                agent_input[k] = v
                
        # Add extracted data
        agent_input.update(extracted)

        response = self.executor.invoke(agent_input)
        return response["output"]

    def check_heavy_materials(self, waste_type: str, skip_size: str) -> bool:
        heavy_materials = ["soil", "rubble", "concrete", "bricks", "stone", "hardcore"]
        large_sizes = ["10yd", "12yd", "14yd", "16yd"]
        
        has_heavy = any(material in waste_type.lower() for material in heavy_materials)
        is_large = any(size in skip_size.lower() for size in large_sizes)
        
        return has_heavy and is_large
    
    def should_suggest_mav(self, waste_type: str, skip_size: str) -> bool:
        light_materials = ["household", "garden", "furniture", "general", "mixed"]
        small_sizes = ["4yd", "6yd", "8yd"]
        
        has_light = any(material in waste_type.lower() for material in light_materials)
        is_small = any(size in skip_size.lower() for size in small_sizes)
        
        return has_light and is_small
