import json
import re
from typing import Dict, Any, List, Optional
from langchain.prompts import PromptTemplate


class AgentOrchestrator:
    def __init__(self, llm, agents: Dict):
        self.llm = llm
        self.agents = agents
        self.conversation_state = {}
        
        self.routing_prompt = PromptTemplate(
            input_variables=["message", "conversation_history", "active_services"],
            template="""Route this customer message to the appropriate WasteKing agent.

Customer Message: {message}
Conversation History: {conversation_history}
Currently Active Services: {active_services}

Available Agents:
- skip_hire: Handle skip hire, container rental, waste bins
- mav: Handle man & van services, collection, clearance
- grab_hire: Handle grab lorries, muck away services  

Routing Rules:
- Skip hire: skip, container, bin, waste disposal
- Man & Van: collection, clearance, furniture removal, "man van", "man and van"
- Grab hire: grab lorry, muck away, bulk earth/soil removal
- If unclear, route to skip_hire as default

Return JSON: {{"primary_agent": "agent_name", "reasoning": "explanation"}}

You are taking way too much time asking same questions over and over and overwriting the data, you need to give the info in first time only. DOnt waste time and say I am looking into it
"""
        )
        
        self.routing_chain = self.routing_prompt | self.llm
    
    def extract_customer_data(self, message: str) -> Dict[str, str]:
        """Extract customer data that can be shared across agents"""
        data = {}
        
        # Extract postcode with proper UK format
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
            
        return data
    
    def process_customer_message(self, message: str, conversation_id: str, call_sid: str = None, elevenlabs_conversation_id: str = None) -> Dict[str, Any]:
        print(f"🎯 Orchestrator processing: {message}")
        
        # Initialize conversation state
        if conversation_id not in self.conversation_state:
            self.conversation_state[conversation_id] = {
                "active_services": [],
                "customer_data": {},
                "conversation_history": [],
                "booking_data": {}
            }
        
        state = self.conversation_state[conversation_id]
        
        # Add call tracking data
        if call_sid:
            state["customer_data"]["call_sid"] = call_sid
        if elevenlabs_conversation_id:
            state["customer_data"]["elevenlabs_conversation_id"] = elevenlabs_conversation_id
        
        # Extract and persist customer data
        extracted_data = self.extract_customer_data(message)
        state["customer_data"].update(extracted_data)
        
        state["conversation_history"].append({"type": "customer", "message": message})
        
        # Route to appropriate agent
        routing_decision = self._route_message(message, state)
        print(f"🎯 Routing to: {routing_decision}")
        
        # Process with primary agent
        primary_response = self._process_with_agent(
            routing_decision["primary_agent"], 
            message, 
            state
        )
        
        print(f"🎯 Agent response: {primary_response}")
        
        state["conversation_history"].append({"type": "agent", "message": primary_response})
        
        return {
            "response": primary_response,
            "conversation_id": conversation_id,
            "routing": routing_decision,
            "state": state
        }
    
    def _route_message(self, message: str, state: Dict) -> Dict:
        try:
            routing_result = self.routing_chain.invoke({
                "message": message,
                "conversation_history": json.dumps(state["conversation_history"][-5:]),
                "active_services": json.dumps(state["active_services"])
            })
            
            # Handle the response format
            if isinstance(routing_result, str):
                return json.loads(routing_result)
            elif hasattr(routing_result, 'content'):
                return json.loads(routing_result.content)
            else:
                return routing_result
        except Exception as e:
            print(f"❌ Routing error: {e}")
            # Keyword-based routing fallback
            message_lower = message.lower()
            if any(word in message_lower for word in ["man", "van", "collection", "clearance", "furniture"]):
                return {"primary_agent": "mav", "reasoning": "keyword_fallback"}
            elif any(word in message_lower for word in ["grab", "lorry", "wheeler", "muck"]):
                return {"primary_agent": "grab_hire", "reasoning": "keyword_fallback"}
            else:
                return {"primary_agent": "skip_hire", "reasoning": "default_fallback"}
    
    def _process_with_agent(self, agent_name: str, message: str, state: Dict) -> str:
        print(f"🤖 Processing with {agent_name} agent")
        
        if agent_name in self.agents:
            try:
                response = self.agents[agent_name].process_message(message, state["customer_data"])
                return response
            except Exception as e:
                print(f"❌ Agent {agent_name} error: {e}")
                return f"Hello! I'm here to help with {agent_name.replace('_', ' ')}. How can I assist you today?"
        else:
            print(f"❌ Agent {agent_name} not found")
            return "Hello! How can I help you today?"
