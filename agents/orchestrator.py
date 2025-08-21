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
            input_variables=["message", "conversation_history", "customer_data"],
            template="""Route this customer message to the appropriate WasteKing agent(s).

Customer Message: {message}
Conversation History: {conversation_history}
Current Customer Data: {customer_data}

Available Agents:
- data_collector: Handle initial data collection (name, postcode, phone, etc.).
- skip_hire: Handle skip hire, container rental, waste bins.
- man_and_van: Handle collection services, clearance.
- grab_hire: Handle grab lorries, muck away services.
- pricing: Handle pricing calculations, surcharges, VAT.

Routing Rules:
- If customer data is incomplete, route to data_collector first.
- If customer provides details (name, postcode, phone, etc.), route to data_collector to store the information.
- Once all basic information is collected, route based on the service mentioned.
- If customer mentions specific service, route to that agent.
- If pricing is mentioned, include the pricing agent.
- If multiple services are mentioned, route to multiple agents.
- If unclear, route to skip_hire as default.

Return JSON: {{"primary_agent": "agent_name", "secondary_agents": ["agent1", "agent2"], "reasoning": "explanation"}}
"""
        )
        
        self.routing_chain = LLMChain(llm=self.llm, prompt=self.routing_prompt)
    
    def process_customer_message(self, message: str, conversation_id: str) -> Dict[str, Any]:
        print(f"🎯 Orchestrator processing: {message}")
        
        if conversation_id not in self.conversation_state:
            self.conversation_state[conversation_id] = {
                "customer_data": {},
                "conversation_history": []
            }
        
        state = self.conversation_state[conversation_id]
        state["conversation_history"].append({"type": "customer", "message": message})
        
        routing_decision = self._route_message(message, state)
        print(f"🎯 Routing to: {routing_decision}")
        
        primary_response = self._process_with_agent(
            routing_decision["primary_agent"], 
            message, 
            state
        )
        
        print(f"🎯 Primary agent response: {primary_response}")
        
        secondary_responses = {}
        for agent_name in routing_decision.get("secondary_agents", []):
            secondary_responses[agent_name] = self._process_with_agent(
                agent_name, 
                message, 
                state
            )
        
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
        # Define the basic data fields we need to collect
        required_data_fields = ["name", "postcode", "service_type", "waste_category", "amount", "phone_number"]
        
        # Check if all basic data has been collected
        is_data_complete = all(field in state["customer_data"] for field in required_data_fields)
        
        # If data is incomplete, prioritize routing to the data_collector agent
        if not is_data_complete:
            return {"primary_agent": "data_collector", "secondary_agents": [], "reasoning": "Collecting initial customer data."}
            
        # If data is complete, proceed with regular routing based on the message
        try:
            routing_result = self.routing_chain.invoke({
                "message": message,
                "conversation_history": json.dumps(state["conversation_history"][-5:]),
                "customer_data": json.dumps(state["customer_data"])
            })
            return json.loads(routing_result["text"])
        except Exception as e:
            print(f"❌ Routing error: {e}")
            message_lower = message.lower()
            if any(word in message_lower for word in ["man", "van", "collection", "clearance"]):
                return {"primary_agent": "man_and_van", "secondary_agents": [], "reasoning": "keyword_fallback"}
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
                response = self.agents[agent_name].process_message(message, state)
                print(f"🤖 {agent_name} agent returned: {response}")
                return response
            except Exception as e:
                print(f"❌ Agent {agent_name} error: {e}")
                return f"I can help you with {agent_name.replace('_', ' ')}. Could you provide more details?"
        else:
            print(f"❌ Agent {agent_name} not found")
            return "I understand. How can I help you today?"
    
    def _coordinate_responses(self, primary: str, secondary: Dict, state: Dict) -> str:
        if not secondary:
            return primary
        all_responses = [primary]
        for agent_name, response in secondary.items():
            if response and response != primary:
                all_responses.append(response)
        if len(all_responses) == 1:
            return all_responses[0]
        else:
            return " ".join(all_responses)
