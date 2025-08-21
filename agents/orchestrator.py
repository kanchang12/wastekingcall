import json
from typing import Dict, Any, List, Optional
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferWindowMemory

class AgentOrchestrator:
    def __init__(self, llm, agents: Dict):
        self.llm = llm
        self.agents = agents
        self.memory = ConversationBufferWindowMemory(k=20, return_messages=True)
        self.conversation_state = {}
        
        self.routing_prompt = PromptTemplate(
            input_variables=["message", "conversation_history", "active_services"],
            template="""Route this customer message to the appropriate WasteKing agent(s).

Customer Message: {message}
Conversation History: {conversation_history}
Currently Active Services: {active_services}

Available Agents:
- skip_hire: Handle skip hire, container rental, waste bins
- man_and_van: Handle collection services, clearance
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
        
        self.routing_chain = LLMChain(llm=self.llm, prompt=self.routing_prompt)
    
    def process_customer_message(self, message: str, conversation_id: str) -> Dict[str, Any]:
        # Get conversation state
        if conversation_id not in self.conversation_state:
            self.conversation_state[conversation_id] = {
                "active_services": [],
                "customer_data": {},
                "conversation_history": []
            }
        
        state = self.conversation_state[conversation_id]
        state["conversation_history"].append({"type": "customer", "message": message})
        
        # Route to appropriate agent(s)
        routing_decision = self._route_message(message, state)
        
        # Process with primary agent
        primary_response = self._process_with_agent(
            routing_decision["primary_agent"], 
            message, 
            state
        )
        
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
        
        state["conversation_history"].append({"type": "agent", "message": final_response})
        
        return {
            "response": final_response,
            "conversation_id": conversation_id,
            "routing": routing_decision,
            "state": state
        }
    
    def _route_message(self, message: str, state: Dict) -> Dict:
        try:
            routing_result = self.routing_chain.run(
                message=message,
                conversation_history=json.dumps(state["conversation_history"][-5:]),
                active_services=json.dumps(state["active_services"])
            )
            return json.loads(routing_result)
        except:
            return {"primary_agent": "skip_hire", "secondary_agents": [], "reasoning": "default"}
    
    def _process_with_agent(self, agent_name: str, message: str, state: Dict) -> str:
        if agent_name in self.agents:
            return self.agents[agent_name].process_message(message, state)
        return "I understand. How can I help you today?"
    
    def _coordinate_responses(self, primary: str, secondary: Dict, state: Dict) -> str:
        if not secondary:
            return primary
        
        # Simple coordination - combine responses
        all_responses = [primary] + list(secondary.values())
        return " ".join(all_responses)
    
    def detect_services_in_message(self, message: str) -> List[str]:
        message_lower = message.lower()
        services = []
        
        skip_keywords = ["skip", "container", "bin", "yard", "disposal"]
        mav_keywords = ["man and van", "collection", "clearance", "man & van"]
        grab_keywords = ["grab", "lorry", "muck away", "wheeler"]
        
        if any(keyword in message_lower for keyword in skip_keywords):
            services.append("skip_hire")
        if any(keyword in message_lower for keyword in mav_keywords):
            services.append("man_and_van")
        if any(keyword in message_lower for keyword in grab_keywords):
            services.append("grab_hire")
            
        return services
