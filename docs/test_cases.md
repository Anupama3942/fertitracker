# FertiTracker - Comprehensive Test Suite & Verification Matrix

This document provides a complete registry of automated test cases implemented in the FertiTracker project (University of Vavuniya, TICT3153, ICT Expo 5.0).
All concurrency, row-locking, and transaction tests run against a live **PostgreSQL** instance to validate real database-level locking semantics (`SELECT FOR UPDATE`).

---

## 1. Test Execution Instructions

### Running the Entire Test Suite
```powershell
# Run all tests against PostgreSQL
.venv\Scripts\python manage.py test
```

### Running Specific Test Modules
```powershell
# 1. Accounts & Authentication tests (OTP, lockout, role enforcement)
.venv\Scripts\python manage.py test accounts

# 2. Inventory, Dispatches & Concurrency tests
.venv\Scripts\python manage.py test inventory

# 3. Distributions, QR, Two-Officer, and FEFO tests
.venv\Scripts\python manage.py test distributions
```

### Code Coverage Measurement
```powershell
# Install coverage.py (if not installed)
.venv\Scripts\pip install coverage

# Run tests under coverage measurement
.venv\Scripts\coverage run --source='.' manage.py test

# View terminal coverage report
.venv\Scripts\coverage report

# Generate interactive HTML report in htmlcov/
.venv\Scripts\coverage html
```

---

## 2. Test Cases Registry (36 Test Cases)

