# FertiTracker - Comprehensive Test Suite & Verification Matrix

This document provides a complete registry of automated test cases implemented in the FertiTracker project (University of Vavuniya, TICT3153, ICT Expo 5.0).
All concurrency, row-locking, and transaction tests run against a live **PostgreSQL** instance to validate real database-level locking semantics (`SELECT FOR UPDATE`).

---

## 1. Test Execution Instructions

### Running the Entire Test Suite
```powershell
# Run all 60 tests against PostgreSQL
.venv\Scripts\python manage.py test
```

### Running Specific Test Modules
```powershell
# 1. Accounts & Authentication tests (OTP rate limits, forced password change, lockout, RBAC, single open season)
.venv\Scripts\python manage.py test accounts.tests

# 2. Inventory, Dispatches & Concurrency tests
.venv\Scripts\python manage.py test inventory.tests

# 3. Distributions, QR, Two-Officer, FEFO, AuditLog immutability, CSV preview, and Boundary tests
.venv\Scripts\python manage.py test distributions.tests
```

### Code Coverage Measurement
```powershell
# Run tests under coverage measurement
.venv\Scripts\coverage run --source='.' manage.py test

# View terminal coverage report
.venv\Scripts\coverage report

# Generate interactive HTML report in htmlcov/
.venv\Scripts\coverage html
```

---

## 2. Test Cases Registry (60 Test Cases)

