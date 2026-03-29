# Accounts App

This app is the identity and business structure backbone of the project.

## What this app owns

- `User`: the login entity.
- `Business`: the restaurant or merchant account.
- `Branch`: a physical operating branch under a business.
- `BranchOperatingHours`: open/close schedule per branch.
- `ProfileBase`: shared profile identity used for referrals and profile-type resolution.
- `CustomerProfile`: customer-facing profile attached to a user.
- `DriverProfile`: driver-facing profile attached to a user.
- `PrimaryAgent`: the main branch operator account.
- `LinkedStaff`: staff devices/accounts under a primary agent.
- `BusinessAdmin`: the business owner/admin account.
- `BusinessOnboardStatus`: progress through business onboarding.
- `BusinessCerd`: business registration/KYC record.
- `BusinessPayoutAccount`: payout destination for a business.
- Driver support models: `DriverCred`, `DriverAvailability`, `DriverOnboardingSubmission`, `DriverDocument`, `DriverVerification`, `DriverBankAccount`.

## Mental model

- `User` is the raw authenticated person.
- Profiles define what kind of actor that user is in the system.
- `BusinessAdmin` owns a `Business`.
- A `Business` has many `Branch` records.
- A `PrimaryAgent` is the branch-level operator.
- `LinkedStaff` hangs off `PrimaryAgent`, not directly off `Business`.

## Relationships that matter

- `User -> ProfileBase -> CustomerProfile/DriverProfile`
- `User -> BusinessAdmin -> Business -> Branch`
- `Branch -> PrimaryAgent -> LinkedStaff`
- `Branch -> BranchOperatingHours`
- `Business -> BusinessCerd`
- `Business -> BusinessPayoutAccount`

## What other apps depend on this

- `menu` depends heavily on `Business`, `Branch`, `CustomerProfile`, and `DriverProfile`.
- `payments` uses `User` and business ownership relationships.
- `driver_api` uses `DriverProfile`.
- `ratings` uses `CustomerProfile`, `DriverProfile`, and `Branch`.
- `referrals` uses `ProfileBase`.

## API shape in this app

- Auth and token endpoints live here.
- Customer registration/profile update lives here.
- Business onboarding phases 1-3 start here.
- Driver onboarding phases live here.

## Remember this when coming back

- If you are asking "who is this actor?", start in `accounts`.
- If you are asking "what business or branch does this person belong to?", start in `accounts`.
- This app owns identity and org structure, not ordering, pricing, or payments logic.
