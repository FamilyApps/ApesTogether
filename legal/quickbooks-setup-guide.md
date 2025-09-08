# QuickBooks Setup Guide for Family Apps LLC

## Phase 1: Business Foundation Setup

### Step 1: Business Bank Account Setup ✅ COMPLETED
**You already have:**
- Business checking account ✅
- EIN number ✅ (locate your documents for QuickBooks setup)

**Next Steps:**
- Ensure check writing is enabled
- Confirm online banking access
- Request business debit card if needed

### Step 2: QuickBooks Simple Start Setup (When Ready)

1. **Sign Up:**
   - Go to quickbooks.intuit.com
   - Choose "Simple Start" ($15/month)
   - Use support@apestogether.ai business email (set up first)

2. **Company Setup:**
   - Company Name: Family Apps LLC
   - Industry: Software/Technology Services
   - Business Type: LLC
   - EIN: [Locate from your documents]
   - Address: [Your business address]

3. **Connect Bank Account:**
   - Add your existing business checking account
   - Enable automatic transaction downloads
   - Set up bank feeds for real-time sync

## Phase 2: Chart of Accounts Setup

### Step 3: Create Custom Account Categories

**Income Accounts:**
- `4000 - Subscription Revenue` (for all Stripe payments)
- `4100 - Platform Fees` (your 30% retained revenue)

**Expense Accounts:**
- `6000 - User Payments` (70% paid to content creators)
- `6100 - Payment Processing Fees` (Stripe fees)
- `6200 - Software Subscriptions` (QuickBooks, hosting, etc.)
- `6300 - Professional Services` (legal, accounting)

**Asset Accounts:**
- `1200 - Accounts Receivable` (pending Stripe transfers)
- `1300 - User Payment Clearing` (temporary holding account)

## Phase 3: Stripe Integration

### Step 4: Connect Stripe to QuickBooks

1. **In QuickBooks:**
   - Go to Banking → Connect Account
   - Search for "Stripe"
   - Enter your Stripe login credentials
   - Authorize connection

2. **Transaction Mapping:**
   - Map Stripe deposits → `4000 - Subscription Revenue`
   - Map Stripe fees → `6100 - Payment Processing Fees`
   - Set up automatic categorization rules

3. **Daily Sync Setup:**
   - Enable automatic daily imports
   - Set up email notifications for new transactions

## Phase 4: Progressive W-9 and Payment System

### Step 5: W-9 Collection Workflow

**Progressive Collection Strategy:**
1. **User Enables Subscriptions:**
   - Show gentle W-9 prompt: "Complete tax forms to receive payments"
   - Allow skip initially - store in app database when completed

2. **User Gets First Subscriber:**
   - Email + in-app notification: "Complete W-9 to receive payments"
   - Store W-9 data in your app database (encrypted SSN/EIN)

3. **User Earns $50+ Monthly:**
   - Auto-create QuickBooks vendor from stored W-9 data
   - Process payment through QuickBooks

### Step 6: Monthly Payment Workflow

**Automated Process:**
1. **Generate Earners Report** (from your app):
   ```
   User ID | Username | Monthly Earnings | W-9 Complete | QB Vendor Exists
   123     | john_doe | $70.00          | Yes          | No
   456     | jane_inv | $175.00         | Yes          | Yes
   ```

2. **Create Missing QuickBooks Vendors:**
   - Only for users earning $50+ this month
   - Use stored W-9 data from app database
   - Batch create via API or manual entry

3. **Record Payments in QuickBooks:**
   - Go to Expenses → Write Checks
   - Payee: User's legal name (from W-9)
   - Amount: User's 70% share
   - Account: `6000 - User Payments`
   - Class: "Content Creators" (single class for all)

4. **Print and Mail Checks:**
   - Batch print all checks at once
   - Update app database with check numbers

### Step 6: Scalable User Management Strategy

**Only Create Vendors When They Actually Get Paid:**
- Don't create vendors for every W-9 submission
- Only add to QuickBooks when user reaches first payout ($1+ earned)
- Use your app's database to store all W-9 info until needed

**Automated Vendor Creation Process:**
1. **Monthly Revenue Report** identifies users earning money
2. **Batch Create Vendors** only for users getting paid that month
3. **Use QuickBooks API** to automate vendor creation (see Phase 7)

**Class Strategy - Simplified:**
- **Option A**: No classes - track everything in your app database
- **Option B**: Single class "Content Creators" for all user payments
- **Option C**: Quarterly classes "Q1-2025-Creators", "Q2-2025-Creators"

## Phase 5: Tax Compliance Setup

### Step 7: Automated 1099 Preparation System

