import json 
import re
import os
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
import PyPDF2

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        # Direct PDF import from data/rules/all_rules.pdf
        pdf_rules = self._load_pdf_rules()
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a Skip Hire agent. Be FAST and DIRECT.

RULES FROM PDF KNOWLEDGE BASE:
{pdf_rules}

CRITICAL WORKFLOW:
1. If customer provides ALL info (postcode + waste + name + phone): IMMEDIATELY call create_booking_quote
2. If just pricing info: Call get_pricing then ask to book
3. Missing data → Ask once

API CALLS:
- BOOKING: smp_api(action="create_booking_quote", postcode=X, service="skip", firstName=X, phone=X, booking_ref=X)
- PRICING: smp_api(action="get_pricing", postcode=X, service="skip")

IMPORTANT: Customer says "Book" + provides name/phone = CREATE BOOKING IMMEDIATELY

Follow PDF rules above. Be direct."""),
            ("human", "Customer: {input}\n\nData: {extracted_info}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True, max_iterations=10)
    
    def _load_pdf_rules(self) -> str:
        """Load rules directly from data/rules/all rules.pdf"""
        try:
            pdf_path = "data/rules/all rules.pdf"
            print(f"🔧 SKIP AGENT: Loading PDF rules from: {pdf_path}")
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                print(f"🔧 SKIP AGENT: PDF rules loaded successfully ({len(text)} characters)")
                return text
            else:
                print(f"❌ SKIP AGENT: PDF rules not found at {pdf_path}")
                return "PDF rules not found - using basic skip hire rules"
        except Exception as e:
            print(f"❌ SKIP AGENT: Error loading PDF rules: {e}")
            return "PDF rules not available - using basic skip hire rules"
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Process with proper data extraction"""
        
        extracted_data = self._extract_data_properly(message, context)
        
        print(f"🔧 SKIP DATA: {json.dumps(extracted_data, indent=2)}")
        
        postcode = extracted_data.get('postcode')
        waste_type = extracted_data.get('waste_type')
        has_name = bool(extracted_data.get('firstName'))
        has_phone = bool(extracted_data.get('phone'))
        
        wants_booking = 'book' in message.lower()
        has_all_info = postcode and waste_type and has_name and has_phone
        
        print(f"🎯 DECISION:")
        print(f"   - Wants booking: {wants_booking}")
        print(f"   - Has all info: {has_all_info}")
        print(f"   - Name: {extracted_data.get('firstName')}")
        print(f"   - Phone: {extracted_data.get('phone')}")
        
        if wants_booking and has_all_info:
            action = "create_booking_quote"
            print(f"🔧 CREATING BOOKING IMMEDIATELY")
        elif postcode and waste_type:
            action = "get_pricing"
            print(f"🔧 GETTING PRICING FIRST")
        else:
            if not postcode:
                return "What's your postcode?"
            if not waste_type:
                return "What type of waste?"
            return "Let me get you a quote."
        
        extracted_info = f"""
Postcode: {postcode}
Waste Type: {waste_type}
Service: skip
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
            "action": action,
            **extracted_data
        }
        
        print(f"🔧 SKIP AGENT: Executing agent with action: {action}")
        print(f"🔧 SKIP AGENT: Tools available: {[tool.name for tool in self.tools]}")
        response = self.executor.invoke(agent_input)
        print(f"🔧 SKIP AGENT: Agent execution completed successfully")
        return response["output"]
    
    def _extract_data_properly(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Proper data extraction that actually works"""
        data = {}
        
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress', 'waste_type']:
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
        
        waste_types = ['household', 'construction', 'garden', 'mixed', 'bricks', 'concrete', 'soil', 'rubble']
        found = []
        message_lower = message.lower()
        for waste in waste_types:
            if waste in message_lower:
                found.append(waste)
        if found:
            data['waste_type'] = ', '.join(found)
            print(f"✅ FOUND WASTE: {data['waste_type']}")
        
        data['service'] = 'skip'
        
        return data