| ID | Module | Test Class | Test Name | Purpose & Business Rule Verified |
|---|---|---|---|---|
| **TC-01** | `accounts` | `AccountLockoutTests` | `test_successful_login_resets_failed_attempts` | Verifies successful login resets failed attempt counter to 0. |
| **TC-02** | `accounts` | `AccountLockoutTests` | `test_account_locked_after_5_failed_attempts` | Hardens brute-force defense: locks account for 15 minutes after 5 consecutive failed passwords. |
| **TC-03** | `accounts` | `AccountLockoutTests` | `test_locked_account_cannot_login_even_with_correct_password` | Prevents authentication while account is in lock period. |
| **TC-04** | `accounts` | `RoleAccessTests` | `test_farmer_cannot_access_asc_scanner` | Role-Based Access Control (RBAC): Farmer blocked from counter scanner with 403. |
| **TC-05** | `accounts` | `RoleAccessTests` | `test_farmer_cannot_access_warehouse_dispatches` | RBAC: Farmer blocked from warehouse dispatches. |
| **TC-06** | `accounts` | `RoleAccessTests` | `test_asc_officer_can_access_scanner` | ASC Officer can access QR scanning and token redemption. |
| **TC-07** | `accounts` | `RoleAccessTests` | `test_auditor_can_access_audit_logs_read_only` | Auditor has read-only access to immutable audit log records. |
| **TC-08** | `accounts` | `InternationalizationTests` | `test_sinhala_and_tamil_po_catalog_roundtrip` | Asserts `.mo` message catalogs round-trip Sinhala and Tamil Unicode text without garbling. |
| **TC-09** | `inventory` | `ReceivingAndReconciliationTests` | `test_dispatch_full_good_receiving` | Warehouse dispatch receiving: 50 bags dispatched = 50 good received. Stock increases by 50 bags. |
| **TC-10** | `inventory` | `ReceivingAndReconciliationTests` | `test_dispatch_damaged_and_missing_with_discrepancy` | Receiving with damaged/missing bags: only good bags added to usable stock; discrepancy record logged. |
| **TC-11** | `inventory` | `ReceivingAndReconciliationTests` | `test_discrepancy_requires_mandatory_justification_note` | FR-07: Mandatory explanation required when damaged/missing stock is reported. |
| **TC-12** | `inventory` | `ReceivingAndReconciliationTests` | `test_cannot_receive_more_than_dispatched` | Quantity validation: total received + damaged cannot exceed dispatched bags. |
| **TC-13** | `inventory` | `ReceivingAndReconciliationTests` | `test_cannot_receive_already_received_dispatch` | Prevents re-receiving already processed dispatches. |
| **TC-14** | `inventory` | `ReceivingAndReconciliationTests` | `test_asc_officer_cannot_receive_dispatch_for_other_asc` | Multi-tenancy check: officer cannot process stock belonging to another ASC centre. |
| **TC-15** | `inventory` | `DispatchConcurrencyTransactionTests` | `test_concurrent_dispatch_receiving_prevented` | **PostgreSQL Concurrency**: 2 simultaneous threads attempt to receive the same dispatch; `select_for_update` row lock allows exactly 1 and prevents double-counting. |
| **TC-16** | `distributions` | `QRDistributionWorkflowTests` | `test_token_generation_and_expiry` | Farmer dynamic QR token generation; expires after 60 seconds. |
| **TC-17** | `distributions` | `QRDistributionWorkflowTests` | `test_token_verification_does_not_redeem` | Scan -> Verify step does NOT modify stock or quota before confirmation. |
| **TC-18** | `distributions` | `QRDistributionWorkflowTests` | `test_token_cannot_be_redeemed_twice` | One-time token redemption: subsequent attempts rejected with error. |
| **TC-19** | `distributions` | `QRDistributionWorkflowTests` | `test_expired_token_rejected` | Expired tokens are rejected and cannot issue fertilizer. |
| **TC-20** | `distributions` | `QRDistributionWorkflowTests` | `test_cannot_issue_more_than_remaining_quota` | Farmer quota enforcement: issue quantity cannot exceed remaining kg. |
| **TC-21** | `distributions` | `QRDistributionWorkflowTests` | `test_cannot_issue_without_active_season` | Season locking: fertilizer issuance blocked when season is closed. |
| **TC-22** | `distributions` | `SMSBackupCodeTests` | `test_sms_backup_code_hmac_hashing` | Keypad phone backup: 6-digit code stored using keyed HMAC-SHA256, never plaintext. |
| **TC-23** | `distributions` | `SMSBackupCodeTests` | `test_sms_backup_code_success_redemption` | Valid 6-digit code issued successfully at counter counter. |
| **TC-24** | `distributions` | `SMSBackupCodeTests` | `test_code_bound_to_specific_asc` | ASC Binding: code issued for Vavuniya South cannot be redeemed at Cheddikulam. |
| **TC-25** | `distributions` | `SMSBackupCodeTests` | `test_code_brute_force_officer_lockout_after_5_attempts` | Brute-force protection: locks manual entry for 10 minutes after 5 wrong code attempts. |
| **TC-26** | `distributions` | `SMSBackupCodeTests` | `test_token_invalidated_after_5_wrong_attempts` | Token invalidation: destroys token if 5 incorrect codes are tested against it. |
| **TC-27** | `distributions` | `OfficerAssistedIssueTests` | `test_assisted_issue_creation_and_mandatory_reason_note` | Officer-Assisted Issue: 'OTHER' reason requires a mandatory explanatory note. |
| **TC-28** | `distributions` | `OfficerAssistedIssueTests` | `test_two_officer_rule_requester_cannot_approve_own_request` | **Two-Officer Rule**: Counter officer CANNOT approve their own assisted request. |
| **TC-29** | `distributions` | `OfficerAssistedIssueTests` | `test_non_head_officer_cannot_approve` | Two-Officer Rule: Only authorized ASC Head (`is_asc_head=True`) can approve requests. |
| **TC-30** | `distributions` | `OfficerAssistedIssueTests` | `test_assisted_issue_approval_and_execution` | Complete assisted issue cycle: request -> head approval -> counter issue -> receipt. |
| **TC-31** | `distributions` | `OfficerAssistedIssueTests` | `test_assisted_issue_expiry_after_30_minutes` | Assisted approvals expire after 30 minutes if not redeemed at the counter. |
| **TC-32** | `distributions` | `ConcurrencyRowLockingTransactionTests` | `test_concurrent_token_double_redemption_prevented` | **PostgreSQL Concurrency**: 2 simultaneous threads redeem the same token; `select_for_update` prevents double issue and over-quota deductions. |
| **TC-33** | `distributions` | `FEFOExpiryAndWriteOffTests` | `test_fefo_multi_batch_split_and_expired_batch_skip` | **FEFO Multi-Batch Split**: Issues from earliest expiry date first, splits across batches when 1 batch is insufficient, and skips expired batches. |
| **TC-34** | `distributions` | `FEFOExpiryAndWriteOffTests` | `test_cannot_issue_from_expired_stock_when_no_fresh_stock` | Strict safety: expired batches are blocked from issuance even when zero fresh stock remains. |
| **TC-35** | `distributions` | `FEFOExpiryAndWriteOffTests` | `test_expired_stock_write_off_by_asc_head` | **Expired Stock Write-Off**: ASC Head write-off creates append-only `WRITE_OFF` `StockMovement` and `AuditLog` (no destructive deletion). |
| **TC-36** | `distributions` | `FEFOExpiryAndWriteOffTests` | `test_seed_demo_data_command_execution` | Validates `python manage.py seed_demo_data` executes idempotently and seeds realistic Sri Lankan master records. |

---

## 3. Database Concurrency & Locking Verification

Unlike SQLite (which ignores `select_for_update()` row locks), our automated test suite connects to **PostgreSQL**.
- Tests `TC-15` and `TC-32` spawn real Python threads using `django.test.TransactionTestCase` with distinct database connections.
- This guarantees:
  1. No two counter officers can redeem the same QR token or 6-digit SMS code simultaneously.
  2. No warehouse dispatch can be double-received.
  3. No farmer quota can drop below 0 kg under concurrent counter requests.
