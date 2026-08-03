# S2PNexus Supplier Request & Registration – Functional Specification

(Including Excel-Based Registration Specification)

Consolidated FS covering the Excel Template Specification, Excel Column Definitions, Excel Validation Rules, and Import Engine Technical Specification. Pasted into the repo 2026-08-03 as the source of truth for the Supplier Type / Excel-registration feature; not yet built. See the "Cross-check against existing code" note at the bottom before scoping implementation work.

## 1. Purpose

Define a metadata-driven Supplier Request & Registration framework that:

- Eliminates SAP Ariba SLP pain points
- Uses Supplier Type to drive workflow behavior
- Supports Excel-based supplier registration (no portal yet)
- Allows SLP Admin to import supplier registration Excel
- Supports ad-hoc tasks, notifications, dynamic questionnaires, scoring, qualification, preferred supplier logic

## 2. Scope

**In Scope**

- Supplier Request
- Supplier Type configuration
- Excel-based Supplier Registration
- Questionnaire metadata
- Scoring & grading
- Ad-hoc tasks
- Notifications
- Qualification & preferred supplier logic
- Import engine for Excel responses

**Out of Scope**

- Supplier portal
- Downstream P2P processes
- External risk/compliance systems (only integration points)

## 3. Roles

- Supplier Request Creator
- SLP Admin
- Approvers
- Supplier User

Only Creator and SLP Admin can trigger Manual Registration.

## 4. Supplier Type Model

Each Supplier Type defines:

- SupplierTypeCode
- SupplierTypeName
- RegistrationMode (AUTO / MANUAL / NONE)
- RegistrationMethod (EXCEL_ONLY)
- RequiredQuestionnaireModules
- QualificationRules
- PreferredSupplierRules
- AdHocTaskTemplates
- NotificationRules
- ApprovalWorkflowConfig

## 5. Supplier Request Specification

### 5.1 Data Model

- RequestID
- SupplierName
- SupplierTypeCode
- RequesterID
- BusinessUnit
- SpendCategory
- Country
- EstimatedAnnualSpend
- RiskLevel
- RequiredQuestionnaireModules
- RequiredApprovals
- AdHocTasks
- Attachments
- Comments
- Status

### 5.2 Lifecycle

- Draft
- Validation
- Submission
- Approval
- Supplier Creation
- Registration Trigger
- Qualification
- Preferred Supplier Evaluation
- Completed

## 6. Registration Trigger Logic

**AUTO** — Supplier created → Excel sent automatically.

**MANUAL** — Supplier created → Registration must be triggered by:

- Supplier Request Creator
- SLP Admin

**NONE** — Supplier created → No registration.

## 7. Supplier Registration (Excel Mode)

Registration is completed using a locked Excel workbook.

## 8. Questionnaire Framework

Each question has:

- QuestionID
- ModuleID
- QuestionText
- QuestionType
- VisibilityRules
- MandatoryRules
- EditabilityRules
- ScoringRules
- RiskImpact
- QualificationImpact
- PreferredSupplierImpact

## 9. Scoring & Grading

`TotalScore = Σ(question score × weight × module weight)`

Grades:

- A = 90–100
- B = 75–89
- C = 50–74
- D < 50

## 10. Ad-Hoc Tasks

Task Types:

- Approval
- Notification
- Clarification
- Risk Review
- Legal Review
- Compliance Review
- Finance Review
- Category Manager Review

## 11. Notifications

Events:

- Request submitted
- Request approved/rejected
- Supplier created
- Registration pending
- Registration invitation sent
- Registration SLA alerts
- Registration completed
- Qualification completed

## 12. Qualification & Preferred Supplier

Qualification based on:

- Score
- Mandatory questions
- Risk flags

Preferred Supplier:

- Grade A
- No compliance flags
- Category Manager approval

## 13. Excel Template Specification

This section defines the Excel file sent to suppliers.

### 13.1 Excel File Structure

**Sheet 1: Instructions**

- How to fill
- Mandatory fields
- Allowed formats
- Contact details
- TemplateVersion
- QuestionnaireVersion

**Sheet 2: Supplier Information**

Columns:

- SupplierID (locked)
- SupplierType (locked)
- LegalName (editable)
- Address (editable)
- Country (editable)
- TaxID (editable)
- BankAccountNumber (editable)
- BankRoutingNumber (editable)
- ContactName (editable)
- ContactEmail (editable)
- TemplateVersion (locked)

**Sheet 3+: Questionnaire Modules**

Each module is a separate sheet.

Columns:

- QuestionID (hidden)
- ModuleID (hidden)
- QuestionText
- Response (editable)
- AllowedValues (dropdown)
- MandatoryFlag
- ScoreFormula (locked)
- Comments (optional)

## 14. Excel Column Definitions

**Supplier Information Sheet**

```
Column A: SupplierID (Locked)
Column B: SupplierType (Locked)
Column C: LegalName (Editable)
Column D: Address (Editable)
Column E: Country (Editable dropdown)
Column F: TaxID (Editable)
Column G: BankAccountNumber (Editable)
Column H: BankRoutingNumber (Editable)
Column I: ContactName (Editable)
Column J: ContactEmail (Editable, email format)
Column K: TemplateVersion (Locked)
```

**Questionnaire Sheet**

```
Column A: QuestionID (Hidden)
Column B: ModuleID (Hidden)
Column C: QuestionText (Locked)
Column D: Response (Editable)
Column E: AllowedValues (Dropdown)
Column F: MandatoryFlag (Locked)
Column G: ScoreFormula (Locked)
Column H: Comments (Editable)
```

## 15. Excel Validation Rules

### 15.1 Structural Validation

- TemplateVersion must match system version
- QuestionnaireVersion must match system version
- No added or removed sheets
- No added or removed columns
- No unlocked protected cells
- Hidden columns must remain hidden
- Hash signature must match

### 15.2 Field Validation

- Mandatory fields must be filled
- Dropdown values must match allowed list
- Email format validation
- Numeric fields must be numeric
- Bank details must match regex patterns
- Country must be valid ISO code
- No formula tampering allowed

### 15.3 Response Validation

- Response must match QuestionType
- Attachment references must be valid (if used)
- Scoring formulas must remain intact

### 15.4 Error Handling

System generates:

- ErrorReport.xlsx
- ImportSummary.txt

## 16. Import Engine Technical Specification

### 16.1 Import Modes

- Single Supplier Import
- Bulk Import (multiple Excel files)

### 16.2 Import Workflow

1. Admin uploads Excel
2. System validates structure
3. System validates fields
4. System extracts:
   - Supplier Information
   - Questionnaire Responses
5. System maps:
   - QuestionID → Response
   - ModuleID → Score
6. System calculates:
   - ScorePerQuestion
   - ScorePerModule
   - TotalScore
   - Grade
7. System updates:
   - RegistrationStatus
   - QualificationStatus
   - PreferredSupplierFlag
8. System logs:
   - Import timestamp
   - Imported by
   - Errors
   - Overrides

### 16.3 Import Engine Components

- Excel Parser
- Template Validator
- Questionnaire Mapper
- Scoring Engine
- Qualification Engine
- Audit Logger

### 16.4 Error Categories

- Structural errors
- Version mismatch
- Mandatory missing
- Invalid dropdown value
- Invalid format
- Tampered locked cell
- Unknown QuestionID
- Unknown ModuleID

### 16.5 Output

- ImportSummary
- ErrorReport
- Updated Supplier Registration Record

## 17. Supplier Type Configuration Matrix

(To be added — reference the matrix from the originating conversation if it needs to be captured here.)
