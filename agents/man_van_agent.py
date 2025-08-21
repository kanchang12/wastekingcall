import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Man & Van specialist agent.

BUSINESS RULES:
- Man & Van service includes collection and disposal
- We do all the loading for customers
- Pricing based on volume and item types
- Heavy items (dumbbells, kettlebells) may have surcharges
- Access charges apply for upper floors
- Upholstered furniture requires special disposal (EA regulations)

PRICING APPROACH:
- Always extract: postcode, items list, estimated volume, access details
- When you have all required info, call smp_api with action='get_pricing'
- Pass: postcode, waste_type (describing items), service_type='man_van'
- Include volume estimate in waste_type description

CUSTOMER DATA REQUIRED:
- Name and contact details
- Full postcode (not partial like "LS14EcoDelta" - ask for valid UK postcode)
- Complete list of items to be collected
- Estimated volume or quantity
- Access details (floor level, parking, etc.)
- Preferred collection date/time

RESPONSES:
- Always confirm all details before providing pricing
- Explain service includes loading and disposal
- Mention any applicable surcharges upfront
- Provide clear next steps for booking

When calling smp_api for pricing, use the extracted customer data properly:
- postcode: Clean UK postcode (e.g., "LS14ED")
- waste_type: Description of items (e.g., "books, clothes, dumbbells, kettlebells")
- service_type: "man_van"
- skip_size: Use volume estimate (e.g., "3_cubic_yards")
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
            memory=self.memory,
            verbose=True,
            max_iterations=3
        )
    
    def extract_customer_data(self, message: str) -> Dict[str, Any]:
        """Extract customer data from message using regex patterns"""
        data = {}
        
        # Extract postcode - be more specific about UK postcode format
        postcode_patterns = [
            r'postcode\s+([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})',  # Standard UK format
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b',  # Standalone UK postcode
        ]
        
        for pattern in postcode_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                # Validate it looks like a real UK postcode
                potential_postcode = match.group(1).upper().replace(' ', '')
                if len(potential_postcode) >= 5 and len(potential_postcode) <= 8:
                    # Add space in correct position for UK postcodes
                    if len(potential_postcode) == 6:
                        data['postcode'] = potential_postcode[:3] + ' ' + potential_postcode[3:]
                    elif len(potential_postcode) == 7:
                        data['postcode'] = potential_postcode[:4] + ' ' + potential_postcode[4:]
                    else:
                        data['postcode'] = potential_postcode
                break
        
        # Extract name
        name_match = re.search(r'name\s+(\w+)', message, re.IGNORECASE)
        if name_match:
            data['name'] = name_match.group(1)
        
        # Extract contact
        contact_match = re.search(r'contact\s+(\d+)', message, re.IGNORECASE)
        if contact_match:
            data['contact'] = contact_match.group(1)
        
        # Extract items list - look for comma-separated items
        items_patterns = [
            r'books?,\s*clothes?,\s*(?:two\s+)?dumbbells?,\s*(?:one\s+)?kettlebells?',
            r'(?:books?|clothes?|dumbbells?|kettlebells?|furniture|sofa|chair)(?:\s*,\s*(?:books?|clothes?|dumbbells?|kettlebells?|furniture|sofa|chair))*'
        ]
        
        items_found = []
        for pattern in items_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                items_text = match.group(0)
                # Split and clean items
                items = [item.strip() for item in re.split(r',\s*', items_text)]
                items_found.extend(items)
        
        if items_found:
            data['items'] = ', '.join(set(items_found))  # Remove duplicates
        
        # Extract volume
        volume_patterns = [
            r'(?:about\s+)?(\d+)\s+cubic\s+yards?',
            r'(\d+)\s*(?:cubic\s*)?(?:yard|meter)s?'
        ]
        
        for pattern in volume_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['estimated_volume'] = f"{match.group(1)} cubic yards"
                break
        
        # Extract access details
        access_patterns = [
            r'(third\s+floor(?:\s+but\s+will\s+bring\s+to\s+ground)?)',
            r'(ground\s+floor)',
            r'(first\s+floor)',
            r'(second\s+floor)'
        ]
        
        for pattern in access_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['access'] = match.group(1)
                break
        
        # Extract timing
        timing_match = re.search(r'(next\s+week|this\s+week|tomorrow|today)', message, re.IGNORECASE)
        if timing_match:
            data['preferred_time'] = timing_match.group(1)
        
        return data
    
    def validate_required_data(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Check what required data is missing"""
        missing = {}
        
        if not data.get('postcode'):
            missing['postcode'] = "Please provide your full postcode"
        elif not re.match(r'^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$', data['postcode'], re.IGNORECASE):
            missing['postcode'] = "Please provide a valid UK postcode (e.g., LS14 ED)"
        
        if not data.get('items'):
            missing['items'] = "Please tell me what items you need collected"
        
        if not data.get('estimated_volume') and not data.get('items'):
            missing['volume'] = "Please estimate the volume or quantity of items"
        
        return missing
    
    def process_message(self, message: str, context: Dict = None) -> str:
        try:
            # Extract customer data from message
            extracted_data = self.extract_customer_data(message)
            
            # Merge with existing context
            if context:
                extracted_data.update(context)
            
            # Check for missing required data
            missing_data = self.validate_required_data(extracted_data)
            
            if missing_data:
                # Return specific request for missing data
                missing_items = list(missing_data.values())
                return f"I have some of your details. {missing_items[0]}"
            
            # Prepare waste_type description for API
            waste_description = []
            if extracted_data.get('items'):
                waste_description.append(extracted_data['items'])
            if extracted_data.get('estimated_volume'):
                waste_description.append(f"approximately {extracted_data['estimated_volume']}")
            if extracted_data.get('access'):
                waste_description.append(f"access: {extracted_data['access']}")
            
            # Create agent input with all extracted data
            agent_input = {
                "input": message,
                "postcode": extracted_data.get('postcode'),
                "waste_type": ' - '.join(waste_description) if waste_description else 'household items',
                "service_type": "man_van",
                "skip_size": extracted_data.get('estimated_volume', '3_cubic_yards').replace(' ', '_'),
                **extracted_data
            }
            
            print(f"🔧 Man & Van agent input: {agent_input}")
    
            response = self.executor.invoke(agent_input)
            return response["output"]
            
        except Exception as e:
            print(f"Man & Van agent error: {e}")
            return "I can help you with Man & Van collection service. Please provide your postcode and tell me what items you need collected."
