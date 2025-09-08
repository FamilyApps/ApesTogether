# W-9 Collection and Storage Workflow

## W-9 Collection Timing Strategy

### Option 1: Progressive Collection (Recommended)
**When User Enables Subscriptions:**
- Show gentle prompt: "To receive payments, you'll need to complete tax forms"
- Allow them to skip initially
- Store subscription toggle = ON without W-9

**When User Gets First Subscriber:**
- Email + in-app notification: "Congratulations! Complete your W-9 to receive payments"
- Still allow payments to accumulate
- More urgent messaging

**When User Approaches $50+ Monthly:**
- Required W-9 before next payout
- "Complete W-9 now to receive your $X payment"

### Option 2: Upfront Collection
**When User Enables Subscriptions:**
- Require W-9 completion before allowing subscription toggle
- Cleaner from compliance perspective
- May reduce subscription adoption

## W-9 Data Storage Lifecycle

### Phase 1: App Database Storage
**All W-9 data stored in your Flask app database:**
```sql
CREATE TABLE user_tax_info (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    legal_name VARCHAR(255),
    business_name VARCHAR(255),
    tax_classification VARCHAR(50),
    ssn_ein VARCHAR(20) ENCRYPTED,
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    zip_code VARCHAR(20),
    w9_completed_date TIMESTAMP,
    backup_withholding_exempt BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Phase 2: QuickBooks Integration (Only When Paid)
**Monthly Process:**
1. Query users earning $50+ this month
2. Check if vendor exists in QuickBooks
3. If not, create vendor using stored W-9 data
4. Mark user as "qb_vendor_created" in your database

### Phase 3: Long-term Storage
**W-9s Never Earning Money:**
- Keep in your database indefinitely (required for backup withholding compliance)
- Never create QuickBooks vendor
- Annual cleanup of users who never earned anything

**W-9s for Paid Users:**
- Sync to QuickBooks when first payment occurs
- Keep original in your database as backup
- QuickBooks becomes source of truth for active vendors

## Data Flow Example

### User Journey: john_doe
1. **Month 1**: Enables subscriptions, skips W-9
2. **Month 2**: Gets first subscriber, completes W-9 → stored in app database
3. **Month 3**: Earns $25 → W-9 stays in app database only
4. **Month 4**: Earns $75 → W-9 data auto-creates QuickBooks vendor
5. **Month 5+**: All payments processed through QuickBooks vendor

### User Journey: jane_inv  
1. **Month 1**: Enables subscriptions, completes W-9 → stored in app database
2. **Months 2-12**: Never gets subscribers → W-9 stays in app database only
3. **Year 2**: Still no earnings → W-9 remains in app database (compliance requirement)

## Benefits of This Approach

### Compliance Maintained:
- All W-9s collected and stored (backup withholding compliance)
- 1099s generated only for users earning $600+
- Clean QuickBooks with only active vendors

### Scalability:
- 1000 W-9s in app database = manageable
- 20-50 vendors in QuickBooks = clean and organized
- API automation handles the bridge between systems

### User Experience:
- Progressive collection reduces friction
- Users can start earning before completing paperwork
- Clear communication about requirements

## Implementation Priority

**Phase 1**: Store all W-9s in app database
**Phase 2**: Manual QuickBooks vendor creation for paying users
**Phase 3**: API automation for vendor creation
**Phase 4**: Automated 1099 generation from QuickBooks data
