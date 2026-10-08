@echo off
rem ---------------------------------------------------------------------------------------------
rem  EDIT THESE THREE LINES ONCE. They are NOT secrets (no passwords or keys belong in this file).
rem  SITE_URL  : the SharePoint site that will hold the POU lists, e.g. https://contoso.sharepoint.com/sites/POU
rem  TENANT    : your tenant, e.g. contoso.onmicrosoft.com   (or the tenant GUID)
rem  CLIENT_ID : Application (client) ID of the Entra app registration you create in docs\07_Deployment.md step 2
rem ---------------------------------------------------------------------------------------------
set SITE_URL=https://CHANGE-ME.sharepoint.com/sites/POU
set TENANT=CHANGE-ME.onmicrosoft.com
set CLIENT_ID=00000000-0000-0000-0000-000000000000
rem  WORKBOOK: path to the workbook, relative to the package folder. Default = the folder that CONTAINS the package folder.
set WORKBOOK=..\POU_Inventory_Pilot Test _With_Badge.xlsm
