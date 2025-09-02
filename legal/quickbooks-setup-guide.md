# QuickBooks Setup Guide for Family Apps LLC

## Phase 1: Business Foundation Setup

### Step 1: Business Bank Account Setup
**Before QuickBooks, you need a business checking account:**

1. **Choose a Business Bank:**
   - Chase Business Complete Banking (no monthly fee with $2K balance)
   - Bank of America Business Advantage (no monthly fee with $3K balance)
   - Local credit unions (often better rates)

2. **Required Documents:**
   - Family Apps LLC formation documents
   - EIN (Employer Identification Number) from IRS
   - Your personal ID and SSN
   - Initial deposit ($100-500 minimum)

3. **Account Features to Request:**
   - Business checking with check writing
   - Online banking access
   - Mobile deposit for checks
   - Business debit card

### Step 2: QuickBooks Simple Start Setup

1. **Sign Up:**
   - Go to quickbooks.intuit.com
   - Choose "Simple Start" ($15/month)
   - Use Family Apps LLC business email

2. **Company Setup:**
   - Company Name: Family Apps LLC
   - Industry: Software/Technology Services
   - Business Type: LLC
   - EIN: [Your EIN number]
   - Address: [Your business address]

3. **Connect Bank Account:**
   - Add your new business checking account
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

## Phase 4: User Payment System

### Step 5: Create User Payment Workflow

**Monthly Process:**
1. **Generate User Revenue Report** (from your app):
   ```
   User ID | Username | Gross Revenue | User Share (70%) | Platform Fee (30%)
   123     | john_doe | $100.00      | $70.00          | $30.00
   456     | jane_inv | $250.00      | $175.00         | $75.00
   ```

2. **In QuickBooks - Record User Payments:**
   - Go to Expenses → Write Checks
   - For each user payment:
     - Payee: User's legal name (from W-9)
     - Amount: User's 70% share
     - Account: `6000 - User Payments`
     - Memo: "Portfolio subscription revenue - [Month/Year]"
     - Class: [Username] (for tracking)

3. **Print and Mail Checks:**
   - Use QuickBooks check printing feature
   - Or write manual checks and record in QB

### Step 6: Set Up Classes for User Tracking

**Create Classes for Each User:**
- Class Name: Username (e.g., "john_doe")
- Use classes to track revenue and payments per user
- Essential for 1099 preparation

## Phase 5: Tax Compliance Setup

### Step 7: 1099 Preparation System

1. **Vendor Setup:**
   - For each user receiving payments:
     - Go to Expenses → Vendors
     - Add vendor with legal name from W-9
     - Enter SSN/EIN from W-9
     - Add address from W-9
     - Set vendor type: "1099 Contractor"

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

## Phase 7: App Integration (Future Enhancement)

### Step 9: QuickBooks API Integration (Optional)

**For Automation:**
- Use QuickBooks Online API
- Automatically create vendor records from W-9 submissions
- Auto-generate expense entries for user payments
- Sync subscription data with QuickBooks

**API Endpoints Needed:**
- Create vendors (users)
- Record expenses (user payments)
- Generate 1099 data
- Pull financial reports

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

- [ ] Open business checking account
- [ ] Sign up for QuickBooks Simple Start
- [ ] Connect bank account to QuickBooks
- [ ] Set up chart of accounts
- [ ] Connect Stripe integration
- [ ] Create user classes for tracking
- [ ] Set up 1099 vendor system
- [ ] Establish monthly reconciliation routine

This system will handle everything from subscription revenue tracking to 1099 generation, making tax compliance seamless.
