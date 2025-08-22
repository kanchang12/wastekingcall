# skip_hire_agent.py - REPLACEMENT FILE
# CHANGES: Minimal changes, enhanced data extraction, better context handling

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
1. Has postcode + waste → Call smp_api(action="get_pricing", postcode=X, service="skip", type="8yd")
2. Customer wants to book → Call smp_api(action="create_booking_quote")
3. Missing postcode → "I need your postcode for pricing"
4. Missing waste type → "What type of waste do you have?"

SKIP SIZES: 4yd, 6yd, 8yd, 12yd (default 8yd)

Be direct. Get price. No chat."""),
            ("human", "Customer: {input}\n\nData: {extracted_info}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=8)
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """CHANGE: Enhanced processing with better context handling"""
        
        # Extract data with context
        extracted_data = self._extract_data(message, context)
        
        print(f"🔧 SKIP DATA: {json.dumps(extracted_data, indent=2)}")
        
        # Check if ready for API call
        postcode = extracted_data.get('postcode')
        waste_type = extracted_data.get('waste_type')
        
        if postcode and waste_type:
            print(f"🔧 READY FOR API - calling immediately")
            
            extracted_info = f"""
Postcode: {postcode}
Waste Type: {waste_type}
Service: skip
Type: {extracted_data.get('size', '8yd')}
Customer Name: {extracted_data.get('firstName', 'NOT PROVIDED')}
Customer Phone: {extracted_data.get('phone', 'NOT PROVIDED')}
Ready for API: True
"""
            
            agent_input = {
                "input": message,
                "extracted_info": extracted_info,
                **extracted_data
            }
            
            response = self.executor.invoke(agent_input)
            return response["output"]
        
        # Missing data - ask directly
        if not postcode:
            return "I need your postcode to get skip hire pricing. What's your postcode?"
        
        if not waste_type:
            return "What type of waste do you have? (construction, garden, household, etc.)"
        
        return "Let me get you a skip hire quote."
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """CHANGE: Enhanced data extraction with context handling"""
        data = {}
        
        # Check context first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress', 'waste_type']:
                if context.get(key):
                    data[key] = context[key]
        
        # Extract postcode
        postcode = self._get_postcode(message, context)
        if postcode:
            data['postcode'] = postcode
        
        # Extract waste type
        waste_type = self._get_waste_type(message, context)
        if waste_type:
            data['waste_type'] = waste_type
        
        # Extract skip size
        size = self._get_size(message, context)
        data['size'] = size
        
        # Extract customer info
        name_match = re.search(r'(?:name is|i\'m|call me)\s+(\w+)', message, re.IGNORECASE)
        if name_match:
            data['firstName'] = name_match.group(1).title()
        
        phone_match = re.search(r'\b(\d{11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
        
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
        if email_match:
            data['emailAddress'] = email_match.group()
        
        data['service'] = 'skip'
        data['type'] = size  # Use size as type for API
        
        return data
    
    def _get_postcode(self, message: str, context: Dict) -> str:
        """Extract postcode with context priority"""
        # Check context first
        if context and context.get('postcode'):
            return context['postcode']
        
        # Extract from message
        patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b',
            r'postcode\s*:?\s*([A-Z0-9\s]+)'
        ]
        for pattern in patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean = match.strip().replace(' ', '')
                if len(clean) >= 4 and any(c.isdigit() for c in clean) and any(c.isalpha() for c in clean):
                    return clean
        
        return None
    
    def _get_waste_type(self, message: str, context: Dict) -> str:
        """Extract waste type with context priority"""
        # Check context first
        if context and context.get('waste_type'):
            return context['waste_type']
        
        # Extract from message
        waste_types = [
            'construction', 'building', 'garden', 'household', 'mixed', 
            'bricks', 'concrete', 'soil', 'rubble', 'mortar', 'wood',
            'metal', 'plastic', 'cardboard', 'general', 'office',
            'demolition', 'renovation', 'clearance'
        ]
        found = []
        message_lower = message.lower()
        for waste in waste_types:
            if waste in message_lower:
                found.append(waste)
        
        return ', '.join(found) if found else None
    
    def _get_size(self, message: str, context: Dict) -> str:
        """Extract skip size with context priority"""
        # Check context first
        if context and context.get('size'):
            return context['size']
        
        # Extract from message
        size_patterns = [r'(\d+)\s*(?:yard|yd)', r'(\d+)yd']
        for pattern in size_patterns:
            match = re.search(pattern, message.lower())
            if match:
                return f"{match.group(1)}yd"
        
        return "8yd"  # Default size
