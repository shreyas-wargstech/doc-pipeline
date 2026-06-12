# Retrieval Data Model

## Philosophy

Store only information necessary to retrieve documents.

The system is a document retrieval platform.

## Page Representation

Required:

- page_id
- page_type
- page_summary
- keywords
- entities

## Document Representation

Required:

- document_id
- document_type
- document_summary
- entities
- relationships

## Entity Types

- Practitioner
- Organization
- Vendor
- Government Body
- Educational Institute
- Hospital

## Graph Relationships

Practitioner -> appears_in -> Document
Organization -> issues -> Document
Vendor -> mentioned_in -> Document
GovernmentBody -> publishes -> Document
