import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Grab Hire specialist - friendly, British, and RULE-FOLLOWING!

PERSONALITY - CRITICAL:
- Start with: "Alright love!" or "Hello there!" or "Right then!" 
- Use British phrases: "Brilliant!", "Lovely!", "Smashing!", "Perfect!"
- Be chatty: "How's your day going?", "Lovely to hear from you!"
- Sound human and warm, not robotic

BUSINESS RULES - FOLLOW EXACTLY:
1. ALWAYS collect NAME, POSTCODE, MATERIAL TYPE before pricing
2. Grab lorries ideal for: soil, muck, rubble, hardcore, sand, gravel
3. Minimum 8-tonne loads, maximum 16-tonne
4. Road access required for grab lorry
5. Same day service available

QUALIFICATION PROCESS:
1. If missing NAME: "Hello! I'm here to help with grab hire. What's your name?"
2. If missing POSTCODE: "Lovely! And what's your postcode for collection?"
3. If missing MATERIAL: "Perfect! What material do you need collected?"
4. Only AFTER getting all 3, call smp_api with: action="get_pricing", postcode="{postcode}", service="grab", type="8yd"

MATERIAL RULES:
- Heavy materials (soil, muck, rubble, hardcore) → grab lorry ideal
- Light materials (household waste) → suggest skip or MAV instead
- Mixed loads → check access and tonnage

WORKFLOW:
1. Get pricing with smp_api action="get_pricing"
2. If customer wants to book, call smp_api action="create_booking_quote"  
3. For payment, call smp_api action="take_payment"

RESPONSES:
- Always confirm: "Grab lorry will collect directly from your location"
- Check road access: "Can our grab lorry access your property from the road?"
- Explain tonnage limits clearly
- Give same day availability

NEVER skip qualification questions. NEVER call smp_api without name, postcode, material type.
"""),
            ("human", "Customer: {input}\n\nExtracted data: {extracted_info}"),
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
        """Extract customer data and check what's missing"""
        data = {}
        missing = []
        
        # Extract name
        name_patterns = [
            r'name\s+(?:is\s+)?(\w+)',
            r'i\'?m\s+(\w+)',
            r'my\s+name\s+is\s+(\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['firstName'] = match.group(1).title()
                break
        if 'firstName' not in data:
            missing.append('name')
        
        # Extract postcode
        postcode_patterns = [
            r'postcode\s+(?:is\s+)?([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})',
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b'
        ]
        for pattern in postcode_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                pc = match.group(1).upper()
                if len(pc.replace(' ', '')) >= 5:
                    if ' ' not in pc and len(pc) >= 6:
                        data['postcode'] = pc[:-3] + ' ' + pc[-3:]
                    else:
                        data['postcode'] = pc
                    break
        if 'postcode' not in data:
            missing.append('postcode')
        
        # Extract material type
        material_indicators = {
            'heavy': ['soil', 'muck', 'rubble', 'hardcore', 'sand', 'gravel', 'concrete', 'stone'],
            'light': ['household', 'general', 'office', 'furniture', 'garden'],
            'mixed': ['mixed', 'various', 'different']
        }
        
        found_material = []
        material_category = None
        
        message_lower = message.lower()
        for category, keywords in material_indicators.items():
            for keyword in keywords:
                if keyword in message_lower:
                    found_material.append(keyword)
                    material_category = category
                    break
        
        if found_material:
            data['material_type'] = ', '.join(found_material)
            data['material_category'] = material_category
        else:
            missing.append('material_type')
        
        # Extract tonnage if mentioned
        tonnage_patterns = [
            r'(\d+)\s*(?:ton|tonne)s?',
            r'(eight|8|twelve|12|sixteen|16)\s*(?:ton|tonne)s?'
        ]
        tonnage_map = {
            'eight': '8', '8': '8', 'twelve': '12', '12': '12', 'sixteen': '16', '16': '16'
        }
        
        for pattern in tonnage_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                tonnage_word = match.group(1).lower()
                tonnage_num = tonnage_map.get(tonnage_word, tonnage_word)
                data['tonnage'] = f"{tonnage_num}t"
                break
        
        if 'tonnage' not in data:
            data['tonnage'] = '8t'  # Default
        
        # Set grab hire specific fields
        data['type'] = '8yd'  # Default for grab hire
        data['service'] = 'grab'
        
        # Extract phone
        phone_patterns = [
            r'phone\s+(?:is\s+)?(\d{11})',
            r'mobile\s+(?:is\s+)?(\d{11})',
            r'\b(\d{11})\b'
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                data['phone'] = match.group(1)
                break
        
        # Extract email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, message)
        if email_match:
            data['emailAddress'] = email_match.group()
        
        data['missing_info'] = missing
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        # Create extracted info summary for the prompt
        extracted_info = f"""
Name: {extracted.get('firstName', 'NOT PROVIDED')}
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Material Type: {extracted.get('material_type', 'NOT PROVIDED')}
Material Category: {extracted.get('material_category', 'unknown')}
Tonnage: {extracted.get('tonnage', '8t')}
Phone: {extracted.get('phone', 'NOT PROVIDED')}
Email: {extracted.get('emailAddress', 'NOT PROVIDED')}
Missing Info: {extracted.get('missing_info', [])}
"""
        
        agent_input = {
            "input": message,
            "extracted_info": extracted_info
        }
        
        if context:
            for k, v in context.items():
                agent_input[k] = v
                
        # Add extracted data for tools
        agent_input.update(extracted)

        response = self.executor.invoke(agent_input)
        return response["output"]
