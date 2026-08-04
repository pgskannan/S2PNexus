"""S2PNexus Models Package.

All models are imported here to ensure they are registered with SQLAlchemy's metadata.
"""

from app.models.user import User  # noqa: F401
from app.models.supplier import Supplier  # noqa: F401
from app.models.supplier_address import SupplierAddress  # noqa: F401
from app.models.supplier_bank_account import SupplierBankAccount  # noqa: F401
from app.models.supplier_request import SupplierRequest  # noqa: F401
from app.models.supplier_registration import SupplierRegistration  # noqa: F401
from app.models.contract import Contract  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.chat_session import ChatSession  # noqa: F401
from app.models.chat_message import ChatMessage  # noqa: F401
from app.models.embedding import Embedding  # noqa: F401
from app.models.procurement import (  # noqa: F401
    ProcurementInvoice,
    ProcurementRequisition,
    ProcurementRequisitionVersion,
    PurchaseOrder,
    GoodsReceipt,
    PurchaseOrderLineItem,
)
from app.models.sourcing import (  # noqa: F401
    SourcingEvent,
    SourcingEventLineItem,
    SourcingEventInvitation,
    SourcingEventResponse,
)
from app.models.contract_lifecycle import (  # noqa: F401
    ContractClause,
    ContractClauseLink,
    ContractTemplate,
    ContractObligation,
    ContractRenewal,
)
from app.models.spend import SavingsRecord  # noqa: F401
from app.models.workflow import (  # noqa: F401
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowTask,
    Notification,
)
from app.models.system_setting import SystemSetting  # noqa: F401
from app.models.email_template import EmailTemplateOverride  # noqa: F401
from app.models.catalog_item import CatalogItem  # noqa: F401
from app.models.agent_activity import AgentActivityLog  # noqa: F401
from app.models.document_numbering import DocumentNumberingFormat, DocumentNumberingSequence  # noqa: F401
from app.models.commodity import CommodityCode, CommodityAccountMapping, CommodityMatchingPolicy  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.gl_account import GLAccount  # noqa: F401
from app.models.address import Address  # noqa: F401
from app.models.accounting_split import LineItemAccountingSplit, Budget  # noqa: F401
from app.models.approval import ApproverSeed, ApprovalEvent, SlaDefinition, SlaMetric  # noqa: F401
from app.models.act_as import ActAsSession  # noqa: F401
from app.models.supplier_qualification import SupplierQualification  # noqa: F401
from app.models.preferred_supplier import PreferredSupplierStatus  # noqa: F401
from app.models.supplier_type import SupplierType  # noqa: F401
from app.models.supplier_audit import SupplierAuditEvent  # noqa: F401
from app.models.template import (  # noqa: F401
    TemplateDefinition,
    TemplateSection,
    TemplateQuestion,
    TemplateResponse,
)
from app.metadata_engine.models import (
    MetadataAuditEvent,
    MetadataField,
    MetadataFieldType,
    MetadataLayout,
    MetadataObject,
    MetadataValue,
)  # noqa: F401

__all__ = [
    "User",
    "Supplier",
    "SupplierAddress",
    "SupplierBankAccount",
    "SupplierRequest",
    "SupplierRegistration",
    "Contract",
    "Document",
    "ChatSession",
    "ChatMessage",
    "Embedding",
    "ProcurementRequisition",
    "PurchaseOrder",
    "GoodsReceipt",
    "ProcurementInvoice",
    "SourcingEvent",
    "SourcingEventLineItem",
    "SourcingEventInvitation",
    "SourcingEventResponse",
    "ContractClause",
    "ContractClauseLink",
    "ContractTemplate",
    "ContractObligation",
    "ContractRenewal",
    "SavingsRecord",
    "WorkflowDefinition",
    "WorkflowInstance",
    "WorkflowTask",
    "Notification",
    "AgentActivityLog",
    "DocumentNumberingFormat",
    "DocumentNumberingSequence",
    "CommodityCode",
    "CommodityAccountMapping",
    "CommodityMatchingPolicy",
    "Category",
    "GLAccount",
    "Address",
    "PurchaseOrderLineItem",
    "LineItemAccountingSplit",
    "Budget",
    "ActAsSession",
    "SupplierQualification",
    "PreferredSupplierStatus",
    "SupplierType",
    "SupplierAuditEvent",
    "TemplateDefinition",
    "TemplateSection",
    "TemplateQuestion",
    "TemplateResponse",
]