**Smart Vendor Management:**
1. **Threshold-Based Creation:**
   - Only create QB vendors when user hits $50+ in monthly earnings
   - Or when user approaches $600 annual threshold (November/December)
   - Bulk import W-9 data via QuickBooks API

2. **Batch Processing:**
   - Monthly: Export earning users from your app
   - Auto-create vendors in QuickBooks via API
   - Generate checks for all new vendors

2. **1099 Settings:**
   - Go to Taxes → 1099s
   - Enable 1099-NEC tracking
   - Map `6000 - User Payments` to Box 1 (Nonemployee Compensation)
   - Set $600 threshold for automatic 1099 generation

3. **Quarterly Reviews:**
   - Run "1099 Summary Report" quarterly
   - Track users approaching $600 threshold
   - Ensure W-9s are collected before threshold

## Phase 6: Monthly Reconciliation Process

### Step 8: Monthly Bookkeeping Routine

**Week 1 of Each Month:**
1. **Bank Reconciliation:**
   - Go to Banking → Reconcile
   - Match all transactions from previous month
   - Resolve any discrepancies

2. **Revenue Allocation:**
   - Review all Stripe deposits
   - Ensure proper categorization (subscription revenue)
   - Verify fee deductions are recorded

3. **User Payment Processing:**
   - Generate user revenue report from app
   - Create checks in QuickBooks
   - Print and mail checks
   - Record check numbers and dates

4. **Financial Reports:**
   - Generate Profit & Loss statement
   - Review cash flow
   - Export data for tax preparation

## Phase 7: QuickBooks API Integration (Recommended for Scale)

### Step 9: Automated W-9 to QuickBooks Workflow

**Monthly Automation Process:**
1. **Your App Generates Report:**
   ```python
   # Monthly payout report
   users_to_pay = [
       {"user_id": 123, "username": "john_doe", "amount": 70.00, "w9_complete": True},
       {"user_id": 456, "username": "jane_inv", "amount": 175.00, "w9_complete": True}
   ]
   ```

2. **QuickBooks API Auto-Creates Vendors:**
   ```python
   # Only for users getting paid this month
   for user in users_to_pay:
       if not vendor_exists_in_qb(user['user_id']):
           create_vendor_from_w9(user['user_id'])
   ```

3. **Batch Check Generation:**
   - API creates all expense entries at once
   - Print checks in single batch
   - Update your app with check numbers

**QuickBooks API Endpoints:**
- `POST /v3/company/{companyId}/vendor` - Create vendors
- `POST /v3/company/{companyId}/purchase` - Record expenses
- `GET /v3/company/{companyId}/reports/1099Summary` - 1099 data

**Implementation Priority:**
- **Phase 1**: Manual process for first 10-20 users
- **Phase 2**: API integration when you hit 50+ monthly payouts
- **Phase 3**: Full automation with batch processing

## Phase 8: Year-End Tax Process

### Step 10: Annual 1099 Filing

**January Process:**
1. **Generate 1099s:**
   - Go to Taxes → 1099s → Prepare 1099s
   - Review all contractors with $600+ payments
   - Verify W-9 information is complete

2. **File 1099s:**
   - E-file through QuickBooks (additional fee)
   - Or print and mail manually
   - Deadline: January 31st

3. **Provide to CPA:**
   - Export all financial data
   - Provide 1099 summary
   - Include bank statements and receipts

## Monthly Costs Summary

**Required Expenses:**
- QuickBooks Simple Start: $15/month
- Business checking account: $0-15/month
- Check printing supplies: ~$20/quarter
- 1099 e-filing (optional): ~$50/year

**Total Monthly Cost: ~$20-30**

## Getting Started Checklist

**Prerequisites (Completed):**
- [x] Business checking account
- [x] EIN number

**Email Setup (Do First):**
- [ ] Set up support@apestogether.ai in Gmail Workspace
- [ ] Set up privacy@apestogether.ai in Gmail Workspace
- [ ] Update TOS and Privacy Policy with correct emails

**QuickBooks Setup (When Ready):**
- [ ] Sign up for QuickBooks Simple Start ($15/month)
- [ ] Connect existing business bank account
- [ ] Set up chart of accounts
- [ ] Connect Stripe integration
- [ ] Create "Content Creators" class
- [ ] Set up 1099 vendor system

**App Database Setup (Development):**
- [ ] Create user_tax_info table for W-9 storage
- [ ] Implement progressive W-9 collection UI
- [ ] Build monthly earners report
- [ ] Create QuickBooks vendor sync process

**Monthly Operations (Future):**
- [ ] Generate earners report
- [ ] Create QuickBooks vendors for new earners
- [ ] Process batch payments
- [ ] Bank reconciliation

This progressive system scales from manual processing (first 20 users) to full automation (100+ users) while maintaining compliance.
