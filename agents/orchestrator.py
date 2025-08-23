import re
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
import PyPDF2
from utils.state_manager import StateManager

# PDF RULES CACHE
_PDF_RULES_CACHE = None
# GLOBAL STATE STORAGE
_GLOBAL_CONVERSATION_STATES = {}

class AgentOrchestrator:
    def __init__(self, llm, agents):
        self.llm = llm
        self.agents = agents
        self.state_manager = StateManager(os.getenv('DATABASE_PATH', 'conversations.db'))
        self.pdf_rules = self._load_pdf_rules_with_cache()
        
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        
        print("✅ AgentOrchestrator: Router with PDF rules initialized")
        print("✅ Available agents:", list(self.agents.keys()))
    
    def _load_pdf_rules_with_cache(self) -> str:
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
                _PDF_RULES_CACHE = "Basic routing rules"
                return _PDF_RULES_CACHE
        except Exception as e:
            _PDF_RULES_CACHE = f"Error loading PDF: {str(e)}"
            return _PDF_RULES_CACHE
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        conversation_state = self._load_conversation_state(conversation_id)
        self._extract_and_update_state(message, conversation_state, context)
        
        extracted = conversation_state.get('extracted_info', {})
        
        # Handle transfers from agents
        if message.startswith('TRANSFER_TO_ORCHESTRATOR:'):
            transfer_data = json.loads(message.split('TRANSFER_TO_ORCHESTRATOR:')[1])
            extracted.update(transfer_data)
            conversation_state['extracted_info'] = extracted
            routing_decision = self._determine_service_routing_with_rules(message, extracted)
        # First message or general inquiry
        elif not conversation_state.get('messages') or len(conversation_state.get('messages', [])) == 0:
            response = "How may I help you today?"
            agent_used = 'orchestrator'
            self._save_conversation_state(conversation_id, conversation_state, message, response, agent_used)
            return {
                "success": True,
                "response": response,
                "conversation_id": conversation_id,
                "agent_used": agent_used,
                "timestamp": datetime.now().isoformat()
            }
        else:
            routing_decision = self._determine_service_routing_with_rules(message, extracted)
        
        if routing_decision['agent'] in self.agents:
            agent = self.agents[routing_decision['agent']]
            context_with_id = {**(context or {}), **extracted, 'conversation_id': conversation_id}
            response = agent.process_message(message, context_with_id)
            agent_used = routing_decision['agent']
        else:
            response = "How may I help you today?"
            agent_used = 'orchestrator'
        
        self._save_conversation_state(conversation_id, conversation_state, message, response, agent_used)
        
        return {
            "success": True,
            "response": response,
            "conversation_id": conversation_id,
            "agent_used": agent_used,
            "timestamp": datetime.now().isoformat()
        }
    
    def _determine_service_routing_with_rules(self, message: str, extracted: Dict) -> Dict[str, str]:
        message_lower = message.lower()
        rules_lower = self.pdf_rules.lower()
        
        if any(word in message_lower for word in ['skip', 'skip hire']):
            return {'agent': 'skip_hire', 'reason': 'skip_requested'}
        elif any(word in message_lower for word in ['grab', 'grab hire']):
            return {'agent': 'grab_hire', 'reason': 'grab_requested'}
        elif any(word in message_lower for word in ['mav', 'man and van', 'man & van']):
            return {'agent': 'mav', 'reason': 'mav_requested'}
        else:
            # Use PDF rules for routing
            if any(word in message_lower for word in ['soil', 'concrete', 'rubble', 'heavy']):
                return {'agent': 'grab_hire', 'reason': 'heavy_materials'}
            elif any(word in message_lower for word in ['furniture', 'household']):
                return {'agent': 'mav', 'reason': 'light_items'}
            else:
                return {'agent': 'grab_hire', 'reason': 'default'}
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any], context: Dict = None):
        extracted = state.get('extracted_info', {})
        
        if context:
            extracted.update(context)
        
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})', message.upper().replace(' ', ''))
        if postcode_match:
            extracted['postcode'] = postcode_match.group(1)
        
        name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
        if name_match:
            extracted['firstName'] = name_match.group(1).strip().title()
        
        phone_match = re.search(r'\b(07\d{9}|\d{11})\b', message)
        if phone_match:
            extracted['phone'] = phone_match.group(1)
        
        state['extracted_info'] = extracted
    
    def _load_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        global _GLOBAL_CONVERSATION_STATES
        if conversation_id in _GLOBAL_CONVERSATION_STATES:
            return _GLOBAL_CONVERSATION_STATES[conversation_id].copy()
        return {"conversation_id": conversation_id, "messages": [], "extracted_info": {}}
    
    def _save_conversation_state(self, conversation_id: str, state: Dict[str, Any], message: str, response: str, agent_used: str):
        if 'messages' not in state:
            state['messages'] = []
        
        state['messages'].append({
            "timestamp": datetime.now().isoformat(),
            "customer_message": message,
            "agent_response": response,
            "agent_used": agent_used
        })
        
        if len(state['messages']) > 50:
            state['messages'] = state['messages'][-30:]
        
        state['last_updated'] = datetime.now().isoformat()
        
        global _GLOBAL_CONVERSATION_STATES
        _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
