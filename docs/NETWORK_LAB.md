# Safe Windows network-support lab guide

Only use a dedicated lab, with written authorisation and a defined scope. The Task 5 API checks a single allowlisted host and TCP port, never a subnet.

## 1. IP configuration and default gateway

On a Windows 11 lab workstation, open PowerShell (ordinary user). Run `ipconfig /all`, `Get-NetIPConfiguration`, `Get-NetIPAddress -AddressFamily IPv4`, and `Get-NetRoute -DestinationPrefix '0.0.0.0/0'`. Record IPv4 address, mask/prefix length, DNS servers, NIC interface alias, DHCP status and default gateway. An IPv4 address in `169.254.0.0/16` often indicates automatic link-local assignment after DHCP failure. Use `ping <approved-gateway>` for a manual ICMP check (firewalls may block ICMP; failed ping does not prove a router is down).

## 2. TCP/IP vs DNS

`Resolve-DnsName localhost` demonstrates a safe lookup; `Resolve-DnsName testhost.lab.example` only in an authorised internal DNS environment. Inspect A/AAAA results and the configured DNS server; beware split-horizon VPN resolution. `Test-NetConnection -ComputerName localhost -Port 8000` (while FastAPI runs) checks a single approved TCP service. Application HTTP health (`http://127.0.0.1:8000/health`) is a separate layer from raw TCP reachability. If DNS succeeds but TCP fails, check whether the application listens at the expected address, the destination host firewall and routing. Avoid turning these commands into unapproved scans.

## 3. VLANs, switchports and trunks

In an isolated managed-switch lab, place client A into VLAN 10 and client B into VLAN 20, with management ports separated. Verify each client has the correct gateway subnet and that inter-VLAN routing requires an explicitly configured L3 device or firewall. Confirm switchport access VLAN and upstream tagged trunk membership in the **switch vendor's manual**; do not apply Cisco-specific commands to unfamiliar switches. Keep a physical recovery/console path before modifying VLANs. The platform does **not** change switchport configuration.

## 4. Routes, gateways and VPN

`route print` and `Get-NetRoute` reveal competing default routes and VPN-added more-specific routes. Confirm the lab VPN is configured and test only approved internal hosts. If DNS changes when VPN connects, compare `Get-DnsClientServerAddress` and NRPT/split DNS policies. Firewall troubleshooting: `Get-NetFirewallProfile` and `Get-NetFirewallRule -Enabled True` are read-only, but logs/policies may be centrally managed. Never disable Windows Firewall or antivirus to test connectivity. Work with the security administrator to check specific allow rules.

## 5. Failure triage and Task 2 escalation

Record symptom → local IP settings → name resolution → host reachability → single service TCP check → application health → firewall/VPN logs. In `/operations` enter `TCP`, `localhost`, port `8000`. Stop FastAPI only in a separate lab session or use a deliberately stopped **allowlisted** lab port to simulate failure; a linked `Network` ticket is created. Repeat the same failure to show incident reuse rather than ticket multiplication. Capture error class and elapsed time; do not store credentials, customer identifiers or full command transcripts in tickets.
