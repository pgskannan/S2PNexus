# WF-011 – Event Bus & Messaging Architecture

**Document ID:** WF-011

**Title:** Event Bus & Messaging Architecture

**Version:** 1.0

**Status:** Draft

**Owner:** S2PNexus Architecture Team

---

# 1. Purpose

The Event Bus provides asynchronous communication between platform services.

Instead of tightly coupling services through direct API calls, services publish and subscribe to events, enabling scalability, resilience, and extensibility.

The Event Bus is the communication backbone of S2PNexus.

---

# 2. Design Goals

The Event Bus shall be

- Event Driven
- Asynchronous
- Reliable
- Scalable
- Observable
- Idempotent
- Secure
- Multi-Tenant
- Cloud Native

---

# 3. High-Level Architecture

```
                   +----------------------+
                   | Workflow Runtime     |
                   +----------+-----------+
                              |
                     Publish Domain Events
                              |
                              ▼
                  +-------------------------+
                  | Event Bus               |
                  | Kafka / RabbitMQ / NATS |
                  +-------------------------+
            _________|_______|________|_________
           |         |       |        |         |
           ▼         ▼       ▼        ▼         ▼
     Action     AI Engine  Analytics Notification ERP Adapter
     Engine
           |
           ▼
      External Systems
```

---

# 4. Event Categories

| Category | Examples |
|-----------|----------|
| Workflow Events | Started, Completed |
| Task Events | Assigned, Escalated |
| Approval Events | Approved, Rejected |
| Supplier Events | Registered, Qualified |
| Procurement Events | PR Created, PO Issued |
| Contract Events | Signed, Renewed |
| AI Events | Recommendation Generated |
| Notification Events | Email Sent |
| Integration Events | ERP Updated |
| Audit Events | Policy Applied |

---

# 5. Event Model

Every event contains

| Field | Description |
|---------|-------------|
| Event ID | UUID |
| Event Type | Domain Event |
| Event Version | Semantic Version |
| Event Time | UTC Timestamp |
| Tenant ID | Tenant Context |
| Correlation ID | End-to-End Trace |
| Causation ID | Parent Event |
| Source Service | Publisher |
| Payload | Business Data |

---

# 6. Event Lifecycle

```
Business Action
      │
      ▼
Create Event
      │
      ▼
Validate Schema
      │
      ▼
Publish
      │
      ▼
Persist (Outbox)
      │
      ▼
Consumers Receive
      │
      ▼
Acknowledge
```

---

# 7. Event Types

### Domain Events

Represent business facts.

Examples

- PurchaseRequisitionCreated
- PurchaseOrderApproved
- SupplierQualified
- ContractExecuted

---

### Integration Events

Shared with external systems.

Examples

- ERPPOCreated
- InvoicePosted
- VendorSynced

---

### System Events

Platform operations.

Examples

- UserLoggedIn
- CacheRefreshed
- SchedulerStarted

---

# 8. Delivery Guarantees

Supported modes

- At Most Once
- At Least Once
- Exactly Once (where supported)

Default

```
At Least Once
```

Consumers must implement idempotency.

---

# 9. Outbox Pattern

To ensure consistency between database commits and event publication:

```
Business Transaction
        │
        ▼
Database Commit
        │
        ▼
Outbox Table
        │
        ▼
Publisher
        │
        ▼
Event Bus
```

Benefits

- No lost events
- Transaction consistency
- Retry support

---

# 10. Inbox Pattern

Consumers maintain an Inbox table.

Purpose

- Prevent duplicate processing
- Track message status
- Support replay

---

# 11. Message Routing

Routing options

- Topic
- Queue
- Fan-out
- Direct
- Header-based

Example

```
workflow.*

approval.*

supplier.*

contract.*
```

---

# 12. Dead Letter Queue (DLQ)

Messages move to the DLQ after configurable retry failures.

DLQ capabilities

- Inspection
- Replay
- Manual correction
- Metrics

---

# 13. Retry Strategy

Retry policies

- Immediate
- Fixed Delay
- Exponential Backoff
- Circuit Breaker
- Poison Message Detection

---

# 14. Event Versioning

Rules

- Events are immutable
- Additive changes preferred
- Breaking changes require new version
- Consumers support multiple versions during transition

---

# 15. Event Schema Registry

All event schemas are centrally managed.

Schema includes

- Event Name
- Version
- Payload Definition
- Required Fields
- Compatibility Rules
- Documentation

Supported formats

- JSON Schema
- Avro
- Protobuf

---

# 16. Idempotency

Every consumer must support idempotent processing.

Idempotency key

```
Event ID
+
Consumer ID
```

Duplicate events are ignored after successful processing.

---

# 17. Event Replay

Replay supports

- Single Event
- Time Range
- Topic Replay
- Consumer Replay
- Tenant Replay

Replay is controlled by authorization policies.

---

# 18. Security

The Event Bus enforces

- Tenant isolation
- Event encryption
- Message signing
- RBAC
- Service authentication
- Sensitive field masking

---

# 19. Observability

Collected metrics

- Publish latency
- Consumer latency
- Queue depth
- Retry count
- DLQ count
- Throughput
- Error rate

Tracing

- Correlation ID
- Causation ID
- Distributed tracing (OpenTelemetry)

---

# 20. Performance Targets

| Metric | Target |
|---------|--------|
| Publish Latency | <20 ms |
| Consumer Dispatch | <30 ms |
| End-to-End Delivery | <200 ms |
| Replay Start | <5 seconds |
| Schema Validation | <10 ms |

---

# 21. Disaster Recovery

Supports

- Persistent queues
- Multi-node clusters
- Cross-region replication
- Replay from Outbox
- DLQ recovery

---

# 22. Future Enhancements

- Event sourcing
- CQRS integration
- Streaming analytics
- AI-driven anomaly detection
- Multi-cloud messaging
- Event marketplace

---

# 23. Implementation Checklist

- Event Publisher
- Event Consumer SDK
- Outbox Service
- Inbox Service
- Schema Registry
- DLQ Manager
- Replay Service
- Metrics
- OpenTelemetry
- REST APIs
- Unit Tests
- Integration Tests

---

# 24. Definition of Done

The Event Bus is complete when

- Events are published reliably.
- Outbox pattern is implemented.
- Consumers are idempotent.
- DLQ supports replay.
- Schema registry is operational.
- Distributed tracing is enabled.
- Tenant isolation is enforced.
- Test coverage exceeds 90%.