import json
from typing import Dict, Any, List, Optional
from langchain.prompts import PromptTemplate

class AgentOrchestrator:
    def __init__(self, llm, agents: Dict):
        self.llm = llm
        self.agents = agents
        self.conversation_state = {}
        
        self.routing_prompt = PromptTemplate(
            input_variables=["message", "conversation_history", "active_services"],
            template="""Route this customer message to the appropriate WasteKing agent(s).

Customer Message: {message}
Conversation History: {conversation_history}
Currently Active Services: {active_services}

Available Agents:
- skip_hire: Handle skip hire, container rental, waste bins
- mav: Handle collection services, clearance
- grab_hire: Handle grab lorries, muck away services  
- pricing: Handle pricing calculations, surcharges, VAT

Routing Rules:
- If customer mentions specific service, route to that agent
- If pricing mentioned, include pricing agent
- If multiple services mentioned, route to multiple agents
- If unclear, route to skip_hire as default

Return JSON: {{"primary_agent": "agent_name", "secondary_agents": ["agent1", "agent2"], "reasoning": "explanation"}}
"""
        )
        
        self.routing_chain = self.routing_prompt | self.llm
    
    def extract_customer_data(self, message: str) -> Dict[str, str]:
        """Extract customer data that can be shared across agents"""
        import re
        data = {}
        
        # Extract postcode
        postcode_match = re.search(r'postcode\s+([A-Z0-9]+)', message, re.IGNORECASE)
        if postcode_match:
            pc = postcode_match.group(1).upper()
            # Only accept valid postcodes
            if len(pc) <= 8 and not any(word in pc for word in ['DELTA', 'ECO', 'KO']):
                data['postcode'] = pc
        
        # Extract name
        name_match = re.search(r'name\s+(\w+)', message, re.IGNORECASE)
        if name_match:
            data['name'] = name_match.group(1)
            
        # Extract contact
        contact_match = re.search(r'contact\s+(\d+)', message, re.IGNORECASE)
        if contact_match:
            data['contact'] = contact_match.group(1)
            
        return data
    
    def process_customer_message(self, message: str, conversation_id: str) -> Dict[str, Any]:
        print(f"🎯 Orchestrator processing: {message}")
        
        # Get conversation state and ensure customer_data exists
        if conversation_id not in self.conversation_state:
            self.conversation_state[conversation_id] = {
                "active_services": [],
                "customer_data": {},
                "conversation_history": []
            }
        
        state = self.conversation_state[conversation_id]
        
        # Extract and PERSIST customer data across messages
        extracted_data = self.extract_customer_data(message)
        state["customer_data"].update(extracted_data)
        
        print(f"🎯 Persistent customer data: {state['customer_data']}")
        
        state["conversation_history"].append({"type": "customer", "message": message})
        
        # Route to appropriate agent(s)
        routing_decision = self._route_message(message, state)
        print(f"🎯 Routing to: {routing_decision}")
        
        # Process with primary agent, passing the PERSISTENT customer_data
        primary_response = self._process_with_agent(
            routing_decision["primary_agent"], 
            message, 
            state
        )
        
        print(f"🎯 Primary agent response: {primary_response}")
        
        # Skip secondary agents if primary agent gave good response
        if "£" in primary_response and len(primary_response) > 50:
            final_response = primary_response
        else:
            # Process with secondary agents if needed
            secondary_responses = {}
            for agent_name in routing_decision.get("secondary_agents", []):
                secondary_responses[agent_name] = self._process_with_agent(
                    agent_name, 
                    message, 
                    state
                )
            
            # Coordinate responses
            final_response = self._coordinate_responses(
                primary_response,
                secondary_responses,
                state
            )
        
        print(f"🎯 Final orchestrator response: {final_response}")
        
        state["conversation_history"].append({"type": "agent", "message": final_response})
        
        return {
            "response": final_response,
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
            
            # Handle the new format - routing_result is now a string, not dict with "text" key
            if isinstance(routing_result, str):
                return json.loads(routing_result)
            else:
                return json.loads(routing_result.content)
        except Exception as e:
            print(f"❌ Routing error: {e}")
            # Simple keyword-based routing as fallback
            message_lower = message.lower()
            if any(word in message_lower for word in ["man", "van", "collection", "clearance"]):
                return {"primary_agent": "mav", "secondary_agents": [], "reasoning": "keyword_fallback"}
            elif any(word in message_lower for word in ["grab", "lorry", "wheeler", "muck"]):
                return {"primary_agent": "grab_hire", "secondary_agents": [], "reasoning": "keyword_fallback"}
            elif any(word in message_lower for word in ["price", "cost", "quote", "pricing"]):
                return {"primary_agent": "pricing", "secondary_agents": [], "reasoning": "keyword_fallback"}
            else:
                return {"primary_agent": "skip_hire", "secondary_agents": [], "reasoning": "default_fallback"}
    
    def _process_with_agent(self, agent_name: str, message: str, state: Dict) -> str:
        print(f"🤖 Processing with {agent_name} agent")
        
        if agent_name in self.agents:
            try:
                # Pass the temporary customer data dictionary to the agent's process_message method
                response = self.agents[agent_name].process_message(message, state["customer_data"])
                print(f"🤖 {agent_name} agent returned: {response}")
                return response
            except Exception as e:
                print(f"❌ Agent {agent_name} error: {e}")
                return f"Hello! I'm here to help with {agent_name.replace('_', ' ')}. How can I assist you today?"
        else:
            print(f"❌ Agent {agent_name} not found")
            return "Hello! How can I help you today?"
    
    def _coordinate_responses(self, primary: str, secondary: Dict, state: Dict) -> str:
        # If no secondary responses, return primary
        if not secondary:
            return primary
        
        # If we have secondary responses, intelligently combine them
        all_responses = [primary]
        for agent_name, response in secondary.items():
            if response and response != primary:
                all_responses.append(response)
        
        # Return the most comprehensive response or combine if needed
        if len(all_responses) == 1:
            return all_responses[0]
        else:
            # Combine responses intelligently
            return " ".join(all_responses)
