# Architecture Constraints

The following constraints are approved for the Northstar Relay pilot.

1. The production region must be in the European Union.
2. Canonical customer content cannot be stored by a service that offers only United
   States regions.
3. Recurring application and data infrastructure must not exceed GBP 400 per month,
   excluding model inference and tax.
4. The team can operate Postgres and containerized services but cannot support a new
   distributed event broker during the pilot.
5. Recovery-point objective is 24 hours and recovery-time objective is four hours.
6. A provider-specific feature is acceptable only when an export path to an open format
   is documented.
7. Public-demo mode may use only the bundled synthetic corpus and must reject uploads,
   live GitHub connections, and arbitrary web URLs.
8. The application may suggest a decision, but only an explicit user action can accept,
   supersede, or delete it.
9. The retrieval system must preserve immutable source revisions and exact citation
   locators.

If evidence cannot establish whether an option satisfies a hard constraint, that result
is `unknown`; the option cannot be recommended until the gap is resolved.

