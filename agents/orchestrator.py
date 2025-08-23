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
            print("✅ Using cached PDF rules")
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
                print("✅ PDF rules loaded and cached")
                return text
            else:
                print("⚠️ PDF rules file not found, using basic rules")
                _PDF_RULES_CACHE = "Basic routing rules"
                return _PDF_RULES_CACHE
        except Exception as e:
            print(f"⚠️ Error loading PDF: {e}")
            _PDF_RULES_CACHE = f"Error loading PDF: {str(e)}"
            return _PDF_RULES_CACHE
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        print(f"\n🎯 ORCHESTRATOR RECEIVED: '{message}' (ID: {conversation_id})")
        
        conversation_state = self._load_conversation_state(conversation_id)
        self._extract_and_update_state(message, conversation_state, context)
        
        extracted = conversation_state.get('extracted_info', {})
        print(f"📋 EXTRACTED DATA: {json.dumps(extracted, indent=2)}")
        
        # Handle transfers from agents
        if message.startswith('TRANSFER_TO_ORCHESTRATOR:'):
            print("🔄 HANDLING AGENT TRANSFER")
            transfer_data = json.loads(message.split('TRANSFER_TO_ORCHESTRATOR:')[1])
            extracted.update(transfer_data)
            conversation_state['extracted_info'] = extracted
            routing_decision = self._determine_service_routing_with_rules(message, extracted)
        else:
            # ALWAYS route based on message content
            routing_decision = self._determine_service_routing_with_rules(message, extracted)
        
        print(f"🎯 ROUTING DECISION: {routing_decision}")
        
        if routing_decision['agent'] in self.agents:
            print(f"🔀 ROUTING TO AGENT: {routing_decision['agent']}")
            agent = self.agents[routing_decision['agent']]
            context_with_id = {**(context or {}), **extracted, 'conversation_id': conversation_id}
            response = agent.process_message(message, context_with_id)
            agent_used = routing_decision['agent']
            print(f"✅ AGENT RESPONSE: {response}")
        else:
            print("❌ NO AGENT FOUND - FALLBACK")
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
        
        print(f"🔍 ROUTING ANALYSIS: '{message}'")
        
        # Skip hire - specific requests
        if any(word in message_lower for word in ['skip', 'skip hire']):
            print("→ ROUTING TO SKIP HIRE (explicit request)")
            return {'agent': 'skip_hire', 'reason': 'skip_requested'}
        
        # Man & Van - specific requests  
        elif any(word in message_lower for word in ['mav', 'man and van', 'man & van', 'furniture', 'household items']):
            print("→ ROUTING TO MAN & VAN (light items)")
            return {'agent': 'mav', 'reason': 'mav_requested'}
        
        # GRAB HIRE - everything else (default for all other requests)
        else:
            print("→ ROUTING TO GRAB HIRE (handles everything else)")
            return {'agent': 'grab_hire', 'reason': 'grab_handles_everything_else'}
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any], context: Dict = None):
        extracted = state.get('extracted_info', {})
        
        if context:
            extracted.update(context)
        
        # Extract postcode
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})', message.upper().replace(' ', ''))
        if postcode_match:
            extracted['postcode'] = postcode_match.group(1)
            print(f"✅ EXTRACTED POSTCODE: {extracted['postcode']}")
        
        # Extract name
        name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
        if name_match:
            extracted['firstName'] = name_match.group(1).strip().title()
            print(f"✅ EXTRACTED NAME: {extracted['firstName']}")
        
        # Extract phone
        phone_match = re.search(r'\b(07\d{9}|\d{11})\b', message)
        if phone_match:
            extracted['phone'] = phone_match.group(1)
            print(f"✅ EXTRACTED PHONE: {extracted['phone']}")
        
        state['extracted_info'] = extracted
    
    def _load_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        global _GLOBAL_CONVERSATION_STATES
        if conversation_id in _GLOBAL_CONVERSATION_STATES:
            print(f"📂 LOADED EXISTING STATE for {conversation_id}")
            return _GLOBAL_CONVERSATION_STATES[conversation_id].copy()
        print(f"📝 NEW CONVERSATION STATE for {conversation_id}")
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
        print(f"💾 SAVED CONVERSATION STATE for {conversation_id}")
