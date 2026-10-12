# Optional isolated FreePBX / Asterisk test-lab guide

**Default Task 5 is mock-only. No PBX connection, carrier account, SIP trunk or external telephone call is necessary.** Import `sample_data/task5_call_logs.csv`, edit a `Main` menu rule and simulate digit 1 routing to `ClaimsQueue` on `/operations`. The rule change is retained in SQL Server and the shared audit table; simulations never establish a call.

## Isolated lab (separate environment, not enabled by FastAPI)

1. Set up an offline Linux VM running a supported version of Asterisk, or a FreePBX VM with Asterisk, on a host-only virtual network. Read vendor deployment and security guidance first. Disable Internet-facing SIP access, dial-out trunks and NAT port forwarding.
2. Create two fictional endpoints/extensions (for example, 201 and 202) with unique lab-only credentials, register software phones on the isolated VM network and verify local extension calls. Never reuse production SIP credentials.
3. In FreePBX, configure a test IVR under **Applications → IVR** with a custom prompt: press 1 for Claims, 2 for IT. Point selections to local lab queues/extensions only. In plain Asterisk, use a dedicated dialplan context with `Background()` and `WaitExten()`, plus tightly scoped numeric DTMF extensions. No public number or trunk.
4. Place lab calls, deliberately do not answer one call, and review call detail records (CDRs) in the lab. Export fictional records to the Task 5 CSV schema. Do not import real call recordings, phone numbers or customer information.
5. Contrast simulated menu rules stored in SQL Server with real PBX dialplan behaviour and troubleshoot endpoint registration, audio/RTP, SIP signalling, firewall policies and prompt routing **only within the approved lab**.

Official references: https://docs.asterisk.org/Deployment/Basic-PBX-Functionality/Auto-attendant-and-IVR-Menus/Background-and-WaitExten-Applications/ and https://www.freepbx.org/ .
