import json
import re
import uuid
import os
import PyPDF2
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

# PDF RULES CACHE
_PDF_RULES_CACHE = None
# AGENT STATE STORAGE
_AGENT_STATES = {}

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.pdf_rules = self._load_pdf_rules_with_cache()
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Skip Hire agent. Follow 9-step sequence:
1. name 2. postcode 3. product 4. waste type 5. quantity 6. product specific 7. price 8. date 9. booking

Ask questions in sequence. Save state. Use tools for pricing and booking.
If customer needs different service, transfer back to orchestrator with: TRANSFER_TO_ORCHESTRATOR:{collected_data}"""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
    
    def _load_pdf_rules_with_cache(self) -> str:
        """Load PDF rules once, cache for future calls"""
        global _PDF_RULES_CACHE
        
        if _PDF_RULES_CACHE is not None:
            return _PDF_RULES_CACHE
        
        try:
            pdf_path = os.path.join('data', 'rules', 'all rules.pdf')
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
                    
                _PDF_RULES_CACHE = text
                return text
            else:
                _PDF_RULES_CACHE = "PDF rules not found"
                return _PDF_RULES_CACHE
        except Exception as e:
            _PDF_RULES_CACHE = f"Error loading PDF: {str(e)}"
            return _PDF_RULES_CACHE
    
    def _load_state(self, conversation_id: str) -> Dict[str, Any]:
        """Load previous conversation state"""
        global _AGENT_STATES
        return _AGENT_STATES.get(conversation_id, {})
    
    def _save_state(self, conversation_id: str, data: Dict[str, Any]):
        """Save current extracted data"""
        global _AGENT_STATES
        _AGENT_STATES[conversation_id] = data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        conversation_id = context.get('conversation_id') if context else 'default'
        
        # Load previous state
        previous_state = self._load_state(conversation_id)
        
        # Extract new data and merge with previous state
        extracted_data = self._extract_data(message, context)
        combined_data = {**previous_state, **extracted_data}
        
        # Check if transfer needed using PDF rules
        transfer_check = self._check_transfer_needed_with_rules(message, combined_data)
        if transfer_check:
            self._save_state(conversation_id, combined_data)
            return f"TRANSFER_TO_ORCHESTRATOR:{json.dumps(combined_data)}"
        
        current_step = self._determine_step(combined_data)
        response = ""
        
        if current_step == 'name' and not combined_data.get('firstName'):
            response = "What's your name?"
        elif current_step == 'postcode' and not combined_data.get('postcode'):
            response = "What's your postcode?"
        elif current_step == 'product' and not combined_data.get('product'):
            response = "What size skip do you need?"
        elif current_step == 'waste_type' and not combined_data.get('waste_type'):
            response = "What type of waste?"
        elif current_step == 'quantity' and not combined_data.get('quantity'):
            response = "How much waste do you have?"
        elif current_step == 'product_specific' and not combined_data.get('product_specific'):
            response = "Any specific requirements?"
        elif current_step == 'price':
            combined_data['has_pricing'] = True
            response = self._get_pricing(combined_data)
        elif current_step == 'date' and not combined_data.get('preferred_date'):
            response = "When would you like delivery?"
        elif current_step == 'booking':
            response = self._create_booking(combined_data)
        else:
            response = "What's your name?"
        
        # Save updated state
        self._save_state(conversation_id, combined_data)
        return response
    
    def _check_transfer_needed_with_rules(self, message: str, data: Dict[str, Any]) -> bool:
        """Check transfer using PDF rules"""
        message_lower = message.lower()
        rules_lower = self.pdf_rules.lower()
        
        # Check if message contains items that should go to other services based on PDF rules
        if any(word in message_lower for word in ['grab', 'grab hire']):
            return True
        if any(word in message_lower for word in ['man and van', 'mav', 'furniture']):
            return True
            
        # Use PDF rules to determine if transfer needed
        # This is where the PDF content would be analyzed
        return False
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        data = context.copy() if context else {}
        
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})', message.upper().replace(' ', ''))
        if postcode_match:
            data['postcode'] = postcode_match.group(1)
        
        name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
        if name_match:
            data['firstName'] = name_match.group(1).strip().title()
        
        phone_match = re.search(r'\b(07\d{9}|\d{11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            
        # Extract other fields based on current message
        if any(word in message.lower() for word in ['4yd', '6yd', '8yd', '12yd']):
            for size in ['4yd', '6yd', '8yd', '12yd']:
                if size in message.lower():
                    data['product'] = size
                    break
        
        # Extract waste type, quantity, etc. from message
        if not data.get('waste_type') and any(word in message.lower() for word in ['waste', 'rubbish', 'materials']):
            data['waste_type'] = message.strip()
            
        if not data.get('quantity') and any(word in message.lower() for word in ['full', 'half', 'bags', 'tonnes']):
            data['quantity'] = message.strip()
            
        if not data.get('preferred_date') and any(word in message.lower() for word in ['tomorrow', 'today', 'monday', 'tuesday', 'week']):
            data['preferred_date'] = message.strip()
            
        return data
    
    def _determine_step(self, data: Dict[str, Any]) -> str:
        if not data.get('firstName'): return 'name'
        if not data.get('postcode'): return 'postcode'  
        if not data.get('product'): return 'product'
        if not data.get('waste_type'): return 'waste_type'
        if not data.get('quantity'): return 'quantity'
        if not data.get('product_specific'): return 'product_specific'
        if not data.get('has_pricing'): return 'price'
        if not data.get('preferred_date'): return 'date'
        return 'booking'
    
    def _get_pricing(self, data: Dict[str, Any]) -> str:
        try:
            agent_input = {
                "input": f"Get pricing for skip at {data.get('postcode')}",
                "postcode": data.get('postcode'),
                "service": "skip",
                "type": data.get('product', '8yd')
            }
            response = self.executor.invoke(agent_input)
            return response["output"]
        except Exception as e:
            return f"Error getting pricing: {str(e)}"
    
    def _create_booking(self, data: Dict[str, Any]) -> str:
        try:
            booking_ref = str(uuid.uuid4())[:8]
            agent_input = {
                "input": f"Create booking for {data.get('firstName')}",
                "postcode": data.get('postcode'),
                "service": "skip", 
                "type": data.get('product', '8yd'),
                "firstName": data.get('firstName'),
                "phone": data.get('phone'),
                "booking_ref": booking_ref
            }
            response = self.executor.invoke(agent_input)
            return response["output"]
        except Exception as e:
            return f"Error creating booking: {str(e)}"
