// Cost guard (ADR-076), next to the resources main.bicep created in the resource group:
// a $20 monthly budget with emails at 25, 50, 80 and 100 percent and when the month is forecast to
// pass $20, and a kill switch: at 100 percent the action group calls a Logic App that stops the
// Container App and makes the database pause, instead of bill, once its free allowance is used.
// setup-cost-guard.sh deploys it with cost-guard-sub.bicep; restart with the same script's --restart.

@description('Same prefix as main.bicep.')
param prefix string = 'cashflow'

@description('Who gets the budget emails.')
param alertEmail string

@description('Monthly cap in USD.')
param amount int = 20

@description('First day of the current month, for the budget start date.')
param budgetStartDate string = utcNow('yyyy-MM-01')

param location string = resourceGroup().location

var suffix = uniqueString(resourceGroup().id)
// Built-in Contributor, scoped below to the app and the database only.
var contributor = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'b24988ac-6180-42a0-ab88-20f7382dd24c'
)
var arm = environment().resourceManager

resource app 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: '${prefix}-app'
}

resource sql 'Microsoft.Sql/servers@2023-08-01-preview' existing = {
  name: '${prefix}-sql-${suffix}'
}

resource db 'Microsoft.Sql/servers/databases@2023-08-01-preview' existing = {
  parent: sql
  name: 'cashflow'
}

// ---------- The kill switch: a Logic App with its own identity ----------
resource killSwitch 'Microsoft.Logic/workflows@2019-05-01' = {
  name: '${prefix}-kill-switch'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    state: 'Enabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      triggers: {
        manual: {
          type: 'Request'
          kind: 'Http'
          inputs: { schema: {} }
        }
      }
      actions: {
        Stop_the_app: {
          type: 'Http'
          runAfter: {}
          inputs: {
            method: 'POST'
            uri: '${arm}${substring(app.id, 1)}/stop?api-version=2024-03-01'
            authentication: { type: 'ManagedServiceIdentity', audience: arm }
          }
        }
        Pause_the_database_at_the_limit: {
          type: 'Http'
          runAfter: {}
          inputs: {
            method: 'PATCH'
            uri: '${arm}${substring(db.id, 1)}?api-version=2023-08-01-preview'
            headers: { 'Content-Type': 'application/json' }
            body: { properties: { freeLimitExhaustionBehavior: 'AutoPause' } }
            authentication: { type: 'ManagedServiceIdentity', audience: arm }
          }
        }
      }
    }
  }
}

resource canStopApp 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(app.id, killSwitch.id, 'contributor')
  scope: app
  properties: {
    roleDefinitionId: contributor
    principalId: killSwitch.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource canPauseDb 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(db.id, killSwitch.id, 'contributor')
  scope: db
  properties: {
    roleDefinitionId: contributor
    principalId: killSwitch.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: '${prefix}-cost-cap'
  location: 'global'
  properties: {
    groupShortName: 'costcap'
    enabled: true
    emailReceivers: [
      { name: 'owner', emailAddress: alertEmail, useCommonAlertSchema: true }
    ]
    logicAppReceivers: [
      {
        name: 'kill-switch'
        resourceId: killSwitch.id
        callbackUrl: listCallbackUrl('${killSwitch.id}/triggers/manual', '2019-05-01').value
        useCommonAlertSchema: true
      }
    ]
  }
}

// ---------- The budget (replaces the $10 one main.bicep had: same name) ----------
var email = [alertEmail]
resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: '${prefix}-budget'
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actualOver25: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 25
        contactEmails: email
        thresholdType: 'Actual'
      }
      actualOver50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        contactEmails: email
        thresholdType: 'Actual'
      }
      actualOver80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        contactEmails: email
        thresholdType: 'Actual'
      }
      actualAt100StopTheApp: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: email
        contactGroups: [actionGroup.id]
        thresholdType: 'Actual'
      }
      forecastOver100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: email
        thresholdType: 'Forecasted'
      }
    }
  }
}

output killSwitch string = killSwitch.name
output actionGroup string = actionGroup.name
