import json 
import re
import os
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
import PyPDF2

class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        # Direct PDF import from data/rules/all_rules.pdf
        pdf_rules = self._load_pdf_rules()

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are the WasteKing Grab Hire specialist - friendly, British, and GET PRICING NOW!

IMPORTANT ROUTING: You handle ALL waste services EXCEPT "mav" (man and van) and "skip" (skip hire).
This includes: grab hire, general waste, large items, heavy materials, construction waste, garden waste, office clearance, etc.

RULES FROM PDF KNOWLEDGE BASE:
{pdf_rules}

CRITICAL API PARAMETERS:
- service: "grab" (for grab hire) or determine appropriate service
- postcode: Clean format (no spaces for API)

MANDATORY WORKFLOW:
1. Extract postcode + material type from message
2. If customer provides name + phone + says "book": CALL create_booking_quote IMMEDIATELY
3. If just pricing info: Call get_pricing then ask to book
4. Booking will automatically call supplier

PERSONALITY:
- Start with: "Alright love!" or "Right then!"
- Get pricing first, then book if customer confirms

Follow PDF rules above. Get pricing fast."""),
            ("human", """Customer: {input}

Extracted data: {extracted_info}

INSTRUCTION: If customer has all info and says "book", call create_booking_quote immediately."""),
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
            max_iterations=10
        )
    
    def _load_pdf_rules(self) -> str:
        """Load rules directly from data/rules/all_rules.pdf"""
        try:
            pdf_path = "data/rules/all_rules.pdf"
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                return text
            else:
                return "PDF rules not found - using basic grab hire rules"
        except Exception as e:
            print(f"Error loading PDF rules: {e}")
            return "PDF rules not available - using basic grab hire rules"
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Process with proper data extraction"""
        
        extracted_data = self._extract_data_properly(message, context)
        
        print(f"🔧 GRAB DATA: {json.dumps(extracted_data, indent=2)}")
        
        postcode = extracted_data.get('postcode')
        materials = extracted_data.get('material_type')
        has_name = bool(extracted_data.get('firstName'))
        has_phone = bool(extracted_data.get('phone'))
        
        wants_booking = 'book' in message.lower()
        has_all_info = postcode and materials and has_name and has_phone
        
        print(f"🎯 DECISION:")
        print(f"   - Wants booking: {wants_booking}")
        print(f"   - Has all info: {has_all_info}")
        print(f"   - Name: {extracted_data.get('firstName')}")
        print(f"   - Phone: {extracted_data.get('phone')}")
        
        if wants_booking and has_all_info:
            action = "create_booking_quote"
            print(f"🔧 CREATING BOOKING IMMEDIATELY")
        elif postcode and materials:
            action = "get_pricing"
            print(f"🔧 GETTING PRICING FIRST")
        else:
            if not postcode:
                return "Right then! What's your postcode?"
            if not materials:
                return "What materials need collecting?"
            return "Let me get you a grab hire quote."
        
        extracted_info = f"""
Postcode: {postcode}
Material Type: {materials}
Service: grab
Customer Name: {extracted_data.get('firstName', 'NOT PROVIDED')}
Customer Phone: {extracted_data.get('phone', 'NOT PROVIDED')}
Action: {action}
Ready for API: True
"""
        
        if action == "create_booking_quote":
            import uuid
            extracted_data['booking_ref'] = str(uuid.uuid4())
        
        agent_input = {
            "input": message,
            "extracted_info": extracted_info,
            "action": action
        }
        
        agent_input.update(extracted_data)
        
        try:
            response = self.executor.invoke(agent_input)
            return response["output"]
        except Exception as e:
            print(f"❌ Grab Agent Error: {str(e)}")
            return "Right then! I need your postcode and what type of materials you have. What's your postcode?"
    
    def _extract_data_properly(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Proper data extraction that actually works"""
        data = {}
        
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress']:
                if context.get(key):
                    data[key] = context[key]
        
        postcode_patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})\b',
            r'M1\s*1AB|M11AB',
        ]
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean = match.strip().replace(' ', '')
                if len(clean) >= 5:
                    data['postcode'] = clean
                    print(f"✅ FOUND POSTCODE: {clean}")
                    break
        
        name_patterns = [
            r'[Nn]ame\s+(\w+\s+\w+)',
            r'[Nn]ame\s+(\w+)',
            r'my name is (\w+)',
            r'i\'m (\w+)',
            r'call me (\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip().title()
                data['firstName'] = name
                print(f"✅ FOUND NAME: {name}")
                break
        
        phone_patterns = [
            r'payment link to (\d{11})',
            r'link to (\d{11})',
            r'to (\d{11})',
            r'\b(07\d{9})\b',
            r'\b(\d{11})\b'
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                phone = match.group(1)
                data['phone'] = phone
                print(f"✅ FOUND PHONE: {phone}")
                break
        
        materials = [
            'soil', 'muck', 'rubble', 'concrete', 'brick', 'sand', 'gravel',
            'construction', 'building', 'demolition', 'household', 'office', 
            'garden', 'wood', 'metal', 'general'
        ]
        found = []
        message_lower = message.lower()
        for material in materials:
            if material in message_lower:
                found.append(material)
        if found:
            data['material_type'] = ', '.join(found)
            print(f"✅ FOUND MATERIALS: {data['material_type']}")
        
        data['service'] = 'grab'
        
        return data
