STATUS: CANDIDATE - NOT VALIDATED.
This tree follows the documented unpacked layout of a Power Platform solution containing cloud flows (solution.xml, customizations.xml,
Workflows/<name>-<guid>.json). It was generated and statically checked, but it has NEVER been imported into a tenant and was NOT produced by
the Power Platform CLI (pac). If the portal refuses it, use the manual route in docs/04_Deployment.md (build each flow from flows/docs/<Flow>.md).
After import: open each flow, set the two connections (SharePoint, Office 365 Outlook) to the FLOW SERVICE ACCOUNT, edit the Cfg_SiteUrl action, then turn the flow on.
