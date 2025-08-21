import json 
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory

class PricingAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
        
        self.surcharge_rates = {
            "fridge": 20,
            "freezer": 20, 
            "mattress": 15,
            "sofa": 15,
            "furniture": 15,
            "upholstered": 15
        }
        
        self.base_prices = {
            "skip_hire": {"4yd": 180, "6yd": 200, "8yd": 220, "12yd": 280},
            "man_and_van": {"rate_per_yard": 30, "minimum": 90},
            "grab_hire": {"6_wheeler": 250, "8_wheeler": 300}
        }
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Pricing specialist agent.

PRICING RULES:
- ALL prices are excluding VAT - always clarify this
- Present TOTAL price including all surcharges
- Surcharge rates: Fridge/Freezer £20, Mattress £15, Sofa/Furniture £15
- VAT must be spelled as "V-A-T" for voice pronunciation
- Never quote base price only when surcharges apply

EXACT PRICING PRESENTATION:
"Your [service] is £[base_price], plus £[surcharge_amount] for [items], making your total £[final_price] excluding V-A-T."

Always use SMP API for real pricing when possible, fallback to base rates if API fails.
"""),
            ("human", "{input}"),
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
            memory=self.memory,
            verbose=True,
            max_iterations=3
        )
    
    def process_message(self, message: str, context: Dict = None) -> str:
        try:
            response = self.executor.invoke({
                "input": message,
                "context": json.dumps(context) if context else "{}"
            })
            return response["output"]
        except Exception as e:
            return "I'll get you an accurate price. What's your postcode?"
    
    def calculate_surcharges(self, items: List[str]) -> Dict:
        total_surcharge = 0
        surcharge_breakdown = []
        
        for item in items:
            item_lower = item.lower()
            for surcharge_item, rate in self.surcharge_rates.items():
                if surcharge_item in item_lower:
                    total_surcharge += rate
                    surcharge_breakdown.append({"item": item, "rate": rate})
        
        return {
            "total_surcharge": total_surcharge,
            "breakdown": surcharge_breakdown
        }
    
    def format_pricing_response(self, service: str, base_price: float, surcharges: Dict) -> str:
        if surcharges["total_surcharge"] > 0:
            return f"Your {service} is £{base_price}, plus £{surcharges['total_surcharge']} for additional items, making your total £{base_price + surcharges['total_surcharge']} excluding V-A-T."
        else:
            return f"Your {service} is £{base_price} excluding V-A-T."