| ID | Module | Test Class | Test Name | Purpose & Business Rule Verified | Status |
|---|---|---|---|---|---|
| **TC-01** | `accounts` | `InternationalizationTests` | `test_set_language_to_sinhala` | Switches session and cookie to Sinhala (`si`) via standard POST. | PASS |
| **TC-02** | `accounts` | `InternationalizationTests` | `test_set_language_to_tamil` | Switches session and cookie to Tamil (`ta`) via standard POST. | PASS |
| **TC-03** | `accounts` | `AccountSecurityTests` | `test_login_page_renders_with_accessibility` | Login page renders HTTP 200 with required form fields. | PASS |
| **TC-04** | `accounts` | `AccountSecurityTests` | `test_account_lockout_after_failed_attempts` | Checks account lockout flag after failed password attempts. | PASS |
| **TC-05** | `accounts` | `AccountSecurityTests` | `test_forced_password_change_flow` | `must_change_password=True` redirects officer to force password change; enforces Django password validator. | PASS |
| **TC-06** | `accounts` | `AccountSecurityTests` | `test_deactivated_user_blocked_from_login` | Deactivated officer account (`is_active=False`) is blocked from login with friendly translated error. | PASS |
| **TC-07** | `accounts` | `AccountSecurityTests` | `test_inactive_account_blocked_from_login` | Farmer account with `is_account_active=False` cannot log in and is redirected to OTP activation. | PASS |
| **TC-08** | `accounts` | `FarmerActivationOTPTests` | `test_generic_response_for_unknown_nic` | Generic response returned whether NIC exists or not to prevent user enumeration attacks. | PASS |
| **TC-09** | `accounts` | `FarmerActivationOTPTests` | `test_otp_rate_limiting_and_60s_cooldown` | Rate limits OTP generation: enforces 60s cooldown between requests and max 3 requests per hour. | PASS |
| **TC-10** | `accounts` | `FarmerActivationOTPTests` | `test_otp_lock_after_5_failed_attempts` | Inactivates and locks OTP after 5 consecutive incorrect code entries. | PASS |
| **TC-11** | `accounts` | `AdminOfficerManagementTests` | `test_non_admin_forbidden_from_officer_management` | RBAC: Non-admin users receive HTTP 403 when accessing officer management. | PASS |
| **TC-12** | `accounts` | `AdminOfficerManagementTests` | `test_admin_creates_officer_with_temp_password` | Admin creates officer with random 12-char temp password and `must_change_password=True`. | PASS |
| **TC-13** | `accounts` | `AdminOfficerManagementTests` | `test_admin_toggles_officer_status` | Admin deactivates and reactivates officers without deleting records (audit integrity). | PASS |
| **TC-14** | `accounts` | `SeasonInvariantTests` | `test_single_active_season_invariant` | Activating Season 2 automatically switches Season 1 to `CLOSED` (only 1 OPEN season invariant). | PASS |
| **TC-15** | `inventory` | `ReceivingAndReconciliationTests` | `test_dispatch_full_good_receiving` | Warehouse dispatch receiving: 50 bags dispatched = 50 good received. Usable stock increases. | PASS |
| **TC-16** | `inventory` | `ReceivingAndReconciliationTests` | `test_dispatch_damaged_and_missing_with_discrepancy` | Receiving with damaged/missing bags: only good bags added to stock; discrepancy record logged. | PASS |
| **TC-17** | `inventory` | `ReceivingAndReconciliationTests` | `test_discrepancy_requires_mandatory_justification_note` | Mandatory explanation required when damaged/missing stock is reported. | PASS |
| **TC-18** | `inventory` | `ReceivingAndReconciliationTests` | `test_cannot_receive_more_than_dispatched` | Quantity check: total received + damaged cannot exceed dispatched bags. | PASS |
| **TC-19** | `inventory` | `ReceivingAndReconciliationTests` | `test_cannot_receive_already_received_dispatch` | Prevents re-receiving already processed dispatches. | PASS |
| **TC-20** | `inventory` | `ReceivingAndReconciliationTests` | `test_asc_officer_cannot_receive_dispatch_for_other_asc` | Multi-tenancy check: officer cannot process stock belonging to another ASC centre. | PASS |
| **TC-21** | `inventory` | `DispatchConcurrencyTransactionTests` | `test_concurrent_dispatch_receiving_prevented` | **PostgreSQL Concurrency**: 2 simultaneous threads attempt to receive the same dispatch; `select_for_update` row lock allows exactly 1 and prevents double-counting. | PASS |
| **TC-22** | `distributions` | `QRDistributionWorkflowTests` | `test_token_generation_and_expiry` | Farmer dynamic QR token generation; expires after 60 seconds. | PASS |
| **TC-23** | `distributions` | `QRDistributionWorkflowTests` | `test_token_verification_does_not_redeem` | Scan -> Verify step does NOT modify stock or quota before confirmation. | PASS |
| **TC-24** | `distributions` | `QRDistributionWorkflowTests` | `test_token_cannot_be_redeemed_twice` | One-time token redemption: subsequent attempts rejected with error. | PASS |
| **TC-25** | `distributions` | `QRDistributionWorkflowTests` | `test_expired_token_rejected` | Expired tokens are rejected and cannot issue fertilizer. | PASS |
| **TC-26** | `distributions` | `QRDistributionWorkflowTests` | `test_cannot_issue_more_than_remaining_quota` | Farmer quota enforcement: issue quantity cannot exceed remaining kg. | PASS |
| **TC-27** | `distributions` | `QRDistributionWorkflowTests` | `test_cannot_issue_without_active_season` | Season locking: fertilizer issuance blocked when season is closed. | PASS |
| **TC-28** | `distributions` | `SMSBackupCodeTests` | `test_sms_backup_code_hmac_hashing` | Keypad phone backup: 6-digit code stored using keyed HMAC-SHA256, never plaintext. | PASS |
| **TC-29** | `distributions` | `SMSBackupCodeTests` | `test_sms_backup_code_success_redemption` | Valid 6-digit code issued successfully at counter. | PASS |
| **TC-30** | `distributions` | `SMSBackupCodeTests` | `test_code_bound_to_specific_asc` | ASC Binding: code issued for Vavuniya South cannot be redeemed at Cheddikulam. | PASS |
| **TC-31** | `distributions` | `SMSBackupCodeTests` | `test_code_brute_force_officer_lockout_after_5_attempts` | Brute-force protection: locks manual entry for 10 minutes after 5 wrong code attempts. | PASS |
| **TC-32** | `distributions` | `SMSBackupCodeTests` | `test_token_invalidated_after_5_wrong_attempts` | Token invalidation: destroys token if 5 incorrect codes are tested against it. | PASS |
| **TC-33** | `distributions` | `OfficerAssistedIssueTests` | `test_assisted_issue_creation_and_mandatory_reason_note` | Officer-Assisted Issue: 'OTHER' reason requires a mandatory explanatory note. | PASS |
| **TC-34** | `distributions` | `OfficerAssistedIssueTests` | `test_two_officer_rule_requester_cannot_approve_own_request` | **Two-Officer Rule**: Counter officer CANNOT approve their own assisted request. | PASS |
| **TC-35** | `distributions` | `OfficerAssistedIssueTests` | `test_non_head_officer_cannot_approve` | Two-Officer Rule: Only authorized ASC Head (`is_asc_head=True`) can approve requests. | PASS |
| **TC-36** | `distributions` | `OfficerAssistedIssueTests` | `test_assisted_issue_approval_and_execution` | Complete assisted issue cycle: request -> head approval -> counter issue -> receipt. | PASS |
| **TC-37** | `distributions` | `OfficerAssistedIssueTests` | `test_assisted_issue_expiry_after_30_minutes` | Assisted approvals expire after 30 minutes if not redeemed at the counter. | PASS |
| **TC-38** | `distributions` | `ConcurrencyRowLockingTransactionTests` | `test_concurrent_token_double_redemption_prevented` | **PostgreSQL Concurrency**: 2 simultaneous threads redeem the same token; `select_for_update` prevents double issue and over-quota deductions. | PASS |
| **TC-39** | `distributions` | `FEFOExpiryAndWriteOffTests` | `test_fefo_multi_batch_split_and_expired_batch_skip` | **FEFO Multi-Batch Split**: Issues from earliest expiry date first, splits across batches when 1 batch is insufficient, and skips expired batches. | PASS |
| **TC-40** | `distributions` | `FEFOExpiryAndWriteOffTests` | `test_cannot_issue_from_expired_stock_when_no_fresh_stock` | Strict safety: expired batches are blocked from issuance even when zero fresh stock remains. | PASS |
| **TC-41** | `distributions` | `FEFOExpiryAndWriteOffTests` | `test_expired_stock_write_off_by_asc_head` | **Expired Stock Write-Off**: ASC Head write-off creates append-only `WRITE_OFF` `StockMovement` and `AuditLog` (no destructive deletion). | PASS |
| **TC-42** | `distributions` | `FEFOExpiryAndWriteOffTests` | `test_seed_demo_data_command_execution` | Validates `python manage.py seed_demo_data --force` executes idempotently and seeds realistic master records. | PASS |
| **TC-43** | `distributions` | `AuditLogImmutabilityTests` | `test_audit_log_instance_cannot_be_modified` | Attempting to call `log.save()` on an existing AuditLog record raises `ValidationError`. | PASS |
| **TC-44** | `distributions` | `AuditLogImmutabilityTests` | `test_audit_log_instance_cannot_be_deleted` | Attempting to call `log.delete()` raises `ValidationError`. | PASS |
| **TC-45** | `distributions` | `AuditLogImmutabilityTests` | `test_audit_log_queryset_bulk_delete_blocked` | Attempting `AuditLog.objects.filter(...).delete()` raises `ValidationError`. | PASS |
| **TC-46** | `distributions` | `AuditLogImmutabilityTests` | `test_audit_log_queryset_bulk_update_blocked` | Attempting `AuditLog.objects.filter(...).update(...)` raises `ValidationError`. | PASS |
| **TC-47** | `distributions` | `FarmerRegistrationAndPhoneSecurityTests` | `test_registration_with_invalid_nic_fails` | Rejects non-compliant NIC numbers (e.g. `12345`). | PASS |
| **TC-48** | `distributions` | `FarmerRegistrationAndPhoneSecurityTests` | `test_registration_with_valid_nic_starts_inactive` | Valid Sri Lankan NIC creates farmer profile with `is_account_active=False` (starts INACTIVE). | PASS |
| **TC-49** | `distributions` | `FarmerRegistrationAndPhoneSecurityTests` | `test_phone_update_requires_in_person_verification` | Phone update is blocked without confirming "I verified the original NIC in person". | PASS |
| **TC-50** | `distributions` | `FarmerRegistrationAndPhoneSecurityTests` | `test_phone_update_with_verification_masks_audit_log` | Phone update saves new number and masks both old (`077****233`) and new (`071****677`) numbers in AuditLog. | PASS |
| **TC-51** | `distributions` | `EntitlementManagementAndCSVPreviewTests` | `test_sample_csv_download_has_utf8_bom` | Sample CSV download endpoint responds with UTF-8 BOM (`\ufeff`) and `nic,product,quantity_kg`. | PASS |
| **TC-52** | `distributions` | `EntitlementManagementAndCSVPreviewTests` | `test_edit_entitlement_audits_old_and_new_values` | Editing quota from 50kg to 80kg records both old and new approved/remaining kg in AuditLog. | PASS |
| **TC-53** | `distributions` | `EntitlementManagementAndCSVPreviewTests` | `test_csv_preview_highlights_errors_and_blocks_commit` | CSV with unknown farmer NIC highlights errors in preview and blocks all-or-nothing confirmation. | PASS |
| **TC-54** | `distributions` | `ExpiryBoundaryAndSafeguardTests` | `test_expiry_boundary_conditions` | Boundary tests: batch expiring yesterday is expired (write-off allowed), batch expiring today/tomorrow is unexpired (write-off blocked). | PASS |
| **TC-55** | `distributions` | `ExpiryBoundaryAndSafeguardTests` | `test_central_service_blocks_issuance_in_closed_season` | `confirm_issue_distribution` raises `ValidationError` if the season status is `CLOSED`. | PASS |
| **TC-56** | `distributions` | `ExpiryBoundaryAndSafeguardTests` | `test_seed_demo_data_guard_refuses_when_demo_mode_false` | Running `seed_demo_data` when `DEMO_MODE=False` without `--force` raises `CommandError`. | PASS |
| **TC-57** | `distributions` | `AuditLogAdminTests` | `test_audit_log_admin_permissions` | Django Admin for AuditLog disables add, change, and delete permissions. | PASS |
| **TC-58** | `distributions` | `CSVExportBOMTests` | `test_reports_csv_export_has_utf8_bom` | Exported reports CSV begins with UTF-8 BOM (`\ufeff`) for proper Excel Unicode rendering. | PASS |
| **TC-59** | `distributions` | `BatchTraceabilityTests` | `test_batch_trace_reconciliation_math` | Batch lifecycle reconciles: Dispatched = Received + Damaged + Missing + In Transit. | PASS |
| **TC-60** | `distributions` | `RoleAccessSecurityTests` | `test_auditor_post_request_rejected` | Auditor attempting POST actions on operational endpoints receives HTTP 403 Forbidden. | PASS |

---

## 3. Database Concurrency & Locking Verification

Unlike SQLite (which ignores `select_for_update()` row locks), our automated test suite connects to **PostgreSQL**.
- Tests `TC-21` and `TC-38` spawn real Python threads using `django.test.TransactionTestCase` with distinct database connections.
- This guarantees:
  1. No two counter officers can redeem the same QR token or 6-digit SMS code simultaneously.
  2. No warehouse dispatch can be double-received.
  3. No farmer quota can drop below 0 kg under concurrent counter requests.
