import json 
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Man & Van specialist agent.

BUSINESS RULES:
- Heavy materials = MUST transfer to specialist (soil, concrete, bricks, rubble)
- Stairs/flats = MUST transfer to specialist
- Office hours transfers only: £500+ to specialist
- Out of hours: NEVER transfer, take callback
- Rate: £30 per cubic yard
- Minimum charge: £90

TRANSFER CONDITIONS:
- Heavy materials: "For heavy materials, I'll need to put you through to our specialist who can assess the requirements properly."
- Stairs: "For properties with stairs, I'll connect you with our specialist who handles complex access situations."
- High value (£500+ during office hours): Transfer to specialist
- Out of hours: "I'll take your details and have someone call you back during office hours."

Always check: items list, access (stairs/ground floor), approximate volume. for pricing always call get_pricing, no other word
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
            return "I understand. Let me help you with our man & van service. What items do you need collected?"
    
    def check_transfer_required(self, items: str, access: str, office_hours: bool, amount: float = 0) -> Dict:
        heavy_keywords = ["soil", "concrete", "bricks", "rubble", "stone", "tiles"]
        stairs_keywords = ["stairs", "flat", "floor", "upstairs", "apartment"]
        
        has_heavy = any(keyword in items.lower() for keyword in heavy_keywords)
        has_stairs = any(keyword in access.lower() for keyword in stairs_keywords)
        
        if has_heavy:
            return {"transfer": True, "reason": "heavy_materials"}
        
        if has_stairs:
            return {"transfer": True, "reason": "stairs_access"}
        
        if office_hours and amount >= 500:
            return {"transfer": True, "reason": "high_value"}
        
        if not office_hours and amount > 0:
            return {"transfer": False, "reason": "out_of_hours_callback"}
        
        return {"transfer": False, "reason": "none"}
