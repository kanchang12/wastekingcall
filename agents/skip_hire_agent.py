import json
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Skip Hire specialist agent.

BUSINESS RULES:
- For heavy materials (soil, rubble, concrete): MAX 8-yard skip
- 12-yard skips ONLY for light materials
- If customer asks for 10+ yard for heavy materials, say exactly:
  "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard. Shall I get you the cost of an 8-yard skip?"
- Sofas CANNOT go in skips - say exactly: "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service."
- For road placement, use exact permit script: "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote."
- MUST suggest MAV for 8-yard or smaller + light materials

EXACT SCRIPTS - Use word for word:
- Heavy materials: "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard. Shall I get you the cost of an 8-yard skip?"
- Sofa prohibition: "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service. We charge extra due to EA regulations."
- MAV suggestion: "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"

Always collect: name, postcode, waste type before pricing.
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
            return "I understand. Let me help you with your skip hire needs. What's your postcode?"
    
    def check_heavy_materials(self, waste_type: str, skip_size: str) -> bool:
        heavy_materials = ["soil", "rubble", "concrete", "bricks", "stone", "hardcore"]
        large_sizes = ["10yd", "12yd", "14yd", "16yd"]
        
        has_heavy = any(material in waste_type.lower() for material in heavy_materials)
        is_large = any(size in skip_size.lower() for size in large_sizes)
        
        return has_heavy and is_large
    
    def should_suggest_mav(self, waste_type: str, skip_size: str) -> bool:
        light_materials = ["household", "garden", "furniture", "general", "mixed"]
        small_sizes = ["4yd", "6yd", "8yd"]
        
        has_light = any(material in waste_type.lower() for material in light_materials)
        is_small = any(size in skip_size.lower() for size in small_sizes)
        
        return has_light and is_small
