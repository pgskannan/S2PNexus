from __future__ import annotations

from app.agents.agent_context import AgentContext
from app.agents.agent_response import AgentResponse
from app.agents.base_agent import BaseAgent


class DocumentAgent(BaseAgent):
    name = "document-agent"
    description = "Handles document-related requests"
    capabilities = ("documents",)

    def can_handle(self, request: str) -> bool:
        return "document" in request.lower() or "file" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["inspect document request", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Document agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles document-oriented questions."


class KnowledgeAgent(BaseAgent):
    name = "knowledge-agent"
    description = "Handles knowledge-base questions"
    capabilities = ("knowledge",)

    def can_handle(self, request: str) -> bool:
        return "knowledge" in request.lower() or "faq" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["retrieve knowledge context", "craft response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Knowledge agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles knowledge-base requests."


class ProcurementAgent(BaseAgent):
    name = "procurement-agent"
    description = "Handles procurement-related requests"
    capabilities = ("procurement",)

    def can_handle(self, request: str) -> bool:
        return "procurement" in request.lower() or "purchase" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review procurement request", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Procurement agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles procurement-oriented requests."


class SupplierAgent(BaseAgent):
    name = "supplier-agent"
    description = "Handles supplier requests"
    capabilities = ("supplier",)

    def can_handle(self, request: str) -> bool:
        return "supplier" in request.lower() or "vendor" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review supplier request", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Supplier agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles supplier-related requests."


class ContractAgent(BaseAgent):
    name = "contract-agent"
    description = "Handles contract requests"
    capabilities = ("contract",)

    def can_handle(self, request: str) -> bool:
        return "contract" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review contract request", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Contract agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles contract-oriented requests."


class ReportingAgent(BaseAgent):
    name = "reporting-agent"
    description = "Handles reporting requests"
    capabilities = ("report",)

    def can_handle(self, request: str) -> bool:
        return "report" in request.lower() or "summary" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["collect reporting context", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Reporting agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles reporting requests."


class SpendAnalysisAgent(BaseAgent):
    name = "spend-analysis-agent"
    description = "Handles spend analysis requests"
    capabilities = ("spend", "analysis")

    def can_handle(self, request: str) -> bool:
        return "spend" in request.lower() or "analysis" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review spend context", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Spend analysis agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles spend analysis requests."


class SourcingAgent(BaseAgent):
    name = "sourcing-agent"
    description = "Handles sourcing requests"
    capabilities = ("sourcing",)

    def can_handle(self, request: str) -> bool:
        return "sourcing" in request.lower() or "source" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review sourcing request", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Sourcing agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles sourcing requests."


class ReceiptAgent(BaseAgent):
    name = "receipt-agent"
    description = "Handles receipt requests"
    capabilities = ("receipt",)

    def can_handle(self, request: str) -> bool:
        return "receipt" in request.lower() or "invoice" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review receipt request", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Receipt agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles receipt-related requests."


class SupplierRiskAgent(BaseAgent):
    name = "supplier-risk-agent"
    description = "Handles supplier risk requests"
    capabilities = ("risk",)

    def can_handle(self, request: str) -> bool:
        return "risk" in request.lower() and "supplier" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review supplier risk context", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Supplier risk agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles supplier risk requests."


class ContractAuthoringAgent(BaseAgent):
    name = "contract-authoring-agent"
    description = "Handles contract authoring requests"
    capabilities = ("authoring",)

    def can_handle(self, request: str) -> bool:
        return "author" in request.lower() or "draft" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review authoring request", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Contract authoring agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles contract authoring requests."


class ContractRiskAgent(BaseAgent):
    name = "contract-risk-agent"
    description = "Handles contract risk requests"
    capabilities = ("risk",)

    def can_handle(self, request: str) -> bool:
        return "risk" in request.lower() and "contract" in request.lower()

    async def plan(self, *, request: str, context: AgentContext) -> list[str]:
        return ["review contract risk context", "prepare response"]

    async def execute(self, *, request: str, context: AgentContext) -> AgentResponse:
        return AgentResponse(agent_name=self.name, success=True, message="Contract risk agent handled the request", data={"request": request}, plan=await self.plan(request=request, context=context), explanation=await self.explain(request=request, context=context))

    async def validate(self, *, request: str, context: AgentContext) -> bool:
        return True

    async def explain(self, *, request: str, context: AgentContext) -> str:
        return "This placeholder agent handles contract risk requests."
