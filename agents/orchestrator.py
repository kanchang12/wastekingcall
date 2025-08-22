# agents/orchestrator.py - ULTRA SIMPLE VERSION
# NO state management, NO complex routing, just basic message routing

import re
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

class AgentOrchestrator:
    """SIMPLE orchestrator - just routes messages to agents"""
    
    def __init__(self, llm, agents: Dict[str, Any], storage_backend=None):
        self.llm = llm
        self.agents = agents
        
        print("✅ AgentOrchestrator initialized - SIMPLE MODE")
        print(f"✅ Available agents: {list(agents.keys())}")
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """SIMPLE: Route message to agent and return response"""
        
        print(f"\n🎯 SIMPLE ORCHESTRATOR: {conversation_id}")
        print(f"📝 Message: {message}")
        
        try:
            # SIMPLE routing
            agent_name = self._simple_routing(message)
            agent = self.agents.get(agent_name)
            
            print(f"🎯 ROUTING TO: {agent_name}")
            
            # SIMPLE context
            simple_context = context or {}
            
            # Add postcode if we can find it
            postcode_match = re.search(r'LS\d{4}|[A-Z]{1,2}\d{1,4}[A-Z]{0,2}', message.upper())
            if postcode_match:
                simple_context['postcode'] = postcode_match.group(0).replace(' ', '')
            
            # Process with agent
            response = agent.process_message(message, simple_context)
            
            return {
                "success": True,
                "response": response,
                "agent_used": agent_name
            }
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return {
                "success": False,
                "response": "What's your postcode and what do you need collected?",
                "error": str(e)
            }
    
    def _simple_routing(self, message: str) -> str:
        """ULTRA SIMPLE routing - just check for keywords"""
        
        message_lower = message.lower()
        
        # Man & Van keywords
        if any(word in message_lower for word in ['man', 'van', 'mav', 'sofa', 'furniture', 'table', 'chair']):
            return 'mav'
        
        # Skip keywords  
        if any(word in message_lower for word in ['skip', 'yard', 'yd', 'container']):
            return 'skip_hire'
        
        # Everything else = grab
        return 'grab_hire'
