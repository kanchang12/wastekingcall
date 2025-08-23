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

        # Prompt: instruct agent to follow rules dynamically
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are Skip Hire agent. Follow the customer interaction flow
defined in the PDF rules below. Do not hardcode steps – always follow the PDF.

PDF RULES:
{self.pdf_rules}

⚠️ Instructions:
- Ask questions in the sequence defined in PDF.
- Collect required info step by step.
- Call tools when reaching pricing or booking stages.
- If customer request belongs to another service (grab, man & van), 
  transfer back to orchestrator:
  TRANSFER_TO_ORCHESTRATOR:{{collected_data}}
"""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)

    def _load_pdf_rules_with_cache(self) -> str:
        """Load PDF rules once, cache globally"""
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
        """Load saved state"""
        global _AGENT_STATES
        return _AGENT_STATES.get(conversation_id, {})

    def _save_state(self, conversation_id: str, data: Dict[str, Any]):
        """Save extracted state"""
        global _AGENT_STATES
        _AGENT_STATES[conversation_id] = data

    def process_message(self, message: str, context: Dict = None) -> str:
        conversation_id = context.get('conversation_id') if context else 'default'
        
        # Load state
        previous_state = self._load_state(conversation_id)
        
        # Extract info
        extracted_data = self._extract_data(message, context)
        combined_data = {**previous_state, **extracted_data}

        # Transfer check
        transfer_check = self._check_transfer_needed_with_rules(message, combined_data)
        if transfer_check:
            self._save_state(conversation_id, combined_data)
            return f"TRANSFER_TO_ORCHESTRATOR:{json.dumps(combined_data)}"

        # Determine next step based on PDF flow
        current_step = self._determine_step_from_rules(combined_data)

        if current_step == "pricing":
            combined_data['has_pricing'] = True
            response = self._get_pricing(combined_data)
        elif current_step == "booking":
            response = self._create_booking(combined_data)
        else:
            # Ask the question that PDF rules say should be next
            response = self._get_question_for_step(current_step)

        # Save updated state
        self._save_state(conversation_id, combined_data)
        return response

    def _check_transfer_needed_with_rules(self, message: str, data: Dict[str, Any]) -> bool:
        """Check if customer should be transferred using PDF rules"""
        msg = message.lower()
        rules_lower = self.pdf_rules.lower()
        if "grab" in msg or "grab hire" in msg:
            return True
        if "man and van" in msg or "mav" in msg or "furniture" in msg:
            return True
        # TODO: could parse PDF rules to identify other transfer keywords
        return False

    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        data = context.copy() if context else {}

        # Normalize postcode → m11ab format
        postcode_match = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b', message.upper())
        if postcode_match:
            normalized = postcode_match.group(1).replace(" ", "").lower()
            data['postcode'] = normalized

        # Name
        name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
        if name_match:
            data['firstName'] = name_match.group(1).strip().title()

        # Phone
        phone_match = re.search(r'\b(07\d{9}|\d{11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)

        # Product detection
        if not data.get('product') and any(size in message.lower() for size in ['4yd', '6yd', '8yd', '12yd']):
            for size in ['4yd', '6yd', '8yd', '12yd']:
                if size in message.lower():
                    data['product'] = size
                    break

        # Waste type, quantity, date, etc. (simple keyword match)
        if not data.get('waste_type') and any(w in message.lower() for w in ['waste', 'rubbish', 'materials']):
            data['waste_type'] = message.strip()

        if not data.get('quantity') and any(w in message.lower() for w in ['full', 'half', 'bags', 'tonnes']):
            data['quantity'] = message.strip()

        if not data.get('preferred_date') and any(w in message.lower() for w in ['tomorrow', 'today', 'monday', 'tuesday', 'week']):
            data['preferred_date'] = message.strip()

        return data

    def _determine_step_from_rules(self, data: Dict[str, Any]) -> str:
        """
        Decide the next step based on rules from PDF instead of hardcoding.
        For simplicity, this assumes the PDF lists steps in order like:
        name → postcode → product → waste → quantity → specifics → pricing → date → booking
        """
        # These would be parsed dynamically from PDF if structured
        if not data.get('firstName'): return "name"
        if not data.get('postcode'): return "postcode"
        if not data.get('product'): return "product"
        if not data.get('waste_type'): return "waste_type"
        if not data.get('quantity'): return "quantity"
        if not data.get('product_specific'): return "product_specific"
        if not data.get('has_pricing'): return "pricing"
        if not data.get('preferred_date'): return "date"
        return "booking"

    def _get_question_for_step(self, step: str) -> str:
        """
        Ask the appropriate question for this step using PDF rules.
        In production, parse the actual text of PDF to generate these.
        """
        mapping = {
            "name": "What's your name?",
            "postcode": "What's your postcode?",
            "product": "What size skip do you need?",
            "waste_type": "What type of waste?",
            "quantity": "How much waste do you have?",
            "product_specific": "Any specific requirements?",
            "date": "When would you like delivery?",
        }
        return mapping.get(step, "Can you provide more details?")

    def _get_pricing(self, data: Dict[str, Any]) -> str:
        try:
            query = (
                f"Get pricing for a {data.get('product', '8yd')} skip "
                f"at postcode {data.get('postcode')} "
                f"for waste type {data.get('waste_type', 'general')}."
            )
            response = self.executor.invoke({"input": query})
            return response["output"]
        except Exception as e:
            return f"Error getting pricing: {str(e)}"

    def _create_booking(self, data: Dict[str, Any]) -> str:
        try:
            booking_ref = str(uuid.uuid4())[:8]
            query = (
                f"Create booking for {data.get('firstName', 'customer')} "
                f"at postcode {data.get('postcode')} "
                f"for a {data.get('product', '8yd')} skip. "
                f"Phone: {data.get('phone', 'unknown')}. "
                f"Booking reference: {booking_ref}."
            )
            response = self.executor.invoke({"input": query})
            return response["output"]
        except Exception as e:
            return f"Error creating booking: {str(e)}"
