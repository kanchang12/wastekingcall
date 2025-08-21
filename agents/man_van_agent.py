import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        # Remove deprecated memory - use simple conversation tracking instead
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Man & Van specialist agent - friendly, chatty, and very British!

TONE & PERSONALITY:
- Be warm, jovial, and lively - British people love a good chat!
- Use greetings like "Hello there! How are you today?" 
- Be polite, cheerful, have a laugh with customers
- Say things like "Brilliant!", "Lovely!", "Right then!", "Perfect!", "Smashing!"
- Keep it friendly and conversational, not robotic

BUSINESS RULES:
- Man & Van service includes collection and disposal
- We do all the loading for customers
- Pricing based on volume and item types
- Heavy items (dumbbells, kettlebells) may have surcharges
- Access charges apply for upper floors
- Upholstered furniture requires special disposal (EA regulations)

PARAMETER EXTRACTION - CRITICAL:
When calling smp_api for pricing, extract and pass these parameters:
- action: "get_pricing"
- postcode: Extract from "postcode LS14ED" format
- service: Use "mav" for mav service  
- type_: Use "8yrd" format based on volume estimate

Example: smp_api(action="get_pricing", postcode="LS14ED", service="man_and_van", type_="8yard")

Always be cheerful and helpful - make customers feel welcome and valued!
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
        
        # Extract postcode - only valid UK postcodes
        postcode_patterns = [
            r'postcode\s+([A-Z0-9]+)',
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b'
        ]
        
        for pattern in postcode_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                pc = match.group(1).upper().replace(' ', '')
                # Reject invalid postcodes like "LS14EKODELTA"
                if len(pc) <= 8 and not any(word in pc for word in ['DELTA', 'ECO', 'KO']):
                    data['postcode'] = pc
                    print(f"🔍 Extracted postcode: {pc}")
                    break
        
        # Extract items (for info only, not used in SMP API)
        items = []
        item_keywords = ['books', 'clothes', 'dumbbells', 'kettlebell', 'furniture', 'sofa']
        for item in item_keywords:
            if item in message.lower():
                items.append(item)
        if items:
            data['items_info'] = ', '.join(items)
        
        # Extract volume and convert to type_ format
        volume_match = re.search(r'(\w+)\s+cubic\s+yards?', message, re.IGNORECASE)
        if volume_match:
            volume_word = volume_match.group(1).lower()
            volume_map = {'one': '4yard', 'two': '6yard', 'three': '8yard', 'four': '12yard'}
            data['type_'] = volume_map.get(volume_word, '8yard')
        else:
            data['type_'] = '8yard'  # Default
        
        # Set service for SMP API
        data['service'] = 'man_and_van'
        
        # Extract name
        name_match = re.search(r'name\s+(\w+)', message, re.IGNORECASE)
        if name_match:
            data['name'] = name_match.group(1)
            
        # Extract contact
        contact_match = re.search(r'contact\s+(\d+)', message, re.IGNORECASE)
        if contact_match:
            data['contact'] = contact_match.group(1)
        
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
        
        # Add extracted data to agent input so tools can access it
        for k, v in extracted.items():
            agent_input[k] = v

        response = self.executor.invoke(agent_input)
        return response["output"]
