"""LLM- and DB-grounded replacements for all twelve of the placeholder agents.

Each class keeps the exact `name`/`description`/`capabilities`/`can_handle`
behavior of its placeholder counterpart in `placeholder_agents.py` (so agent
selection order and routing in `AgentFactory.build` is unchanged), but
`execute()` now gathers real data via `app.agents.tools` and asks the
configured LLM provider to answer grounded in it, via `LLMBackedAgent`.

The first five (Procurement, Supplier, Contract, Sourcing, SpendAnalysis)
were grounded in an earlier pass. The remaining seven (Document, Knowledge,
Reporting, Receipt, SupplierRisk, ContractAuthoring, ContractRisk) are
grounded here -- `placeholder_agents.py` is kept only as the un-grounded
reference implementation / for tests that exercise the placeholder behavior
directly.
"""

from __future__ import annotations

from app.agents.llm_agent import LLMBackedAgent


class ProcurementAgent(LLMBackedAgent):
    name = "procurement-agent"
    description = "Handles procurement-related requests"
    capabilities = ("procurement",)
    tool_names = ("list_open_requisitions",)
    role_prompt = "You are a procurement operations assistant for S2PNexus. Help the user with purchase requisitions."

    def can_handle(self, request: str) -> bool:
        return "procurement" in request.lower() or "purchase" in request.lower()


class SupplierAgent(LLMBackedAgent):
    name = "supplier-agent"
    description = "Handles supplier requests"
    capabilities = ("supplier",)
    tool_names = ("search_suppliers",)
    role_prompt = "You are a supplier management assistant for S2PNexus. Help the user find and evaluate suppliers/vendors."

    def can_handle(self, request: str) -> bool:
        return "supplier" in request.lower() or "vendor" in request.lower()


class ContractAgent(LLMBackedAgent):
    name = "contract-agent"
    description = "Handles contract requests"
    capabilities = ("contract",)
    tool_names = ("list_expiring_contracts",)
    role_prompt = "You are a contract lifecycle assistant for S2PNexus. Help the user with contract status, renewals, and expirations."

    def can_handle(self, request: str) -> bool:
        return "contract" in request.lower()


class SourcingAgent(LLMBackedAgent):
    name = "sourcing-agent"
    description = "Handles sourcing requests"
    capabilities = ("sourcing",)
    tool_names = ("list_open_sourcing_events",)
    role_prompt = "You are a strategic sourcing assistant for S2PNexus. Help the user with RFI/RFP/RFQ/auction sourcing events."

    def can_handle(self, request: str) -> bool:
        return "sourcing" in request.lower() or "source" in request.lower()


class SpendAnalysisAgent(LLMBackedAgent):
    name = "spend-analysis-agent"
    description = "Handles spend analysis requests"
    capabilities = ("spend", "analysis")
    tool_names = ("get_spend_summary",)
    role_prompt = "You are a spend intelligence assistant for S2PNexus. Help the user understand spend, savings, and supplier concentration."

    def can_handle(self, request: str) -> bool:
        return "spend" in request.lower() or "analysis" in request.lower()


class DocumentAgent(LLMBackedAgent):
    name = "document-agent"
    description = "Handles document-related requests"
    capabilities = ("documents",)
    tool_names = ("list_recent_documents",)
    role_prompt = "You are a document management assistant for S2PNexus. Help the user find and understand stored documents and files."

    def can_handle(self, request: str) -> bool:
        return "document" in request.lower() or "file" in request.lower()


class KnowledgeAgent(LLMBackedAgent):
    name = "knowledge-agent"
    description = "Handles knowledge-base questions"
    capabilities = ("knowledge",)
    tool_names = ("search_metadata_objects",)
    role_prompt = "You are a knowledge-base assistant for S2PNexus. Help the user find object definitions and reference information in the system."

    def can_handle(self, request: str) -> bool:
        return "knowledge" in request.lower() or "faq" in request.lower()


class ReportingAgent(LLMBackedAgent):
    name = "reporting-agent"
    description = "Handles reporting requests"
    capabilities = ("report",)
    tool_names = ("get_operations_report",)
    role_prompt = "You are an operations reporting assistant for S2PNexus. Summarize supplier, contract, and approval status across the business."

    def can_handle(self, request: str) -> bool:
        return "report" in request.lower() or "summary" in request.lower()


class ReceiptAgent(LLMBackedAgent):
    name = "receipt-agent"
    description = "Handles receipt requests"
    capabilities = ("receipt",)
    tool_names = ("list_recent_receipts",)
    role_prompt = "You are a receiving and invoice-matching assistant for S2PNexus. Help the user review goods receipts and invoice match/duplicate status."

    def can_handle(self, request: str) -> bool:
        return "receipt" in request.lower() or "invoice" in request.lower()


class SupplierRiskAgent(LLMBackedAgent):
    name = "supplier-risk-agent"
    description = "Handles supplier risk requests"
    capabilities = ("risk",)
    tool_names = ("list_supplier_risk_flags",)
    role_prompt = "You are a supplier risk assistant for S2PNexus. Help the user understand which supplier registrations carry elevated risk scores."

    def can_handle(self, request: str) -> bool:
        return "risk" in request.lower() and "supplier" in request.lower()


class ContractAuthoringAgent(LLMBackedAgent):
    name = "contract-authoring-agent"
    description = "Handles contract authoring requests"
    capabilities = ("authoring",)
    tool_names = ("list_contract_templates",)
    role_prompt = "You are a contract authoring assistant for S2PNexus. Help the user pick a template and draft new contract language."

    def can_handle(self, request: str) -> bool:
        return "author" in request.lower() or "draft" in request.lower()


class ContractRiskAgent(LLMBackedAgent):
    name = "contract-risk-agent"
    description = "Handles contract risk requests"
    capabilities = ("risk",)
    tool_names = ("list_overdue_contract_obligations",)
    role_prompt = "You are a contract risk assistant for S2PNexus. Help the user understand overdue obligations and compliance exposure."

    def can_handle(self, request: str) -> bool:
        return "risk" in request.lower() and "contract" in request.lower()
